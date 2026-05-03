"""
title: Hindsight Memory for Open WebUI
author: Jon Stacey
author_url: https://JonStacey.com
version: 0.1.1
description: Recall and retain long-term memory in Open WebUI using Hindsight.
required_open_webui_version: 0.5.0
"""

from __future__ import annotations

import asyncio
import copy
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, Field


class HindsightHTTPClient:
    def __init__(self, base_url: str, api_key: str, timeout_seconds: int = 20):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key.strip()
        self.timeout_seconds = max(1, int(timeout_seconds))

    def _candidate_base_urls(self) -> List[str]:
        candidates = [self.base_url]
        parsed = urllib.parse.urlsplit(self.base_url)
        host = (parsed.hostname or "").lower()
        if host in {"localhost", "127.0.0.1"}:
            # Open WebUI often runs in Docker where localhost refers to the container,
            # not the host machine running Hindsight.
            fallback_netloc = "host.docker.internal"
            if parsed.port:
                fallback_netloc += f":{parsed.port}"
            if parsed.username or parsed.password:
                auth = parsed.username or ""
                if parsed.password:
                    auth += f":{parsed.password}"
                fallback_netloc = f"{auth}@{fallback_netloc}"
            fallback = urllib.parse.urlunsplit(
                (parsed.scheme or "http", fallback_netloc, parsed.path, parsed.query, parsed.fragment)
            ).rstrip("/")
            if fallback not in candidates:
                candidates.append(fallback)
        return candidates

    def _request_once(
        self,
        base_url: str,
        method: str,
        path: str,
        body: Optional[dict] = None,
        query: Optional[dict] = None,
    ) -> Any:
        url = base_url.rstrip("/") + path
        if query:
            encoded = urllib.parse.urlencode(
                [(k, v) for k, v in query.items() if v is not None and v != ""],
                doseq=True,
            )
            if encoded:
                url += "?" + encoded

        data = None
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if body is not None:
            data = json.dumps(body).encode("utf-8")

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
            raw = resp.read()
            if not raw:
                return None
            text = raw.decode("utf-8")
            content_type = resp.headers.get("Content-Type", "")
            if "application/json" in content_type or text[:1] in ("{", "["):
                return json.loads(text)
            return text

    def request(
        self,
        method: str,
        path: str,
        body: Optional[dict] = None,
        query: Optional[dict] = None,
    ) -> Any:
        last_error: Optional[Exception] = None
        for base_url in self._candidate_base_urls():
            try:
                return self._request_once(base_url, method, path, body=body, query=query)
            except urllib.error.HTTPError as e:
                error_text = e.read().decode("utf-8", errors="replace") if e.fp else ""
                raise RuntimeError(
                    f"Hindsight HTTP {e.code} {e.reason} for {method} {base_url + path}: {error_text}"
                ) from e
            except Exception as e:
                last_error = e
                continue
        raise RuntimeError(
            f"Hindsight request failed for {method} {self.base_url + path}: {last_error}"
        ) from last_error


class Filter:
    class Valves(BaseModel):
        priority: int = Field(
            default=0,
            description="Filter execution order. Lower values run earlier.",
        )
        enabled: bool = Field(
            default=True,
            description="Master switch for Hindsight integration.",
        )
        base_url: str = Field(
            default="http://localhost:8888",
            description="Hindsight server base URL.",
        )
        api_key: str = Field(
            default="",
            description="Hindsight API bearer token.",
            json_schema_extra={"input": {"type": "password"}},
        )
        bank_scope: Literal["global", "user", "chat", "manual"] = Field(
            default="global",
            description="How to resolve the Hindsight bank ID.",
            json_schema_extra={
                "input": {
                    "type": "select",
                    "options": ["global", "user", "chat", "manual"],
                }
            },
        )
        bank_id: str = Field(
            default="open-webui",
            description="Default/manual Hindsight bank ID.",
        )
        global_bank_id: str = Field(
            default="open-webui",
            description="Databank used when bank_scope=global.",
        )
        bank_prefix: str = Field(
            default="open-webui",
            description="Prefix used when deriving user/chat-scoped bank IDs.",
        )
        recall_mode: Literal["hybrid", "context", "tools", "off"] = Field(
            default="hybrid",
            description="How aggressively to inject recalled memory into the prompt.",
            json_schema_extra={
                "input": {
                    "type": "select",
                    "options": ["hybrid", "context", "tools", "off"],
                }
            },
        )
        search_budget: Literal["low", "mid", "high"] = Field(
            default="mid",
            description="Hindsight recall budget.",
            json_schema_extra={
                "input": {"type": "select", "options": ["low", "mid", "high"]},
            },
        )
        reflect_budget: Literal["low", "mid", "high"] = Field(
            default="low",
            description="Hindsight reflect budget.",
            json_schema_extra={
                "input": {"type": "select", "options": ["low", "mid", "high"]},
            },
        )
        reasoning_level: Literal["low", "medium", "high"] = Field(
            default="low",
            description="Guidance level used when shaping Hindsight missions.",
            json_schema_extra={
                "input": {"type": "select", "options": ["low", "medium", "high"]},
            },
        )
        reasoning_level_cap: Literal["low", "medium", "high"] = Field(
            default="medium",
            description="Maximum reasoning level guidance.",
            json_schema_extra={
                "input": {"type": "select", "options": ["low", "medium", "high"]},
            },
        )
        recall_types: str = Field(
            default="world,experience,observation",
            description="Comma-separated memory types to recall.",
        )
        recall_tags: str = Field(
            default="",
            description="Optional comma-separated tags to scope recall and retention.",
        )
        recall_tags_match: Literal["any", "all", "any_strict", "all_strict"] = Field(
            default="any",
            description="Tag matching mode for recall.",
            json_schema_extra={
                "input": {
                    "type": "select",
                    "options": ["any", "all", "any_strict", "all_strict"],
                }
            },
        )
        context_tokens: int = Field(
            default=1200,
            description="Approximate token budget for injected memory context.",
        )
        recall_query_context_turns: int = Field(
            default=2,
            description="How many prior turns to include when building a recall query.",
        )
        recall_query_max_tokens: int = Field(
            default=400,
            description="Approximate token budget for recall queries. Keeps requests safely under Hindsight's 500-token cap.",
        )
        recall_query_max_queries: int = Field(
            default=4,
            description="Maximum number of recall queries to generate from one user prompt.",
        )
        context_refresh_ttl_seconds: int = Field(
            default=300,
            description="Refresh recalled memory context after this many seconds.",
        )
        context_refresh_message_threshold: int = Field(
            default=8,
            description="Refresh recalled memory context after this many new turns.",
        )
        context_cadence: int = Field(
            default=1,
            description="Minimum turns between active recall refreshes.",
        )
        injection_frequency: Literal["every-turn", "first-turn"] = Field(
            default="every-turn",
            description="Whether to inject memory on every turn or only the first turn.",
            json_schema_extra={
                "input": {
                    "type": "select",
                    "options": ["every-turn", "first-turn"],
                }
            },
        )
        retain_async: bool = Field(
            default=True,
            description="Send retain requests asynchronously.",
        )
        auto_create_bank: bool = Field(
            default=True,
            description="Ensure the bank exists and is configured before use.",
        )
        save_messages: bool = Field(
            default=True,
            description="Retain the latest user/assistant turn.",
        )
        max_recall_results: int = Field(
            default=8,
            description="Maximum number of recalled memories to render.",
        )
        max_recall_chars: int = Field(
            default=6000,
            description="Maximum characters to inject from recalled memories.",
        )
        max_message_chars: int = Field(
            default=25000,
            description="Maximum characters to store per retained turn.",
        )
        recall_long_query_behavior: Literal["skip", "truncate"] = Field(
            default="truncate",
            description="How to handle recall queries that exceed the configured length. Truncate is the recommended default.",
            json_schema_extra={
                "input": {"type": "select", "options": ["skip", "truncate"]},
            },
        )
        reflect_mode: Literal["smart", "always", "never"] = Field(
            default="smart",
            description="How reflect should be applied. smart is the recommended Hindsight-style default.",
            json_schema_extra={
                "input": {"type": "select", "options": ["smart", "always", "never"]},
            },
        )
        retain_mission: str = Field(
            default="Retain important personal preferences, decisions, facts, and long-lived context from the conversation.",
            description="Mission guidance passed to Hindsight retain operations.",
        )
        reflect_mission: str = Field(
            default="Use the conversation and memory bank to answer with useful long-term context.",
            description="Mission guidance passed to Hindsight reflect / bank configuration.",
        )
        retain_extraction_mode: Literal["concise", "verbose", "custom"] = Field(
            default="concise",
            description="How Hindsight should extract facts when retaining memories.",
            json_schema_extra={
                "input": {
                    "type": "select",
                    "options": ["concise", "verbose", "custom"],
                }
            },
        )
        retain_custom_instructions: str = Field(
            default="",
            description="Custom extraction instructions when retain_extraction_mode=custom.",
        )
        retain_chunk_size: int = Field(
            default=2500,
            description="Maximum character chunk size used when packaging retained content.",
        )
        enable_observations: bool = Field(
            default=True,
            description="Enable automatic observation consolidation after retain.",
        )
        observations_mission: str = Field(
            default="Observations should preserve stable facts, preferences, and recurring decisions.",
            description="Mission used when consolidating observations.",
        )
        show_recall_indicator: bool = Field(
            default=True,
            description="Emit status messages while recalling memory.",
        )
        show_retain_indicator: bool = Field(
            default=True,
            description="Emit status messages while retaining memory.",
        )
        indicators_in_context: bool = Field(
            default=False,
            description="Include memory status markers in the model context.",
        )
        logging: bool = Field(
            default=True,
            description="Log lightweight debugging details to stdout.",
        )
        timeout_seconds: int = Field(
            default=90,
            description="HTTP timeout for Hindsight requests.",
        )

    class UserValves(BaseModel):
        bank_scope: Optional[Literal["global", "user", "chat", "manual"]] = Field(
            default=None,
            description="Optional per-user override for how the bank ID is resolved.",
            json_schema_extra={
                "input": {
                    "type": "select",
                    "options": ["global", "user", "chat", "manual"],
                }
            },
        )
        bank_id: Optional[str] = Field(
            default=None,
            description="Optional per-user override for the global/manual bank ID.",
        )
        recall_mode: Optional[Literal["hybrid", "context", "tools", "off"]] = Field(
            default=None,
            description="Optional per-user override for recall mode.",
        )
        recall_tags: Optional[str] = Field(
            default=None,
            description="Optional per-user override for recall/retain tags.",
        )
        enable_memory: Optional[bool] = Field(
            default=None,
            description="Optional per-user override to enable/disable Hindsight integration.",
        )

    def __init__(self):
        self.valves = self.Valves()
        self._lock = threading.Lock()
        self._chat_state: Dict[str, Dict[str, Any]] = {}
        self._bank_cache: Dict[str, float] = {}

    def _log(self, message: str):
        if self.valves.logging:
            print(f"[hindsight-openwebui] {message}")

    async def _emit(self, emitter, description: str, done: bool = False):
        if not emitter:
            return
        try:
            result = emitter(
                {
                    "type": "status",
                    "data": {"description": description, "done": done, "hidden": False},
                }
            )
            if asyncio.iscoroutine(result):
                return await result
            return result
        except Exception:
            return None

    def _normalize_text(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, list):
            parts = []
            for item in value:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        parts.append(str(item.get("text", "")))
                    elif item.get("type") == "image_url":
                        parts.append("[image]")
                    else:
                        parts.append(json.dumps(item, ensure_ascii=False))
                else:
                    parts.append(str(item))
            return "\n".join(p for p in parts if p)
        if isinstance(value, dict):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    def _clean_id(self, value: str, fallback: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", value or "")
        slug = re.sub(r"-+", "-", slug).strip("-_")
        return slug or fallback

    def _split_csv(self, value: str) -> List[str]:
        return [item.strip() for item in (value or "").split(",") if item.strip()]

    def _approx_token_count(self, text: str) -> int:
        if not text:
            return 0
        return len(re.findall(r"\w+|[^\w\s]", text, flags=re.UNICODE))

    def _trim_text_to_tokens(self, text: str, max_tokens: int) -> str:
        max_tokens = max(1, int(max_tokens))
        if not text:
            return ""
        tokens = re.findall(r"\w+|[^\w\s]", text, flags=re.UNICODE)
        if len(tokens) <= max_tokens:
            return text
        if max_tokens <= 16:
            return " ".join(tokens[:max_tokens])
        keep_head = max(8, max_tokens // 3)
        keep_tail = max(8, max_tokens - keep_head)
        if keep_head + keep_tail > max_tokens:
            keep_tail = max(8, max_tokens - keep_head)
        return " ".join(tokens[:keep_head]) + "\n...[truncated]...\n" + " ".join(tokens[-keep_tail:])

    def _extract_recall_queries(self, user_text: str, messages: List[dict], settings: dict) -> List[str]:
        user_text = (user_text or "").strip()
        if not user_text:
            return []

        max_queries = max(1, int(settings.get("recall_query_max_queries", 4)))
        max_tokens = max(1, int(settings.get("recall_query_max_tokens", 400)))
        context_turns = max(0, int(settings.get("recall_query_context_turns", 2)))

        lines = []
        for msg in (messages or [])[-context_turns - 1 :]:
            role = msg.get("role", "unknown")
            content = self._normalize_text(msg.get("content")).strip()
            if content:
                lines.append(f"{role}: {content}")

        source_text = "\n".join(lines).strip() or user_text
        user_sentence = re.split(r"[\n\.!?]", user_text)[-1].strip() or user_text
        user_sentence = self._trim_text_to_tokens(user_sentence, max_tokens)

        # Heuristic extractive compression: preserve names, technical terms, dates, and the last user ask.
        anchors: List[str] = []
        seen = set()
        for pattern in (
            r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b",  # names / titles
            r"\b\d{4}(?:-\d{2}(?:-\d{2})?)?\b",  # dates
            r"\b(?:january|february|march|april|may|june|july|august|september|october|november|december|spring|summer|fall|autumn|winter|yesterday|today|tomorrow|last\s+spring|last\s+summer|last\s+fall|last\s+winter|last\s+year|this\s+week|last\s+week|next\s+week)\b",
            r"`[^`]+`|\"[^\"]+\"|'[^']+'",  # quoted / code terms
            r"\b[A-Za-z0-9_.-]{3,}\b",  # technical / identifier-like terms
        ):
            for match in re.findall(pattern, source_text, flags=re.IGNORECASE):
                candidate = str(match).strip().strip(".,:;!?()[]{}")
                key = candidate.lower()
                if candidate and key not in seen:
                    seen.add(key)
                    anchors.append(candidate)

        queries: List[str] = []

        def add_query(q: str):
            q = re.sub(r"\s+", " ", (q or "")).strip()
            if not q:
                return
            q = self._trim_text_to_tokens(q, max_tokens)
            if q and q not in queries:
                queries.append(q)

        # Start with the user's own question, then add compressed anchor-based variants.
        add_query(user_sentence)
        if anchors:
            add_query(" ".join(anchors[: min(len(anchors), 6)]))
            if len(anchors) >= 2:
                add_query(" ".join(anchors[:2]))
            if len(anchors) >= 4:
                add_query(" ".join(anchors[:4]))
            if len(anchors) >= 6:
                add_query(" ".join(anchors[:6]))

        if not queries:
            add_query(source_text)

        return queries[:max_queries]

    def _resolve_user_valves(self, __user__: Optional[dict]) -> Optional[BaseModel]:
        if not __user__:
            return None
        return __user__.get("valves")

    def _effective_settings(self, __user__: Optional[dict], __metadata__: Optional[dict]) -> dict:
        settings = self.valves.model_dump()
        user_valves = self._resolve_user_valves(__user__)
        if user_valves is not None:
            for key in ("bank_scope", "bank_id", "recall_mode", "recall_tags", "enable_memory"):
                try:
                    value = getattr(user_valves, key)
                except Exception:
                    value = None
                if value not in (None, ""):
                    settings[key] = value
        if settings.get("enable_memory") is False:
            settings["enabled"] = False
        if settings.get("recall_mode") is None:
            settings["recall_mode"] = self.valves.recall_mode
        if settings.get("recall_tags") is None:
            settings["recall_tags"] = self.valves.recall_tags
        if settings.get("bank_id") is None:
            settings["bank_id"] = self.valves.bank_id
        if settings.get("global_bank_id") is None:
            settings["global_bank_id"] = self.valves.global_bank_id
        if settings.get("bank_scope") is None:
            settings["bank_scope"] = self.valves.bank_scope
        return settings

    def _resolve_bank_id(self, settings: dict, __metadata__: Optional[dict]) -> str:
        scope = settings.get("bank_scope", "global")
        bank_id = settings.get("bank_id") or "open-webui"
        global_bank_id = settings.get("global_bank_id") or bank_id
        prefix = self._clean_id(settings.get("bank_prefix", "open-webui"), "open-webui")
        user_raw = ( __metadata__ or {}).get("user_id") or (( __metadata__ or {}).get("user") or {}).get("id") or "anonymous"
        chat_raw = ( __metadata__ or {}).get("chat_id") or ( __metadata__ or {}).get("session_id") or "session"
        user_id = self._clean_id(str(user_raw), "anonymous")
        chat_id = self._clean_id(str(chat_raw), "session")

        if scope == "manual":
            return self._clean_id(bank_id, "open-webui-manual")
        if scope == "user":
            return f"{prefix}-user-{user_id}"
        if scope == "chat":
            return f"{prefix}-chat-{chat_id}"
        return self._clean_id(global_bank_id, "open-webui")

    def _make_client(self, settings: dict) -> HindsightHTTPClient:
        return HindsightHTTPClient(
            base_url=settings["base_url"],
            api_key=settings["api_key"],
            timeout_seconds=settings.get("timeout_seconds", 20),
        )

    def _bank_config_payload(self, settings: dict) -> dict:
        reasoning = settings.get("reasoning_level", "low")
        cap = settings.get("reasoning_level_cap", "medium")
        reflect_mission = settings.get("reflect_mission", "")
        retain_mission = settings.get("retain_mission", "")
        if reasoning:
            reflect_mission = f"{reflect_mission}\n\nReasoning level: {reasoning}.".strip()
            retain_mission = f"{retain_mission}\n\nReasoning level: {reasoning}.".strip()
        if cap:
            reflect_mission = f"{reflect_mission}\nReasoning level cap: {cap}.".strip()

        payload = {
            "reflect_mission": reflect_mission,
            "retain_mission": retain_mission,
            "retain_extraction_mode": settings.get("retain_extraction_mode"),
            "retain_custom_instructions": settings.get("retain_custom_instructions") or None,
            "retain_chunk_size": settings.get("retain_chunk_size"),
            "enable_observations": settings.get("enable_observations"),
            "observations_mission": settings.get("observations_mission") or None,
        }
        return {k: v for k, v in payload.items() if v not in (None, "")}

    def _ensure_bank(self, client: HindsightHTTPClient, bank_id: str, settings: dict):
        if not settings.get("auto_create_bank", True):
            return
        cache_key = f"{settings.get('base_url')}::{bank_id}"
        now = time.time()
        with self._lock:
            last = self._bank_cache.get(cache_key)
            if last and now - last < 300:
                return
        payload = self._bank_config_payload(settings)
        try:
            client.request("PUT", f"/v1/default/banks/{urllib.parse.quote(bank_id, safe='')}", body=payload)
            with self._lock:
                self._bank_cache[cache_key] = now
        except Exception as e:
            # Best effort: bank config API may be absent or restricted.
            self._log(f"bank ensure skipped for {bank_id}: {e}")

    def _get_last_user_message(self, messages: List[dict]) -> str:
        for msg in reversed(messages or []):
            if msg.get("role") == "user":
                return self._normalize_text(msg.get("content"))
        return ""

    def _get_last_assistant_message(self, messages: List[dict]) -> str:
        for msg in reversed(messages or []):
            if msg.get("role") == "assistant":
                return self._normalize_text(msg.get("content"))
        return ""

    def _get_latest_messages_text(self, messages: List[dict], limit: int = 4) -> str:
        chunks = []
        for msg in (messages or [])[-limit:]:
            role = msg.get("role", "unknown")
            content = self._normalize_text(msg.get("content"))
            if content:
                chunks.append(f"{role}: {content}")
        return "\n".join(chunks)

    def _should_skip_task(self, __task__: Optional[str]) -> bool:
        if not __task__:
            return False
        return __task__ in {
            "title_generation",
            "tags_generation",
            "emoji_generation",
            "query_generation",
            "image_prompt_generation",
            "autocomplete_generation",
            "moa_response_generation",
        }

    def _is_skip_marker_present(self, text: str) -> bool:
        lowered = text.lower()
        return any(marker in lowered for marker in ("#nomem", "#skip", "hindsight:skip"))

    def _query_too_long(self, text: str, settings: dict) -> bool:
        return self._approx_token_count(text) > max(1, int(settings.get("recall_query_max_tokens", 400)))

    def _trim_text(self, text: str, max_chars: int) -> str:
        if len(text) <= max_chars:
            return text
        return text[: max_chars - 30] + "\n...[truncated]..."

    def _build_recall_query(self, user_text: str, messages: List[dict], settings: dict) -> str:
        user_text = (user_text or "").strip()
        if not user_text:
            return ""

        max_tokens = max(1, int(settings.get("recall_query_max_tokens", 400)))
        context_turns = max(0, int(settings.get("recall_query_context_turns", 2)))
        context = self._get_latest_messages_text(messages[:-1] if messages else [], limit=context_turns).strip()
        if not context:
            return self._trim_text_to_tokens(user_text, max_tokens)

        prefix_tokens = self._approx_token_count("Conversation context:\n\nCurrent user request:\n")
        user_budget = max(1, max_tokens - prefix_tokens)
        if self._approx_token_count(user_text) > user_budget:
            user_text = self._trim_text_to_tokens(user_text, user_budget)

        remaining = max_tokens - prefix_tokens - self._approx_token_count(user_text)
        if remaining <= 0:
            return user_text

        context = self._trim_text_to_tokens(context, remaining)
        query = f"Conversation context:\n{context}\n\nCurrent user request:\n{user_text}"
        if self._query_too_long(query, settings):
            return self._trim_text_to_tokens(query, max_tokens)
        return query

    def _format_recall_results(self, response: Any, settings: dict) -> str:
        if isinstance(response, str):
            return response.strip()
        results = response.get("results") if isinstance(response, dict) else None
        if not results:
            return ""

        rendered = []
        limit = max(1, int(settings.get("max_recall_results", 8)))
        for idx, item in enumerate(results[:limit], start=1):
            if not isinstance(item, dict):
                continue
            text = self._normalize_text(item.get("text") or item.get("content") or item.get("label"))
            if not text:
                continue
            mem_type = item.get("type") or item.get("memory_type") or "memory"
            context = self._normalize_text(item.get("context"))
            tag_text = []
            if mem_type:
                tag_text.append(str(mem_type))
            if context:
                tag_text.append(context)
            header = f"[{idx}]"
            if tag_text:
                header += f" ({' | '.join(tag_text)})"
            rendered.append(f"{header} {text}")

        text = "\n".join(rendered).strip()
        max_chars = max(200, int(settings.get("max_recall_chars", 6000)))
        return self._trim_text(text, max_chars)

    def _build_memory_context(self, recall_text: str, reflect_text: str, settings: dict) -> str:
        sections = []
        if settings.get("indicators_in_context"):
            sections.append("[Hindsight memory enabled]")
        if recall_text:
            sections.append("Relevant long-term memories:\n" + recall_text)
        if reflect_text:
            sections.append("Synthesized memory insight:\n" + reflect_text.strip())
        return "\n\n".join(sections).strip()

    def _recall_memories(self, client: HindsightHTTPClient, bank_id: str, query: str, settings: dict):
        payload = {
            "query": query,
            "types": self._split_csv(settings.get("recall_types", "world,experience,observation")),
            "budget": settings.get("search_budget", "mid"),
            "max_tokens": max(256, int(settings.get("context_tokens", 1200)) * 2),
            "tags": self._split_csv(settings.get("recall_tags", "")) or None,
            "tags_match": settings.get("recall_tags_match", "any"),
            "trace": False,
        }
        payload = {k: v for k, v in payload.items() if v not in (None, [], "")}
        return client.request("POST", f"/v1/default/banks/{urllib.parse.quote(bank_id, safe='')}/memories/recall", body=payload)

    def _reflect_memories(self, client: HindsightHTTPClient, bank_id: str, query: str, settings: dict):
        payload = {
            "query": query,
            "budget": settings.get("reflect_budget", "low"),
            "max_tokens": max(512, int(settings.get("context_tokens", 1200)) * 2),
            "tags": self._split_csv(settings.get("recall_tags", "")) or None,
            "tags_match": settings.get("recall_tags_match", "any"),
            "fact_types": self._split_csv(settings.get("recall_types", "world,experience,observation")) or None,
        }
        payload = {k: v for k, v in payload.items() if v not in (None, [], "")}
        result = client.request("POST", f"/v1/default/banks/{urllib.parse.quote(bank_id, safe='')}/reflect", body=payload)
        if isinstance(result, dict):
            return self._normalize_text(result.get("text") or "")
        return self._normalize_text(result)

    def _package_retain_content(self, user_text: str, assistant_text: str, messages: List[dict], settings: dict) -> str:
        context = self._get_latest_messages_text(messages[:-2] if len(messages) >= 2 else messages, limit=4)
        parts = []
        if context:
            parts.append(f"Conversation context:\n{context}")
        if user_text:
            parts.append(f"User: {user_text}")
        if assistant_text:
            parts.append(f"Assistant: {assistant_text}")
        combined = "\n\n".join(parts).strip()
        return self._trim_text(combined, max(500, int(settings.get("max_message_chars", 25000))))

    def _retain_turn(self, client: HindsightHTTPClient, bank_id: str, content: str, settings: dict, metadata: dict):
        if not content.strip():
            return None
        document_id = "-".join(
            [
                self._clean_id(bank_id, "bank"),
                self._clean_id(str(metadata.get("chat_id") or metadata.get("session_id") or "session"), "session"),
                self._clean_id(str(metadata.get("message_id") or int(time.time() * 1000)), "turn"),
            ]
        )
        payload = {
            "async": bool(settings.get("retain_async", True)),
            "items": [
                {
                    "content": content,
                    "context": metadata.get("interface") or "open-webui",
                    "document_id": document_id,
                }
            ],
        }
        return client.request("POST", f"/v1/default/banks/{urllib.parse.quote(bank_id, safe='')}/memories", body=payload)

    async def inlet(
        self,
        body: dict,
        __user__: Optional[dict] = None,
        __metadata__: Optional[dict] = None,
        __event_emitter__=None,
        __task__: Optional[str] = None,
        **kwargs,
    ) -> dict:
        settings = self._effective_settings(__user__, __metadata__)
        if not settings.get("enabled", True):
            return body
        if self._should_skip_task(__task__):
            return body

        messages = copy.deepcopy(body.get("messages") or [])
        user_text = self._get_last_user_message(messages)
        if not user_text.strip():
            return body
        if self._is_skip_marker_present(user_text):
            return body

        bank_id = self._resolve_bank_id(settings, __metadata__)
        client = self._make_client(settings)
        if settings.get("auto_create_bank", True):
            await asyncio.to_thread(self._ensure_bank, client, bank_id, settings)

        reflect_mode = settings.get("reflect_mode", "smart")

        # Recall refresh gating.
        chat_key = str((__metadata__ or {}).get("chat_id") or ( __metadata__ or {}).get("session_id") or bank_id)
        now = time.time()
        with self._lock:
            state = self._chat_state.setdefault(chat_key, {"turns": 0, "last_recall_turn": -999, "last_recall_at": 0.0, "last_reflect_turn": -999, "recall_text": "", "reflect_text": ""})
            state["turns"] += 1
            current_turn = state["turns"]

        recall_mode = settings.get("recall_mode", "hybrid")
        should_recall = recall_mode != "off"
        if should_recall:
            if settings.get("injection_frequency", "every-turn") == "first-turn" and current_turn > 1:
                should_recall = False
            if current_turn - state["last_recall_turn"] < max(1, int(settings.get("context_cadence", 1))):
                should_recall = False
            if now - state["last_recall_at"] < max(0, int(settings.get("context_refresh_ttl_seconds", 300))):
                # TTL only avoids refresh if we already have recall text cached.
                should_recall = should_recall and bool(state.get("recall_text"))
            if current_turn - state["last_recall_turn"] >= max(1, int(settings.get("context_refresh_message_threshold", 8))):
                should_recall = should_recall or True

        recall_text = state.get("recall_text", "")
        reflect_text = state.get("reflect_text", "")
        if should_recall:
            queries = self._extract_recall_queries(user_text, messages, settings)
            if not queries:
                self._log("recall skipped: empty query after extraction")
            else:
                raw_query = queries[0]
                if self._query_too_long(raw_query, settings):
                    behavior = settings.get("recall_long_query_behavior", "truncate")
                    if behavior == "skip":
                        self._log("recall skipped: query too long")
                        queries = []
                    else:
                        truncated = self._trim_text_to_tokens(raw_query, max(1, int(settings.get("recall_query_max_tokens", 400))))
                        self._log(f"recall query trimmed from {self._approx_token_count(raw_query)} to {self._approx_token_count(truncated)} tokens")
                        queries[0] = truncated

            if queries:
                if settings.get("show_recall_indicator", True):
                    await self._emit(__event_emitter__, "Searching Hindsight memory…", False)

                recall_response = None
                recall_text = ""
                reflect_text = ""
                recall_count = 0
                seen_result_ids = set()
                merged_results = []

                for idx, query in enumerate(queries, start=1):
                    if idx > 1 and settings.get("logging", True):
                        self._log(f"recall query {idx}/{len(queries)}: {query}")
                    response = await asyncio.to_thread(self._recall_memories, client, bank_id, query, settings)
                    if recall_response is None:
                        recall_response = response
                    if isinstance(response, dict):
                        results = response.get("results")
                        if isinstance(results, list):
                            for item in results:
                                if not isinstance(item, dict):
                                    continue
                                rid = self._normalize_text(item.get("id") or item.get("memory_id") or item.get("chunk_id") or item.get("text"))
                                if rid and rid in seen_result_ids:
                                    continue
                                if rid:
                                    seen_result_ids.add(rid)
                                merged_results.append(item)

                if isinstance(recall_response, dict):
                    recall_response = dict(recall_response)
                    recall_response["results"] = merged_results
                    recall_count = len(merged_results)
                elif recall_response is None:
                    recall_response = {"results": merged_results}
                    recall_count = len(merged_results)

                recall_text = self._format_recall_results(recall_response, settings)

                should_reflect = False
                if reflect_mode == "always":
                    should_reflect = True
                elif reflect_mode == "smart":
                    should_reflect = (
                        recall_mode == "hybrid"
                        and recall_count >= 5
                        and (current_turn == 1 or current_turn - state.get("last_reflect_turn", -999) >= max(4, int(settings.get("context_refresh_message_threshold", 8))))
                    )
                if should_reflect:
                    reflect_query = f"Given the user request and recalled memories, summarize what matters most for future turns.\n\nUser request: {user_text}\n\nRecalled memories:\n{recall_text or 'None'}"
                    if settings.get("show_recall_indicator", True):
                        await self._emit(__event_emitter__, "Synthesizing Hindsight memory…", False)
                    reflect_text = await asyncio.to_thread(self._reflect_memories, client, bank_id, reflect_query, settings)
                with self._lock:
                    state["recall_text"] = recall_text
                    state["reflect_text"] = reflect_text
                    state["last_recall_at"] = time.time()
                    state["last_recall_turn"] = current_turn
                    if reflect_text:
                        state["last_reflect_turn"] = current_turn

                memory_context = self._build_memory_context(recall_text, reflect_text, settings)
                if memory_context:
                    system_message = {"role": "system", "content": memory_context}
                    insert_at = 0
                    for idx, msg in enumerate(messages):
                        if msg.get("role") != "system":
                            insert_at = idx
                            break
                        insert_at = idx + 1
                    messages.insert(insert_at, system_message)
                    body["messages"] = messages
                    body.setdefault("metadata", {})
                    body["metadata"]["hindsight_memory_injected"] = True

                if settings.get("show_recall_indicator", True):
                    await self._emit(__event_emitter__, "Hindsight memories injected.", True)

        # Stash state for outlet retention.
        if __metadata__ is not None:
            __metadata__["hindsight"] = {
                "bank_id": bank_id,
                "user_text": user_text,
                "turn": state.get("turns", 0),
                "recall_mode": recall_mode,
            }
        return body

    async def outlet(
        self,
        body: dict,
        __user__: Optional[dict] = None,
        __metadata__: Optional[dict] = None,
        __event_emitter__=None,
        **kwargs,
    ) -> dict:
        settings = self._effective_settings(__user__, __metadata__)
        if not settings.get("enabled", True) or not settings.get("save_messages", True):
            return body

        metadata_hindsight = ( __metadata__ or {}).get("hindsight") or {}
        bank_id = metadata_hindsight.get("bank_id") or self._resolve_bank_id(settings, __metadata__)
        client = self._make_client(settings)
        if settings.get("auto_create_bank", True):
            await asyncio.to_thread(self._ensure_bank, client, bank_id, settings)

        messages = copy.deepcopy(body.get("messages") or [])
        user_text = metadata_hindsight.get("user_text") or self._get_last_user_message(messages)
        assistant_text = self._get_last_assistant_message(messages) or self._normalize_text(body.get("content") or body.get("message") or body.get("response"))
        if not user_text.strip() or not assistant_text.strip():
            return body
        if self._is_skip_marker_present(user_text):
            return body

        content = self._package_retain_content(user_text, assistant_text, messages, settings)
        if not content.strip():
            return body

        metadata = {
            "chat_id": ( __metadata__ or {}).get("chat_id"),
            "session_id": ( __metadata__ or {}).get("session_id"),
            "message_id": ( __metadata__ or {}).get("message_id"),
            "interface": ( __metadata__ or {}).get("interface"),
        }
        if settings.get("show_retain_indicator", True):
            await self._emit(__event_emitter__, "Saving turn to Hindsight…", False)

        try:
            await asyncio.to_thread(self._retain_turn, client, bank_id, content, settings, metadata)
            if settings.get("show_retain_indicator", True):
                await self._emit(__event_emitter__, "Hindsight memory saved.", True)
        except Exception as e:
            self._log(f"retain failed: {e}")
            if settings.get("show_retain_indicator", True):
                await self._emit(__event_emitter__, f"Hindsight retain failed: {e}", True)
        return body