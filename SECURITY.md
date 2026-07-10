# Security Policy

## Threat Model

`blender-mcp` ships a **socket server inside the Blender process** and a
**FastMCP server** that connects to it. Read this section before exposing
either component.

### What we protect against

- **Accidental payload flood.** A malformed or buggy MCP tool call that
  sends gigabytes of JSON. Mitigated by `BLENDER_MCP_MAX_PAYLOAD_BYTES`
  (default 4 MiB).
- **Sandbox escape attempts in `execute_blender_code`.** Mitigated by an
  import allow/deny list and per-call timeout (`BLENDER_MCP_CODE_TIMEOUT`).
- **Resource exhaustion.** Mitigated by per-connection rate limit
  (`BLENDER_MCP_RATE_LIMIT_CALLS`/`_WINDOW`) and the circuit breaker.

### What we do **not** protect against

- **Plain-text transport.** Commands travel as JSON over TCP without TLS.
  Any actor with access to the loopback interface can read commands.
- **Untrusted LLM.** `execute_blender_code` is intentionally a `bpy` REPL;
  a prompt-injected or compromised LLM can do anything Blender's Python
  API allows (delete files inside `BLENDER_MCP_CACHE_DIR`, install
  addons, etc.).
- **Listening on public interfaces.** Binding to `0.0.0.0` exposes the
  socket to the network. We refuse to do that unless
  `BLENDER_MCP_ALLOW_PUBLIC_BIND=1` is set.
- **A malicious Blender extension.** The addon runs inside Blender with
  full `bpy` and filesystem privileges.

### Recommended deployment

1. Keep `BLENDER_HOST=127.0.0.1` (default).
2. Run the MCP server and Blender on the **same host**, under a single user.
3. Set `BLENDER_MCP_TOKEN` to a random secret if you ever cross a trust
   boundary (containers, VMs, multi-user host).
4. Treat `execute_blender_code` as **root-equivalent for the user that
   launched Blender**. Don't point it at untrusted prompts.

## Supported Versions

| Version | Supported |
| ------- | --------- |
| 2.11.x  | ✅        |
| 2.10.x  | ✅        |
| 2.9.x   | ✅        |
| < 2.9   | ❌        |

Older versions may still work but won't receive security fixes.

## Reporting a Vulnerability

**Please do not file public issues for suspected vulnerabilities.**

Email `security@yuri-schmaltz.dev` (PGP key in
`.github/SECURITY_PGP.asc` when published) with:

1. Reproduction steps or a minimal test
2. Affected version (`uv run blender-mcp --version`)
3. Component: MCP server / addon / CLI / GUI / docs

We aim to acknowledge within **3 business days** and triage within **10**.
Critical fixes ship in a patch release with a CVE when applicable.

## Hardening checklist

- [ ] `BLENDER_HOST` is `localhost` or `127.0.0.1`
- [ ] Firewall blocks the MCP port from non-loopback
- [ ] `BLENDER_MCP_LOG_LEVEL=INFO` (not `DEBUG`) in production
- [ ] No third-party MCP client runs as root
- [ ] LLM provider is trusted / self-hosted
- [ ] `BLENDER_MCP_CACHE_DIR` is on a disk with disk-usage monitoring
