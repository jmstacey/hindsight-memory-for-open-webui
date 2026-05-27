# hindsight-memory-for-open-webui

This repository contains a **single Open WebUI Filter function** that integrates Hindsight for long-term memory.

- [Open WebUI](https://github.com/open-webui/open-webui) — extensible, self-hosted AI interface
- [Hindsight](https://github.com/vectorize-io/hindsight) — agent memory that learns over time

> **Tip: You can set up Open WebUI using the Hindsight MCP server.** Hindsight ships a built-in MCP server and you can connect Hindsight directly as an MCP server and get recall/retain/reflect as native tools without a separate function. This filter is a direct integration that bypasses the MCP layer (which is becoming less of a differentiator as context windows grow and MCP support becomes standard).

## What it does

- Reuses **Hindsight recall** to inject relevant memories before the model sees the prompt
- Reuses **Hindsight retain** to persist the user/assistant turn after the assistant responds
- Uses an extractive, multi-query recall rewrite pipeline to keep recall requests under Hindsight's 500-token limit
- Strips fenced code blocks and skips malformed recall queries so code snippets do not trigger empty-word recall errors
- Exposes admin-configurable settings in Open WebUI's function valves panel
- Is toggleable per chat in Open WebUI's Integrations menu when enabled as a filter
- Supports memory scoping by:
  - global databank (default)
  - per-user databank
  - per-chat databank
  - manual databank override

## Features

- **Biomimetic long-term memory**: Hindsight provides durable recall and retention instead of a short chat-only context window.
- **Cross-agent memory sharing**: the same Hindsight memory setup can be shared with other agents and clients, such as **Pi**, **Claude**, and others, so your memory doesn’t have to live inside only one app.
- **Open WebUI native**: runs as a single Open WebUI function with admin-configurable settings.
- **Flexible scoping**: choose global, user, chat, or manual databank isolation.

## Files

- `hindsight_openwebui_filter.py` — Open WebUI function code
- `README.md` — install/config/testing notes, attribution, and caveats

## Install

1. Open **Open WebUI → Admin Panel → Functions**.
2. Create a new **Filter** function.
3. Paste the contents of `hindsight_openwebui_filter.py`.
4. Save the function.
5. Open the function settings and configure:
   - `base_url` — Hindsight server URL, for example `http://host.docker.internal:8888`
   - If Open WebUI is running in Docker and Hindsight is running on your host machine, `host.docker.internal` is usually the right address. If that does not work in your environment, use your host LAN IP instead.
   - `api_key` — Hindsight bearer token
   - `bank_scope` — `global`, `user`, `chat`, or `manual`
   - `bank_id` — databank to use when `bank_scope=global` or `manual`
   - `reflect_mode` — `smart`, `always`, or `never`
   - `recall_query_max_tokens` — maximum size for each recall query fragment (default `400`)
   - `recall_query_behavior` — `truncate` (default) or `multi`; `truncate` sends one hard-capped query, `multi` preserves the legacy fan-out behavior
   - `recall_query_max_queries` — max number of query variants generated from one prompt when `recall_query_behavior=multi` (default `4`)
   - `recall_query_context_turns` — how many recent turns to use when extracting recall anchors (default `1`)
   - any other recall/reflect tuning options you want to override
6. In each model's settings, add this filter to the model's Filters list and choose whether it should be enabled by default in **Default Filters**.
   - When enabled as a toggleable filter, users can switch it on or off per chat from the message box **Integrations** menu.

## Recommended defaults

The function defaults are tuned for a practical starting point:

- `bank_scope = global`
- `bank_id = open-webui`
- `recall_mode = hybrid`
- `reflect_mode = smart`
- `search_budget = mid`
- `reflect_budget = low`
- `context_tokens = 1200`
- `recall_query_max_tokens = 400`
- `recall_query_behavior = truncate`
- `recall_query_max_queries = 4`
- `recall_query_context_turns = 1`
- `context_refresh_ttl_seconds = 300`
- `context_refresh_message_threshold = 8`
- `context_cadence = 1`
- `injection_frequency = every-turn`
- `retain_async = true`
- `auto_create_bank = true`
- `save_messages = true`
- `timeout_seconds = 90`

## Hindsight API compatibility

The function uses the standard Hindsight HTTP API:

- `POST /v1/default/banks/{bank_id}/memories/recall`
- `POST /v1/default/banks/{bank_id}/reflect`
- `POST /v1/default/banks/{bank_id}/memories`
- `PUT /v1/default/banks/{bank_id}` when auto-creating/configuring a bank

Authorization is sent as:

- `Authorization: Bearer <api_key>`

### Recall

On each eligible user turn, the function:

1. Strips fenced code blocks from the prompt before query extraction so code samples do not dominate recall
2. Extracts memory-relevant query anchors from the latest user message and a small amount of recent context
3. Generates up to a few compact recall query variants so long prompts can still fit Hindsight's 500-token cap
4. Skips recall entirely if extraction leaves no searchable terms
5. Calls Hindsight recall for each extracted query and merges/dedupes the results
6. Calls Hindsight reflect only when recall is sufficiently rich and the turn is due for synthesis
7. Injects a system message with the retrieved memory context

### Retain

After the assistant response, the function:

1. Collects the latest user and assistant messages
2. Packages them into a turn summary
3. Sends them to Hindsight retain

### Skip markers

If the user message contains any of these markers, the turn will skip memory write/recall:

- `#nomem`
- `#skip`
- `hindsight:skip`

## Testing notes

### 1. Connectivity test

Use a known-good Hindsight server and confirm the function can reach it:

- `base_url` points to the API root, e.g. `http://localhost:8888`
- `api_key` is valid
- Hindsight server health endpoint responds

### 2. Recall test

1. Start a chat.
2. Ask the assistant to remember a fact such as:
   - “My favorite color is blue.”
3. Send a follow-up message:
   - “What is my favorite color?”
4. Confirm the recalled memory is injected and the answer uses it.
5. Try a long, multi-topic prompt and verify the filter extracts compact recall queries instead of sending the full prompt to Hindsight.

### 3. Retain test

1. Say something persistent and distinctive.
2. Check the Hindsight bank for a new retained memory.
3. Verify the retained content contains the conversation turn.

### 4. Scope test

Try switching `bank_scope`:

- `global` — all chats share the same databank
- `user` — each user gets their own databank
- `chat` — each chat gets its own databank
- `manual` — explicit bank ID is used

### 5. Disable test

Set `enabled = false` and verify that:

- no recall is injected
- no retain request is sent
- chat behavior returns to normal

## Notes and caveats

- Open WebUI filter `outlet()` behavior can vary depending on request path and deployment mode.
- If you rely heavily on direct API integrations, test the function carefully in your exact Open WebUI version.
- The Hindsight bank auto-creation step is best-effort; some deployments may restrict bank config updates.
- Recall queries are rewritten extractively, not summarized conversationally, to preserve entities, dates, and technical terms.
- Fenced code blocks are removed before extraction so prompts that are mostly code or markdown do not produce invalid recall queries.

## Assumptions

- Hindsight accepts bearer-authenticated HTTP requests.
- Hindsight recall/reflect endpoints return JSON and retain accepts batch-style memory payloads.
- Open WebUI passes `messages`, `__user__`, `__metadata__`, and `__event_emitter__` into Filter hooks in the documented way.

## Attribution and caveats

- This function was authored by **Jon Stacey**: [https://JonStacey.com](https://JonStacey.com)
- Hindsight project: [GitHub repository](https://github.com/vectorize-io/hindsight)
- License: **MIT**.
- It has **not been extensively tested**.
- It was built and used in a **single-user Open WebUI configuration**; multi-user and production deployments may require additional validation and adjustment.
