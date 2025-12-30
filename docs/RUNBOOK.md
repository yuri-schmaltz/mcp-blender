# Runbook Operacional - BlenderMCP

## 1. Setup e Inicialização
- Instale dependências: `pip install -r requirements.txt`
- Para rodar o add-on: execute `addon.py` dentro do Blender ou via CLI para debug.
- Para rodar o servidor MCP: `python src/blender_mcp/cli.py`

## 2. Troubleshooting
- Verifique logs em caso de erro (logs estruturados em `logs/` ou stdout).
- Use `python -m unittest discover -s tests` para rodar todos os testes.
- Para problemas de cache: rode `AssetCache.clear()` via Python shell.
- Para problemas de conexão: valide portas e firewall (default 9876).

## 3. Fluxos Críticos
- Inicialização do add-on e conexão MCP.
- Execução de comandos via CLI ou socket.
- Manipulação de arquivos temporários.

## 4. Checklist de Release
- Todos os testes (unitários, E2E) passando.
- Checklist de acessibilidade revisado.
- Logs presentes nos fluxos críticos.
- Documentação atualizada (README, ADR, runbook).
- Pipeline CI/CD verde.

## 5. Referências
- [docs/ARCHITECTURE.md](ARCHITECTURE.md)
- [docs/ADR-0001-estrutura-modular.md](ADR-0001-estrutura-modular.md)
- [addon/ui/checklist_a11y.md](../addon/ui/checklist_a11y.md)
- [docs/baseline_metrics.md](baseline_metrics.md)
- [docs/troubleshooting.md](troubleshooting.md)

> Atualize este runbook a cada mudança relevante de arquitetura, fluxo ou operação.
