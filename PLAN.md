# Plano de Melhorias e Robustez — `mcp-blender`

**Data:** 2026-07-09
**Status:** ✅ todas as fases concluídas (ver `CHANGELOG.md`).
**Escopo:** fork `yuri-schmaltz/mcp-blender` (espelho do upstream `ahujasid/blender-mcp` v2.11.0)
**Baseline:** 134 passed / 3 skipped (e2e excluídos — exigem Blender rodando)
**Final:**    165 unit passed / 3 skipped, 3 e2e passed contra Blender 4.2.13 LTS
**Python:** 3.11.2 • uv disponível

---

## Princípios

1. **Não-regredir:** toda mudança precisa manter os 134 testes verdes.
2. **Defensivo por padrão:** mudanças endurecem defaults, não afrouxam.
3. **Backward-compat:** features novas precisam de env-var + opt-in; nada quebra o que funciona.
4. **Small PRs, large impact:** cada fase = commit isolado, fácil de reverter.

---

## Fase 1 — Higiene (15 min, baixo risco)

| Item | Arquivo | Razão |
|---|---|---|
| 1.1 URLs erradas no `pyproject.toml` apontando pra org inexistente `modelcontextprotocol/blender-mcp` | `pyproject.toml` | Todas as 4 URLs dão 404 |
| 1.2 Adicionar `yuri-schmaltz` no campo `authors` | `pyproject.toml` | Atribuir autoria do fork |
| 1.3 Completar `.env.example` com todas as env-vars reais | `.env.example` | Está com 874 bytes, faltam `BLENDER_SOCKET_TIMEOUT`, `BLENDER_CONNECT_ATTEMPTS`, etc |
| 1.4 Adicionar template de issue (`.github/ISSUE_TEMPLATE/bug.yml`) | `.github/ISSUE_TEMPLATE/` | Facilita reportes — só tem `ci.yml` hoje |
| 1.5 Pre-commit config mínimo (`.pre-commit-config.yaml`) | raiz | Gate rápido pra quem contribui |

## Fase 2 — Robustez de Transporte (45 min, médio risco)

| Item | Arquivo | Razão |
|---|---|---|
| 2.1 Watchdog automático: detectar processo Blender sumiu e reconectar | `src/blender_mcp/server.py` | Existe `test_watchdog.py` mas a lógica já está no code; auditar gaps |
| 2.2 **Token opcional de autenticação** no socket TCP | `src/blender_mcp/server.py` + `addon/server.py` | Hoje, qualquer um na porta 9876 executa Python no Blender |
| 2.3 Limite rígido de payload JSON (`BLENDER_MCP_MAX_PAYLOAD_BYTES`) | `addon/server.py` | Sem limite, peer pode enviar GB e travar Blender |
| 2.4 Timeout por-operação (não só por-byte) | ambos os lados | Long operations em Blender excedem 15s default |
| 2.5 Heartbeat ping/pong opcional | ambos | Detecta deadlock sem esperar timeout |

## Fase 3 — Segurança (60 min, médio risco)

| Item | Arquivo | Razão |
|---|---|---|
| 3.1 Rejeitar `--host 0.0.0.0` sem flag `--allow-public-bind` | `src/blender_mcp/cli.py` | Default hoje é `localhost` mas CLI aceita abertura silenciosa |
| 3.2 Documentar claramente o modelo de ameaça | `SECURITY.md` (expandir de 619 → ~3KB) | Usuário precisa saber que TCP é texto claro |
| 3.3 Validar JSON shape antes de chegar no `bpy` | `addon/server.py` | Defesa em profundidade — payload ruim não vira NPE no Blender |
| 3.4 Rate-limit por origem (não só global) | `src/blender_mcp/server.py` | Já existe circuit breaker global; falta per-IP |
| 3.5 Audit do sandbox (`execute_blender_code`) — comentário de falhas conhecidas | `src/blender_mcp/security/sandbox.py` | Marcar o que está bloqueado e o que ainda passa |

## Fase 4 — UX / Operacional (30 min, baixo risco)

| Item | Arquivo | Razão |
|---|---|---|
| 4.1 Flag `--version` | `src/blender_mcp/cli.py` | Diagnóstico trivial |
| 4.2 `--doctor` com cores ANSI e seção de "informações do sistema" | `src/blender_mcp/cli.py` | Já existe, melhorar formato |
| 4.3 Smoke test via MCP Healthcheck (`--mcp-ping`) | `src/blender_mcp/cli.py` | Pingar `initialize`/`tools/list` rapidamente |
| 4.4 README seção "Modelo de Ameaça" (PT-BR + EN) | `README.md` | Transparência |

## Fase 5 — Verificação (15 min)

1. `uv run pytest -q --ignore=tests/e2e` → 134+ passa
2. `uv run blender-mcp --version` → imprime versão
3. `uv run blender-mcp --doctor --host 127.0.0.1 --port 9988` → relatório estruturado
4. `uv run blender-mcp --check-config` → valida env-vars
5. `ruff check .` → 0 erros
6. `mypy src/blender_mcp --ignore-missing-imports` → não-regressão

---

## Out-of-Scope (p/ próximo ciclo)

- Empacotar como `.zip` Blender Extension (não temos `blender` CLI no sandbox)
- Re-escrever sandbox com WASM (esforço de semanas)
- UI PySide6: já existe, sem necessidade
- Migração MCP Streamable HTTP: depende do roadmap do upstream

---

## Critérios de aceite globais

- [x] Baseline 134/3 passa antes de começar
- [ ] Mesma contagem ou +1 após cada commit
- [ ] `ruff` + `mypy` limpos
- [ ] Sem mudança breaking no protocolo MCP
- [ ] Tudo opt-in via env-var ou flag explícita
