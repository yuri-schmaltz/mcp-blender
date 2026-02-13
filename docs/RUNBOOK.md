# Runbook Operacional - BlenderMCP

## 1. Setup e Inicialização
- Instale dependências: `pip install -r requirements.txt`
- Para rodar o add-on: execute `addon.py` dentro do Blender ou via CLI para debug.
- Para rodar o servidor MCP: `python src/blender_mcp/cli.py`
- Blender Windows validado: `C:\Blender\blender.exe`

## 2. Troubleshooting
- Verifique logs em caso de erro (logs estruturados em `logs/` ou stdout).
- Use `python -m unittest discover -s tests` para rodar todos os testes.
- Para problemas de cache: rode `AssetCache.clear()` via Python shell.
- Para problemas de conexão: valide portas e firewall (default 9876).
- Para diagnóstico consolidado no servidor MCP, chame `get_mcp_diagnostics`.

## 3. Fluxos Críticos
- Inicialização do add-on e conexão MCP.
- Execução de comandos via CLI ou socket.
- Manipulação de arquivos temporários.
- Smoke real Blender + socket MCP: `pytest tests/test_e2e_addon_server.py -q`
- Regressão visual GUI (quando PySide6 disponível): `pytest tests/visual/test_gui_visual_regression.py -q`

## 4. Checklist de Release
- Todos os testes (unitários, E2E) passando.
- Checklist de acessibilidade revisado.
- Logs presentes nos fluxos críticos.
- Documentação atualizada (README, ADR, runbook).
- Pipeline CI/CD verde.
- Baseline visual atualizado quando houver mudança intencional de layout:
  - `set BLENDER_MCP_UPDATE_BASELINE=1`
  - `pytest tests/visual/test_gui_visual_regression.py -q`
  - remover variável e rodar novamente para validar diffs.

## 5. Referências
- [docs/ARCHITECTURE.md](ARCHITECTURE.md)
- [docs/ADR-0001-estrutura-modular.md](ADR-0001-estrutura-modular.md)
- [addon/ui/checklist_a11y.md](../addon/ui/checklist_a11y.md)
- [docs/baseline_metrics.md](baseline_metrics.md)
- [docs/troubleshooting.md](troubleshooting.md)
- [docs/MARCO_01_AUDITORIA.md](MARCO_01_AUDITORIA.md)
- [docs/MARCOS_02_04_CONCLUSAO.md](MARCOS_02_04_CONCLUSAO.md)

> Atualize este runbook a cada mudança relevante de arquitetura, fluxo ou operação.
