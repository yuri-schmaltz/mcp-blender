# Repository Review

This document captures a quick structural and quality review of the BlenderMCP project, highlighting potential robustness and usability gaps.

## Project layout
- **Root**: entry script (`addon.py`), CLI entrypoint (`main.py`), and packaging metadata (`pyproject.toml`).
- **Python package**: core MCP server logic in `src/blender_mcp/server.py`; no dedicated test suite found.
- **Assets**: supporting files in `assets/`; no documentation on their usage.

## Findings and recommended improvements

### 1) Packaging metadata and distribution readiness
- `pyproject.toml` still ships placeholder author/contact information and generic URLs, which can confuse users and marketplaces. Consider populating authoritative maintainer data, homepage, and issue tracker links.
- The project lacks release automation/CI to publish or validate distributions; adding a minimal workflow (lint, build, package integrity) would prevent broken releases.

### 2) MCP server robustness and validation gaps
- In `generate_hyper3d_model_via_images`, URL validation mistakenly references `input_image_paths` even when URLs are provided, leading to a `TypeError` before any request is sent. Switching the check to `input_image_urls` and covering the branch with tests would prevent crashes.
- Several commands (e.g., screenshot capture, PolyHaven downloads) assume filesystem operations succeed but do not surface clear recovery steps; lightweight retries and user-facing guidance would improve resilience.

### 3) Observability and error handling
- Logging is configured at module import and mixes user-facing messages with diagnostics. Introducing structured logger initialization (configurable level/handlers) and standard error envelopes for tool responses would help MCP clients surface actionable feedback.

### 4) Documentation depth and onboarding
- The README is extensive for client integrations but lacks a concise "architecture and data flow" section showing how the Blender addon communicates with the MCP server and where to configure environment variables.
- There is no contributor guide or quickstart for running the server without Blender (e.g., mocked responses), which slows community contributions and debugging.

### 5) Testing strategy
- No automated tests or fixtures are present. Adding a minimal suite (unit tests for command formatting, bbox processing, URL validation, and mocked socket interactions) plus a smoke test for CLI startup would protect future changes.

## Task backlog
1. **Fix Hyper3D URL validation**: Correct `input_image_urls` validation in `generate_hyper3d_model_via_images` and add a regression test that covers both path and URL inputs.
2. **Harden IO paths**: Add defensive checks and clearer failure messages around temporary file creation and downloads (screenshot capture, PolyHaven/Sketchfab assets), including cleanup guarantees.
3. **Logging configuration**: Centralize logger setup (configurable level, optional JSON/structured output) and standardize error payloads returned to MCP clients.
4. **Packaging metadata refresh**: Update `pyproject.toml` with real maintainer info, homepage, and issue URLs; add packaging build validation in CI.
5. **Architecture and contributor docs**: Add an architecture overview diagram/section to README plus a CONTRIBUTING guide with local dev setup, mocked Blender guidance, and testing instructions.
6. **Test harness**: Introduce a basic automated test suite for the MCP server utilities (bbox processing, URL/path validation, command formatting) and a CLI smoke test; wire it into CI.
