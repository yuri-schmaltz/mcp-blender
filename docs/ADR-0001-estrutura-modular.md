# ADR-0001: Estrutura Modular e Convenções Iniciais

## Contexto
O projeto BlenderMCP adota uma arquitetura modular, separando responsabilidades em módulos de add-on, CLI, utilitários, UI e testes. O objetivo é facilitar manutenção, evolução incremental e robustez.

## Decisão
- Manter separação clara entre add-on (Blender), src/blender_mcp (núcleo/CLI), utils, UI e testes.
- Utilizar logging estruturado (via logging Python) em todos os fluxos críticos.
- Adotar tokens mínimos para UI (ver `addon/ui/tokens.py`).
- Checklist de acessibilidade obrigatório para toda UI (ver `addon/ui/checklist_a11y.md`).
- Testes unitários obrigatórios para novos módulos; E2E/integrados para fluxos críticos.
- Documentação de arquitetura e runbooks obrigatória para novos fluxos.


## Consequências
- Facilita onboarding e troubleshooting (ver docs/troubleshooting.md).
- Reduz risco de regressão e divergência arquitetural.
- Permite evolução incremental sem grandes rupturas.
- Garante baseline de métricas e acessibilidade (ver docs/baseline_metrics.md e addon/ui/checklist_a11y.md).

## Referências
- [docs/ARCHITECTURE.md](ARCHITECTURE.md)
- [addon/ui/tokens.py](../addon/ui/tokens.py)
- [addon/ui/checklist_a11y.md](../addon/ui/checklist_a11y.md)

---

# Convenções Mínimas

- Nomes de módulos e funções em snake_case.
- Classes em PascalCase.
- Funções públicas com docstring.
- Logging obrigatório em handlers, servidores e operações críticas.
- Testes em `tests/` com prefixo `test_`.
- Documentação de decisões em `docs/`.
