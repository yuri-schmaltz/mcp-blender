# Marco 01 - Diagnostico e Patch Incremental

Data: 2026-02-12

Atualizacao: os itens marcados como `NÃO VERIFICADO` neste marco foram revalidados e fechados em `docs/MARCOS_02_04_CONCLUSAO.md`.

## 1. Diagnostico com evidencias

1. Fluxos MCP criticos estao implementados no servidor:
`src/blender_mcp/server.py:412`, `src/blender_mcp/server.py:425`, `src/blender_mcp/server.py:443`, `src/blender_mcp/server.py:483`, `src/blender_mcp/server.py:532`, `src/blender_mcp/server.py:581`, `src/blender_mcp/server.py:658`, `src/blender_mcp/server.py:796`, `src/blender_mcp/server.py:898`, `src/blender_mcp/server.py:1058`, `src/blender_mcp/server.py:1101`.
`addon.py:305`, `addon.py:315`, `addon.py:324`, `addon.py:1914`, `addon.py:1916`, `addon.py:1923`.
3. Governanca de a11y existe em checklist e design system:
`addon/ui/checklist_a11y.md:1`, `addon/ui/checklist_a11y.md:12`, `docs/design_system.md:17`, `docs/design_system.md:23`.
4. Risco de regressao em i18n/GUI identificado: destino de log dependia de texto exibido do combo.
Evidencias antes do patch: `src/blender_mcp/gui.py:164`, `src/blender_mcp/gui.py:323` (estado anterior, nao mais vigente).
5. `NÃO VERIFICADO`: validacao pixel-perfect em viewport Blender e screenshots reais de UI Blender.
Como validar: executar Blender em `C:\Blender\blender.exe`, abrir addon, capturar viewport e painel MCP por resolucao (100%, 125%, 150% DPI no Windows).

## 2. Propostas incrementais (maximo 2 por topico)

Topico: persistencia segura do destino de log na GUI

1. Opcao A (recomendada): armazenar valor canonico no `QComboBox` (`console`/`file`) via `itemData`.
Impacto: baixo risco, reversivel, evita regressao de traducao.
2. Opcao B: manter texto da UI e normalizar por mapa string->valor em cada `save/apply`.
Impacto: maior risco de drift entre UI e persistencia.

Decisao: Opcao A.

Topico: previsibilidade de estado da GUI

1. Opcao A (recomendada): atualizar resumo de ambiente em tempo real a cada alteracao de campo.
Impacto: reduz friccao e erro humano sem alterar fluxo principal.
2. Opcao B: manter atualizacao apenas em `apply/reset`.
Impacto: menor feedback e maior chance de configuracao incorreta.

Decisao: Opcao A.

## 3. Patches aplicados (pequenos, colaveis, reversiveis)

1. GUI com valor canonico de handler:
`src/blender_mcp/gui.py:173`, `src/blender_mcp/gui.py:174`, `src/blender_mcp/gui.py:175`, `src/blender_mcp/gui.py:320`, `src/blender_mcp/gui.py:342`.
2. GUI com summary em tempo real para host/porta/log-level/format/handler/log-file:
`src/blender_mcp/gui.py:135`, `src/blender_mcp/gui.py:146`, `src/blender_mcp/gui.py:157`, `src/blender_mcp/gui.py:164`, `src/blender_mcp/gui.py:178`, `src/blender_mcp/gui.py:186`.
3. Acessibilidade de campos e botoes por `accessibleName`:
`src/blender_mcp/gui.py:133`, `src/blender_mcp/gui.py:143`, `src/blender_mcp/gui.py:151`, `src/blender_mcp/gui.py:162`, `src/blender_mcp/gui.py:172`, `src/blender_mcp/gui.py:184`, `src/blender_mcp/gui.py:188`, `src/blender_mcp/gui.py:201`, `src/blender_mcp/gui.py:204`, `src/blender_mcp/gui.py:207`.
4. Teste de regressao para traducao/rotulo de handler:
`tests/test_gui.py:71`.

## 4. Validacao executada neste marco

1. Teste executado: `pytest tests/test_gui.py -q`.
2. Resultado: `NÃO VERIFICADO` funcionalmente por dependencia ausente (`ModuleNotFoundError: No module named 'PySide6'`).
3. Como validar: instalar extra GUI (`uv pip install '.[gui]'`) e reexecutar `pytest tests/test_gui.py -q`.

## 5. Roadmap incremental (proximo)

1. Marco 02: adicionar smoke test automatizado para Blender real (headless) com `C:\Blender\blender.exe`.
2. Marco 03: checklist de regressao visual com baseline de screenshots para painel MCP.
3. Marco 04: ampliar diagnosticos (latencia por comando MCP e taxa de erro por handler) com relatorio no runbook.

## 6. Backlog priorizado (impacto x risco x esforco)

1. P0: pipeline de teste GUI com dependencias opcionais instaladas no CI para evitar falso negativo de coleta.
2. P0: smoke E2E com Blender real no Windows para validar import/export e contexto de cena.
3. P1: padronizar estados de UI (loading/disabled/error/success) com criterios de aceitacao por componente.
4. P1: baseline de regressao visual (screenshot diff) para painel MCP.
5. P2: consolidar metricas de UX/performance no `docs/baseline_metrics.md`.

## 7. Metricas e checklists objetivos

1. UX: tempo para aplicar configuracao < 10s; taxa de erro de conexao por host/porta.
2. A11y: 100% dos campos acionaveis por teclado e com identificacao semantica (`accessibleName`).
3. Regressao visual: 0 diferencas criticas no painel MCP entre releases (baseline aprovado).
4. Performance percebida: feedback visual de acao em < 200ms no clique de teste de conexao.
5. Integracao MCP: smoke de `get_scene_info` e `execute_blender_code` passando em ambiente com addon ativo.
