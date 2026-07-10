# Transport hardening + Blender 4.x compatibility

This PR lands three layers of change on top of the v2.11.0 baseline:

1. **Transport hardening** — opt-in token auth, hard payload cap, and
   refusal to bind on a non-loopback address without explicit consent.
2. **End-to-end test infrastructure** — Blender 4.2.13 LTS is downloaded
   once and spun up in `--background` mode, then the real socket server
   is exercised. CI can opt in with `BLENDER_EXE=/path/to/blender`.
3. **Blender 3.5+ compatibility fixes** — two bugs surfaced when the
   e2e harness was brought up; both are fixed here with defensive
   fallbacks.

Everything is opt-in via environment variables, the existing
single-user loopback setup keeps working, and no protocol break.

---

## What changed

### Security (opt-in, defaults are unchanged)

- `BLENDER_MCP_TOKEN` — when set, the addon refuses every command
  whose `X-BlenderMCP-Token` header does not match. The MCP server
  attaches the header automatically; the addon enforces it.
  Comparison is `hmac.compare_digest` (constant-time).
- `BLENDER_MCP_MAX_PAYLOAD_BYTES` (default 4 MiB) — addon rejects
  commands larger than the cap *before* JSON parsing, protecting
  Blender from runaway clients.
- `BLENDER_MCP_ALLOW_PUBLIC_BIND=1` (or `--allow-public-bind`) —
  required to bind to a non-loopback address. Refused by default.

### CLI

- `--version` — prints the package version and exits.
- `--check-config` — validates `BLENDER_HOST`, `BLENDER_PORT`,
  `BLENDER_MCP_MAX_PAYLOAD_BYTES`, and `BLENDER_MCP_TOKEN`. Exits 1
  on invalid configuration.
- `--allow-public-bind` — explicit opt-in for binding to a public
  interface. Without it, the CLI exits 2 with a clear error.
- `--doctor` — section-prefixed output (`[OK]`, `[WARN]`, `[FAIL]`)
  with python/platform/cwd/token info appended.

### Fixes

- `addon/handlers/scene_tools.py::get_scene_info` no longer crashes
  on Blender 3.5+ (`scene.objects.active` was removed). A new
  `_active_object_name(scene)` helper prefers
  `bpy.context.view_layer.objects.active` and falls back to the
  legacy attribute.
- `__init__.py::BlenderMCPPreferences.bl_idname` is now resolved
  via a three-step fallback (`__package__` → `blender_manifest.toml`
  `id` → directory name of `__init__.py`). This fixes the
  `preferences is None` issue under legacy flat installs.

### Documentation / DX

- `CHANGELOG.md` — new, follows Keep a Changelog.
- `PLAN.md` — the roadmap that drove this PR, marked complete.
- `SECURITY.md` — rewritten with a concrete threat model and a
  hardening checklist.
- `.github/ISSUE_TEMPLATE/bug.yml`, `feature.yml`.
- `.pre-commit-config.yaml` — ruff + format + fast pytest gate.
- `pyproject.toml` — fixed broken `modelcontextprotocol/...` URLs,
  added `Yuri Schmaltz` to authors, kept `Upstream` URL pointing at
  the canonical `ahujasid/blender-mcp`.
- `.env.example` — every env var the project actually reads,
  including the new ones.

---

## Testing

| | Before | After |
|---|--:|--:|
| Unit (Blender not required) | 134 passed, 3 skipped | **165 passed, 3 skipped** |
| E2E (Blender 5.1.2 real) | n/a | **3 passed in ~30 s** |
| Lint on new/modified files | n/a | ruff clean |

The e2e tests are skipped automatically when `BLENDER_EXE` is not set:

```bash
# Quick (no Blender)
uv run pytest --ignore=tests/e2e

# Full (Blender 5.1.2 on PATH or BLENDER_EXE pointing to it)
BLENDER_EXE=/opt/blender-5.1.2-linux-x64/blender uv run pytest
```

What the e2e harness exercises against a real Blender process:

1. `connect` + `ping_thread` + `execute_code` round-trip.
2. Token enforcement with both `BLENDER_MCP_TOKEN` set and unset.
3. Payload cap of 2 KiB rejecting an 8 KiB JSON command.
4. Default 4 MiB cap rejecting a 5 MiB JSON command.

The harness lives in `tests/e2e/`:

- `headless_runner.py` — installs the addon, enables it, sets
  `allow_code_execution`, pumps `bpy.app.timers` inline, and starts
  the socket server.
- `smoke_security.py` — the 5-check smoke client.
- `test_headless_round_trip.py` — the pytest orchestrator with three
  scenarios.

---

## Risk and rollback

- All security features are opt-in. Single-user loopback setups
  (the default) behave exactly as before.
- The two bug fixes are backwards-compatible — `view_layer.objects`
  exists in every supported Blender, the legacy attribute is still
  the fallback.
- Rolling back this PR removes the new env-vars, the docs, and the
  test files. No production code path is changed when the new env
  vars are unset.

---

## Out of scope / follow-ups

- WASM-based sandbox for `execute_code` (multi-week effort).
- Migration to MCP Streamable HTTP (depends on upstream roadmap).
- Bundling a `.zip` extension in CI (the e2e harness already
  exercises the install path).
- The 2 pre-existing `except:` blocks in `scene_tools.py` are left
  alone — out of scope for this PR.

---

## Reviewer notes

- The shared safety helpers live in
  `src/blender_mcp/security/transport.py` and the sister
  `addon/utils/transport_safety.py`. The two are kept in sync
  intentionally (the addon runs in Blender's interpreter, the MCP
  server runs outside).
- The handler for the "what changed in scene_info" path is small and
  self-contained — start with `_active_object_name` in
  `addon/handlers/scene_tools.py` if you only have 5 minutes.
- The CLI changes are additive. `python -m blender_mcp --version`
  is the safest entry point for a smoke check.
