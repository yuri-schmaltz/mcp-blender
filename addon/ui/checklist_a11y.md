# checklist_a11y.md - Checklist de acessibilidade para UI BlenderMCP

## WCAG mínimo obrigatório

- [ ] Contraste mínimo 4.5:1 para texto normal
- [ ] Labels claros e descritivos em todos os campos/botões
- [ ] Navegação por teclado (tab/foco visível)
- [ ] Feedback visual para estados (hover, active, disabled)
- [ ] Mensagens de erro claras e acionáveis
- [ ] Uso de ARIA quando necessário
- [ ] Tamanho de fonte mínimo 12px
- [ ] Não depender apenas de cor para transmitir informação
- [ ] Elementos interativos com área mínima de 44x44px

## Como validar

1. Revise cada tela/componente usando o checklist acima.
2. Use ferramentas como [axe](https://www.deque.com/axe/) ou [WAVE](https://wave.webaim.org/) para validação automática.
3. Teste navegação por teclado (tab/shift+tab, foco visível).
4. Verifique contraste usando [WebAIM Contrast Checker](https://webaim.org/resources/contrastchecker/).
5. Documente exceções e planos de ajuste.

> Atualize este checklist a cada alteração relevante na UI.
