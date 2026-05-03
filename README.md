# hindsight-memory-for-open-webui

This repository contains a **single Open WebUI Filter function** that integrates Hindsight for long-term memory.

- [Open WebUI](https://github.com/open-webui/open-webui) — extensible, self-hosted AI interface
- [Hindsight](https://github.com/vectorize-io/hindsight) — agent memory that learns over time

## What it does

- Reuses **Hindsight recall** to inject relevant memories before the model sees the prompt
- Reuses **Hindsight retain** to persist the user/assistant turn after the assistant responds
- Exposes admin-configurable settings in Open WebUI's function valves panel
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
   - any recall/reflect tuning options you want to override

## Recommended defaults

The function defaults are tuned for a practical starting point:

- `bank_scope = global`
- `bank_id = open-webui`
- `recall_mode = hybrid`
- `reflect_mode = smart`
- `search_budget = mid`
- `reflect_budget = low`
- `context_tokens = 1200`
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

1. Builds a recall query from the latest user message and recent conversation context
2. Calls Hindsight recall
3. Calls Hindsight reflect only when recall is sufficiently rich and the turn is due for synthesis
4. Injects a system message with the retrieved memory context

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
