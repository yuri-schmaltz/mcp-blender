# baseline_metrics.md - Como medir e monitorar baseline

## 1. Logs
- Ative logging em modo INFO/DEBUG para capturar eventos críticos.
- Verifique logs de: server_start, client_connected, command_executor_error, response_send_error, etc.

## 2. Métricas
- Use o objeto `metrics` (addon/utils/metrics.py) para consultar contadores e tempos.
- Chame `metrics.report()` no final de execuções ou via endpoint/debug para obter snapshot.

## 3. Checklist de validação
- Todos os fluxos críticos geram logs e métricas.
- Métricas de erro e latência são monitoradas a cada release.
- Ajuste thresholds e alertas conforme maturidade.

> Atualize este documento conforme novas métricas forem instrumentadas.
