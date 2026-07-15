# Changelog

All notable changes to this project are documented here. The format is
loosely based on [Keep a Changelog](https://keepachangelog.com/) and the
project follows [Semantic Versioning](https://semver.org/) where
practical.

## [Unreleased]

Nothing yet.

## [2.12.1] — 2026-07-15

**Security patch.** Bumps de lower-bound em dependências para fechar
15 das 29 vulnerabilidades reportadas pelo Dependabot. Sem mudança de
código, sem breaking change. 165/165 testes passando.

### Security (resolved via dep bumps)

- **`requests>=2.32.4`** — fecha `.netrc` credentials leak
  ([GHSA-9hjg-9r4m-mvj7](https://github.com/advisories/GHSA-9hjg-9r4m-mvj7))
  e outras 7 moderate. Resolve: 8 vulnerabilidades.
- **`mcp[cli]>=1.23.0,<2.0.0`** — fecha DNS rebinding protection que
  não vinha habilitada por default
  ([GHSA-9h52-p55h-vw2f](https://github.com/advisories/GHSA-9h52-p55h-vw2f))
  e mais 2 high/DoS. Resolve: 3 vulnerabilidades.
- **`pytest>=9.0.3`** — fecha vulnerable tmpdir handling
  ([GHSA-6w46-j5rx-g56g](https://github.com/advisories/GHSA-6w46-j5rx-g56g)).
  Resolve: 1 vulnerabilidade.
- **`black>=26.3.1`** — fecha arbitrary file write via unsanitized
  cache filename
  ([GHSA-3936-cmfr-pm3m](https://github.com/advisories/GHSA-3936-cmfr-pm3m))
  e mais 2 moderate. Resolve: 3 vulnerabilidades.

### Deferred

- **`litellm>=1.84.0`** — 15 vulnerabilidades restantes (3 high em auth
  bypass, várias em SSTI/RCE) ficam para `v2.13.0`. É um salto de 92
  minor versions com mudanças de API; vai como release dedicado.

### Notes

- Sem mudança de código, sem mudança de protocolo
- 165/165 unit tests passando após o bump
- Ver `DEPENDABOT_TRIAGE.md` no repo para análise completa

[2.12.1]: https://github.com/yuri-schmaltz/mcp-blender/compare/v2.12.0...v2.12.1

## [2.12.0] — 2026-07-15

**Hardening release.** All changes are opt-in via environment
variables; single-user loopback setups behave exactly as before. No
protocol break.

### Security
- **Token authentication** on the socket protocol: when
  `BLENDER_MCP_TOKEN` is set, the addon rejects every command whose
  `X-BlenderMCP-Token` header does not match (constant-time
  comparison). Both sides opt in together; no breaking change for
  existing single-user loopback setups.
- **Hard payload cap** (`BLENDER_MCP_MAX_PAYLOAD_BYTES`, default 4 MiB):
  the addon refuses commands larger than the cap, protecting Blender
  from runaway clients. The cap is enforced on the wire *before* JSON
  parsing.
- **Public-bind guard**: the CLI refuses to bind to a non-loopback
  address unless `BLENDER_MCP_ALLOW_PUBLIC_BIND=1` (or the matching
  `--allow-public-bind` flag) is set. Refused by default.

### Fixed
- `addon/handlers/scene_tools.py::get_scene_info` no longer crashes on
  Blender 3.5+: the removed `scene.objects.active` is replaced with a
  defensive helper that prefers the modern
  `bpy.context.view_layer.objects.active` and falls back to the legacy
  attribute when needed.
- `__init__.py::BlenderMCPPreferences.bl_idname` is now resolved via a
  three-step fallback (`__package__` → `blender_manifest.toml` `id` →
  directory name of `__init__.py`). Resolves the
  `preferences is None` issue under legacy flat installs.

### Added
- New CLI flags: `--version`, `--check-config`, `--allow-public-bind`,
  and a section-prefixed `--doctor` (`[OK]`, `[WARN]`, `[FAIL]`).
- `PLAN.md` documenting the hardening roadmap and the rationale for
  each change.
- `SECURITY.md` rewritten with a concrete threat model and a
  hardening checklist.
- `.github/ISSUE_TEMPLATE/bug.yml` and `feature.yml`.
- `.pre-commit-config.yaml` with ruff, format, and a fast pytest gate.
- `tests/unit/test_transport_safety.py` (15 tests) and
  `tests/unit/test_addon_transport_safety.py` (8 tests) for the
  shared safety helpers.
- `tests/unit/test_upstream_bug_fixes.py` (7 tests) for the two
  Blender 4.x compat fixes.
- `tests/e2e/headless_runner.py`, `smoke_security.py`, and
  `test_headless_round_trip.py` exercising the new hardening against
  a real Blender 5.1.2 process. The harness transparently handles
  the user-addons path change (4.x uses ``scripts/addons``,
  5.0+ uses ``scripts/addons/modules``) and the renamed
  ``addon_utils.enable`` keyword.

### Changed
- `pyproject.toml`: fixed broken `modelcontextprotocol/...` URLs,
  added `Yuri Schmaltz` to the `authors` list, kept `Upstream` URL
  pointing at the canonical `ahujasid/blender-mcp`.
- `.env.example`: documented every env var the project actually reads,
  with new entries for the hardening knobs.

## [2.11.0] — Upstream baseline

Inherited from `ahujasid/blender-mcp` v2.11.0. See upstream CHANGELOG
for the full list of features inherited unchanged.

[2.12.0]: https://github.com/yuri-schmaltz/mcp-blender/compare/v2.11.0...v2.12.0
[2.11.0]: https://github.com/yuri-schmaltz/mcp-blender/releases/tag/v2.11.0
