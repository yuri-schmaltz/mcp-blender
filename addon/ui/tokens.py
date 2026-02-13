# tokens.py - Tokens mínimos para UI/UX e acessibilidade
# Adicione e utilize estes tokens para garantir consistência visual e facilitar ajustes futuros.

COLORS = {
    "primary": "#1976D2",
    "secondary": "#424242",
    "background": "#FAFAFA",
    "error": "#D32F2F",
    "success": "#388E3C",
    "text": "#212121",
    "disabled": "#BDBDBD",
}

SPACING = {
    "xs": 4,
    "sm": 8,
    "md": 16,
    "lg": 24,
    "xl": 32,
}

FONT_SIZES = {
    "small": 10,
    "normal": 12,
    "large": 16,
}

# Checklist de acessibilidade (WCAG mínimo)
# - Contraste mínimo 4.5:1 para texto normal
# - Labels claros e descritivos
# - Navegação por teclado (tab/foco)
# - Feedback visual para estados (hover, active, disabled)
# - Mensagens de erro claras
# - Uso de ARIA quando necessário
# - Tamanho de fonte mínimo 12px
# - Não depender apenas de cor para transmitir informação
# - Elementos interativos com área mínima de 44x44px

# Para aplicar: utilize estes tokens nos componentes e revise o checklist a cada alteração de UI.
