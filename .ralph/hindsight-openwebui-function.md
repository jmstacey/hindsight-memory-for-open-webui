# Hindsight Open WebUI Function

Implement a single Open WebUI **Filter** function that integrates the Hindsight memory system for long-term recall and retention across conversations.

## Goals
- Implement a single Open WebUI function only.
- Provide admin-configurable settings for Hindsight server connection, API bearer key, bank/scoping strategy, recall/reflect thinking levels, and related defaults.
- Use the standard Hindsight HTTP API.
- Support both memory recall before assistant generation and memory retention after assistant generation.
- Default to a global databank, while allowing the user/admin to change scoping.
- Use defaults inspired by hindsight-pi where applicable.
- Include install/config guidance and testing notes.

## Checklist
- [x] Design the function architecture and state model.
- [x] Implement Hindsight API client helpers with stdlib HTTP.
- [x] Implement Open WebUI Filter with valves and lifecycle hooks.
- [x] Inject recalled memories into the prompt safely.
- [x] Retain conversation memories safely after responses.
- [x] Add bank resolution/scoping options and sane defaults.
- [x] Add docs: install/config guide and testing notes.
- [x] Verify code for obvious API mismatches and summarize assumptions.

## Verification
- Open WebUI function docs and Hindsight API docs reviewed.
- hindsight-pi config defaults reviewed for reference.
- `python3 -m py_compile hindsight_openwebui_filter.py` ✅
- Files updated:
  - `hindsight_openwebui_filter.py`
  - `README.md`

## Notes
- Implemented as a single Open WebUI Filter function.
- Uses bearer auth to the standard Hindsight HTTP API.
- Defaults are set for a global databank, with user/chat/manual scoping options.
- Recall occurs in `inlet()`, retention occurs in `outlet()`.
- Added a Docker-host networking fallback so `localhost` can transparently try `host.docker.internal` when appropriate.
- Bank auto-creation/configuration is best-effort.
- Reflect is now configurable via `reflect_mode` (`smart` default, plus `always` and `never`).
- Default reflect behavior remains Hindsight-aligned (`smart`): only synthesize when recall is rich enough and the turn is due.
- README cleaned up and renamed conceptually to the GitHub repo name `hindsight-memory-for-open-webui`; removed stale guide-file references and kept attribution/caveats plus About / Support details.
- Increased the HTTP timeout to 90s because Hindsight reflect can take ~20-30s in the provided logs.
- No Open WebUI runtime smoke test was possible in this environment.
