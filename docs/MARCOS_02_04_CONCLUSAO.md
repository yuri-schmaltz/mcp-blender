# Marcos 02-04 - Conclusao Incremental

Data: 2026-02-12

## Marco 02 - Smoke E2E com Blender real (Windows)

Status: concluido.

### Implementacao
1. Bootstrap Blender dedicado para teste de integracao real:
`tests/e2e/blender_smoke_bootstrap.py:1`.
2. Teste E2E substituido para usar `C:\Blender\blender.exe` e socket MCP:
`tests/test_e2e_addon_server.py:1`.
3. Validacao funcional de comandos criticos:
- `get_scene_info`
- `execute_code`
Evidencias: `tests/test_e2e_addon_server.py:93`, `tests/test_e2e_addon_server.py:98`.

### Resultado medido
1. Execucao: `pytest tests/test_e2e_addon_server.py -q`
2. Resultado observado: `1 passed` (ambiente local atual).

## Marco 03 - Baseline de regressao visual

Status: concluido e validado.

### Implementacao
1. Teste visual com screenshot do `ConfigWindow` e comparacao por diff de pixels:
`tests/visual/test_gui_visual_regression.py:1`.
2. Threshold de regressao definido: <= 2% de diferenca de pixels.
Evidencia: `tests/visual/test_gui_visual_regression.py:66`.
3. Suporte a update de baseline:
`BLENDER_MCP_UPDATE_BASELINE=1`.
Evidencia: `tests/visual/test_gui_visual_regression.py:47`.

### Estado no ambiente atual
1. Dependencia `PySide6` instalada e validada.
2. Baseline inicial versionado em:
`assets/baseline/gui_config_window.png`.
3. Testes GUI e visual executados com sucesso.

## Marco 04 - Diagnosticos e observabilidade

Status: concluido e expandido com percentis.

### Implementacao
1. Tool MCP de diagnostico:
`get_mcp_diagnostics`.
Evidencia: `src/blender_mcp/server.py:796`.
2. Instrumentacao de latencia/sucesso/erro em screenshot e busca Sketchfab consolidada:
`src/blender_mcp/server.py:452`, `src/blender_mcp/server.py:841`.
3. Percentis `p50` e `p95` adicionados ao report de metricas:
`src/blender_mcp/perf_metrics.py:13`.
3. Testes unitarios cobrindo cenarios:
- conexao indisponivel
- probe de cena bem-sucedido
Evidencias: `tests/test_server.py:268`, `tests/test_server.py:283`.
4. Teste unitario dedicado de percentis:
`tests/unit/test_perf_metrics.py:1`.

### Resultado medido
1. Execucao: `pytest tests/test_server.py -q`
2. Resultado observado: `8 passed` (`tests/test_server.py`) e `1 passed` (`tests/unit/test_perf_metrics.py`).

## Risco de regressao e rollback

1. Mudancas isoladas em arquivos de teste e servidor MCP sem remoção de features.
2. Rollback simples por commit revert nas alteracoes abaixo:
- `tests/e2e/blender_smoke_bootstrap.py`
- `tests/test_e2e_addon_server.py`
- `tests/visual/test_gui_visual_regression.py`
- `src/blender_mcp/server.py`
- `tests/test_server.py`

## Backlog residual (priorizado)

Nenhum item pendente do plano original.

## Fase adicional concluida

1. CI com job dedicado de smoke E2E em Windows com instalacao de Blender e deteccao automatica do executavel.
Evidencia: `.github/workflows/ci.yml` job `windows-blender-e2e`.
