# baseline_metrics.md - Como medir e monitorar baseline

## 1. Logs
- Ative logging em modo INFO/DEBUG para capturar eventos críticos.
- Verifique logs de: server_start, client_connected, command_executor_error, response_send_error, etc.
- Para smoke E2E real, valide no output do Blender a sequência de bootstrap e conexão socket.

## 2. Métricas
- Use o objeto `metrics` (addon/utils/metrics.py) para consultar contadores e tempos.
- Chame `metrics.report()` no final de execuções ou via endpoint/debug para obter snapshot.
- Use o tool MCP `get_mcp_diagnostics()` para snapshot auditável de:
  - `perf_metrics` (contadores e latências do servidor MCP)
  - estado de conectividade Blender (`reachable`, erro, host/porta)
  - probe mínimo de cena (`object_count`, `materials_count`) quando conectado.

## 3. Baselines recomendados (antes/depois)
- Conectividade:
  - taxa de sucesso do smoke E2E com Blender real (`tests/test_e2e_addon_server.py`) >= 95% em runs locais.
- Performance percebida:
  - `viewport_screenshot_latency` e `sketchfab_search_latency` acompanhadas por release.
- Regressão visual:
  - diferença de pixels <= 2% no teste visual quando baseline existir.

## 4. Checklist de validação
- Todos os fluxos críticos geram logs e métricas.
- Métricas de erro e latência são monitoradas a cada release.
- Ajuste thresholds e alertas conforme maturidade.
- Em caso de falha de dependência opcional de GUI (PySide6), registrar como `NÃO VERIFICADO` e manter skip explícito de teste.

> Atualize este documento conforme novas métricas forem instrumentadas.
