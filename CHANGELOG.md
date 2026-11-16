# Changelog

## 1.2.0 — fork maintenance

Forked from `Sophomoresty/gemini-web2api` at `2bb988b` (v1.1.0).

### Added
- `gemini_web2api/bl.py`: build-label (`bl`) discovery from
  `gemini.google.com/app` (`WIZ_global_data.cfb2h`, with bundle fallback),
  cached for `bl_cache_sec`. `gemini_bl: "auto"` is the new default.
- `GET /healthz` (also `/health`): version, uptime, auth mode, resolved build
  label with source/age, default model, model list.
- Custom models via `models` in `config.json`, exposed through `/v1/models`
  and the Google native model list.
- `scripts/smoke.py`: end-to-end check (health + chat + stream) against a
  running server.

### Changed
- `HTTP 400/403/413` or `BardErrorInfo` from upstream now invalidates the
  cached build label and retries instead of failing the request.
- A canned upstream rejection (*"I seem to be encountering an error"*) is
  detected, retried, and surfaced as an error — previously it was returned to
  clients as the model's answer.
- Streaming failures end the SSE stream with an `error` frame and `[DONE]`
  instead of truncating silently.
- Startup banner prints the resolved build label and its origin.
- Version bumped to 1.2.0.

### Notes
- Pinning `gemini_bl` to a literal value disables discovery; the refresh on
  `400` then re-resolves to the same pinned label. Use `"auto"` unless you need
  to freeze an upstream build.
- `gemini_web2api.py` (standalone) and `cloudflare/worker.js` still carry their
  own copies of the protocol code and were **not** updated in this release.
