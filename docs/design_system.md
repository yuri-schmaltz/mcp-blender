# design_system.md - Diretrizes iniciais para Design System BlenderMCP

## Objetivo
Garantir consistência visual, acessibilidade e facilidade de manutenção na UI do BlenderMCP.

## Tokens
- Definidos em `addon/ui/tokens.py` (cores, espaçamento, fontes)

## Componentes base
- Botão
- Input
- Painel
- Feedback visual (erro, sucesso, loading)

## Guidelines
- Sempre usar tokens para cor, espaçamento e fonte
- Seguir checklist de acessibilidade (`addon/ui/checklist_a11y.md`)
- Componentes devem ser reutilizáveis e documentados
- Feedback visual claro para todos os estados
- Não depender apenas de cor para transmitir informação

## Governança
- Toda alteração de UI deve passar pelo checklist de acessibilidade
- Atualizar tokens e documentação ao criar/alterar componentes
- Revisão de design a cada release

> Este documento deve evoluir conforme maturidade do produto e feedback dos usuários.
