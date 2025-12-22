# Auditoria Completa UI/UX e Otimização - BlenderMCP

**Data:** 2025-12-22  
**Versão:** 1.2.1  
**Auditor:** Sistema de Análise Automatizada

---

## A) RESUMO EXECUTIVO

### Principais Riscos e Oportunidades

1. **🔴 ALTA - UI/UX**: Interface PySide6 carece de acessibilidade básica (navegação por teclado, foco visível, labels ARIA) - **Impacto: Usuários com deficiência visual não conseguem usar a aplicação**

2. **🔴 ALTA - Segurança**: Senhas em texto plano no painel Blender (API keys visíveis como StringProperty PASSWORD) sem criptografia - **Impacto: Exposição de credenciais em arquivos .blend**

3. **🟡 MÉDIA - Performance**: Addon.py monolítico (1885 linhas) com lógica misturada e ausência de async/await para I/O de rede - **Impacto: Bloqueio da UI do Blender durante downloads**

4. **🟡 MÉDIA - UX**: Mensagens de erro genéricas e falta de feedback visual durante operações longas (downloads, gerações 3D) - **Impacto: Usuários não sabem o estado da operação**

5. **🟡 MÉDIA - Confiabilidade**: Ausência de circuit breaker e rate limiting no cliente (apenas no servidor MCP) - **Impacto: Falhas em cascata quando APIs externas caem**

6. **🟢 BAIXA - Documentação**: README extenso mas falta arquitetura visual do painel Blender e fluxo UX - **Impacto: Onboarding lento para novos usuários**

7. **🟢 BAIXA - Testes**: Cobertura de testes baixa (~30% estimado) sem testes E2E ou de UI - **Impacto: Regressões não detectadas em fluxos críticos**

8. **🟢 BAIXA - Design System**: Ausência de tokens de design (spacing, cores, tipografia) no GUI PySide6 - **Impacto: Inconsistência visual e dificuldade de manutenção**

9. **🟢 BAIXA - Internacionalização**: GUI e addon misturados em português/inglês sem i18n - **Impacto: Experiência confusa para usuários internacionais**

10. **🟡 MÉDIA - Observabilidade**: Logs estruturados parcialmente implementados mas sem métricas (latência, taxa de erro, throughput) - **Impacto: Dificulta debugging em produção**

---

## B) ACHADOS DETALHADOS

### 1. UI/UX - Interface Gráfica (gui.py)

#### UX-01: Falta navegação por teclado consistente
**Severidade:** Alta | **Impacto:** Acessibilidade | **Esforço:** Pequeno

**Evidência:**
```python
# src/blender_mcp/gui.py: linhas 109-182
class ConfigWindow(QWidget):
    def _build_ui(self) -> None:
        layout = QVBoxLayout()
        form = QFormLayout()
        # Falta setTabOrder() para controlar sequência de foco
        # Falta atalhos de teclado (QShortcut) para ações comuns
```

**Problema:** Usuários não podem navegar entre campos com Tab de forma previsível. Botões não possuem atalhos (Alt+A para Aplicar, etc.).

**Recomendação:**
1. Adicionar `self.setTabOrder()` após criar todos os widgets
2. Configurar `QShortcut` para ações principais
3. Adicionar tooltips com indicação de atalhos

**Critério de aceite:**
- [ ] Tab navega sequencialmente: Host → Porta → Nível log → ... → Botões
- [ ] Esc fecha a janela
- [ ] Enter no último campo aciona "Aplicar"
- [ ] Foco visível em todos os widgets (contorno azul)

---

#### UX-02: Validação inline ausente
**Severidade:** Média | **Impacto:** UX/Eficiência | **Esforço:** Médio

**Evidência:**
```python
# src/blender_mcp/gui.py: linhas 189-210
def _apply_changes(self) -> None:
    is_valid, message = self._validate_inputs()
    if not is_valid:
        self._set_status(message, error=True)  # Apenas status, não destaca campo
        return
```

**Problema:** Validação ocorre só ao clicar "Aplicar". Usuário não vê qual campo está inválido até submeter.

**Recomendação:**
1. Conectar `textChanged`/`valueChanged` signals para validar em tempo real
2. Adicionar ícone de erro ao lado do campo inválido
3. Desabilitar botão "Aplicar" quando há erros
4. Mostrar mensagem explicativa abaixo do campo

**Exemplo:**
```python
self.host_edit.textChanged.connect(self._validate_host_field)

def _validate_host_field(self, text):
    if not text.strip():
        self.host_edit.setStyleSheet("border: 2px solid #d32f2f;")
        self.host_error_label.setText("⚠️ Host não pode ser vazio")
    else:
        self.host_edit.setStyleSheet("")
        self.host_error_label.setText("")
```

---

#### UX-03: Sem feedback durante teste de conexão
**Severidade:** Média | **Impacto:** UX/Clareza | **Esforço:** Pequeno

**Evidência:**
```python
# src/blender_mcp/gui.py: linhas 271-282
def _test_connection(self) -> None:
    # ...
    try:
        with socket.create_connection((host, port), timeout=1):
            self._set_status(f"Conexão bem-sucedida...")
    # Não há spinner/loading durante o teste
```

**Problema:** Botão "Testar conexão" não muda durante execução. Usuário não sabe se está processando.

**Recomendação:**
1. Desabilitar botão e mudar texto para "Testando..."
2. Adicionar spinner/progress indicator
3. Timeout visível (countdown: "Testando... 3s restantes")

---

#### A11Y-01: Contraste insuficiente em mensagens de status
**Severidade:** Alta | **Impacto:** Acessibilidade | **Esforço:** Pequeno

**Evidência:**
```python
# src/blender_mcp/gui.py: linhas 284-287
def _set_status(self, message: str, *, error: bool = False) -> None:
    color = "#d32f2f" if error else "#2e7d32"  # Vermelho e verde
    # Sem verificação de contraste mínimo WCAG AA (4.5:1)
```

**Problema:** Cores podem não ter contraste suficiente dependendo do tema do sistema.

**Recomendação:**
1. Usar palette do sistema: `QPalette.ColorRole.Text`
2. Adicionar ícones além de cor (❌ para erro, ✓ para sucesso)
3. Testar contraste com ferramenta WCAG

---

#### UI-01: Inconsistência visual (espaçamento e tamanhos)
**Severidade:** Baixa | **Impacto:** Consistência | **Esforço:** Pequeno

**Evidência:**
```python
# src/blender_mcp/gui.py: linhas 120-180
# Spacing hardcoded sem padrão
self.summary.setMinimumHeight(150)  # Por que 150?
window.resize(640, 420)  # Por que 640x420?
```

**Problema:** Valores "mágicos" sem justificativa. Layout pode quebrar com fontes maiores.

**Recomendação:**
1. Criar constantes de design:
```python
# constants.py
SPACING_SM = 8
SPACING_MD = 16
SPACING_LG = 24
MIN_WINDOW_WIDTH = 640
MIN_WINDOW_HEIGHT = 420
```

---

### 2. UI/UX - Blender Addon (addon.py)

#### UX-04: Labels em inglês/português misturados
**Severidade:** Baixa | **Impacto:** Clareza | **Esforço:** Médio

**Evidência:**
```python
# addon.py: linhas 1720-1748
bl_label = "Blender MCP"  # Inglês
layout.prop(scene, "blendermcp_use_polyhaven", text="Use assets from Poly Haven")  # Inglês
layout.operator("blendermcp.start_server", text="Connect to MCP server")  # Inglês
```

**Problema:** Toda UI em inglês, mas README em português. Público-alvo ambíguo.

**Recomendação:**
1. Implementar sistema i18n com `gettext` ou dict de strings
2. Detectar locale do Blender: `bpy.app.translations.locale`
3. Oferecer toggle manual de idioma no painel

---

#### UX-05: API Keys visíveis em texto plano
**Severidade:** Alta | **Impacto:** Segurança/UX | **Esforço:** Grande

**Evidência:**
```python
# addon.py: linhas 1835-1852
bpy.types.Scene.blendermcp_hyper3d_api_key = bpy.props.StringProperty(
    name="Hyper3D API Key",
    subtype="PASSWORD",  # Ofuscado na UI mas salvo em texto plano no .blend
    description="API Key provided by Hyper3D",
    default=""
)
```

**Problema:** `subtype="PASSWORD"` apenas oculta caracteres na UI. O valor é salvo em texto plano no arquivo .blend (arquivo JSON/binário sem criptografia).

**Recomendação:**
1. **Imediato:** Adicionar aviso na UI: "⚠️ API key será salva no arquivo .blend. Não compartilhe este arquivo."
2. **Médio prazo:** Usar keyring do SO (Windows Credential Manager, macOS Keychain, Linux libsecret)
3. **Alternativa:** Salvar em arquivo separado `~/.blender_mcp/credentials.enc` criptografado

---

#### UX-06: Sem feedback visual durante operações longas
**Severidade:** Média | **Impacto:** UX/Performance percebida | **Esforço:** Grande

**Evidência:**
```python
# addon.py: linhas 1093-1200 (download_polyhaven_asset)
# Linhas 1640-1700 (download_sketchfab_model)
# Não há progress bar, apenas print() no console
response = requests.get(download_url, timeout=60)  # 60 segundos sem feedback
```

**Problema:** Downloads grandes (modelos 3D, HDRIs) bloqueiam UI sem feedback. Usuário pensa que travou.

**Recomendação:**
1. Usar `requests` com streaming e callback de progresso:
```python
response = requests.get(url, stream=True, timeout=60)
total = int(response.headers.get('content-length', 0))
with open(path, 'wb') as f:
    downloaded = 0
    for chunk in response.iter_content(chunk_size=8192):
        f.write(chunk)
        downloaded += len(chunk)
        progress = downloaded / total * 100
        # Atualizar UI via bpy.app.timers ou threading
```

2. Adicionar modal popup com barra de progresso no Blender
3. Permitir cancelamento

---

#### A11Y-02: Falta de descrições acessíveis (tooltips)
**Severidade:** Média | **Impacto:** Acessibilidade | **Esforço:** Pequeno

**Evidência:**
```python
# addon.py: linhas 1731-1748
layout.prop(scene, "blendermcp_use_polyhaven", text="Use assets from Poly Haven")
# Sem description no prop, logo sem tooltip explicativo
```

**Recomendação:**
Adicionar `description` em todos os props:
```python
bpy.types.Scene.blendermcp_use_polyhaven = bpy.props.BoolProperty(
    name="Use Poly Haven",
    description="Enable downloading HDRIs, textures and 3D models from Poly Haven API. Requires internet connection.",
    default=False
)
```

---

### 3. Performance e Otimização

#### PERF-01: Addon monolítico (1885 linhas)
**Severidade:** Média | **Impacto:** Manutenibilidade | **Esforço:** Grande

**Evidência:**
```bash
# addon.py: 1885 linhas, 41 funções/classes
# Mistura: socket server, UI, handlers Poly Haven, Hyper3D, Sketchfab
```

**Problema:** Arquivo muito grande, dificulta navegação, testes e manutenção. Viola Single Responsibility Principle.

**Recomendação:**
Refatorar em módulos:
```
addon/
├── __init__.py          # Registro Blender
├── server.py            # BlenderMCPServer
├── handlers/
│   ├── scene.py         # get_scene_info, get_object_info
│   ├── polyhaven.py     # Poly Haven integration
│   ├── hyper3d.py       # Hyper3D integration
│   └── sketchfab.py     # Sketchfab integration
└── ui/
    ├── panel.py         # BLENDERMCP_PT_Panel
    └── operators.py     # Start/Stop/SetAPIKey operators
```

---

#### PERF-02: I/O síncrono bloqueia thread principal do Blender
**Severidade:** Alta | **Impacto:** Performance/UX | **Esforço:** Grande

**Evidência:**
```python
# addon.py: linhas 1093-1200
def download_polyhaven_asset(self, asset_id, ...):
    response = requests.get(api_url, headers=REQ_HEADERS, timeout=30)
    # Bloqueia thread principal por até 30 segundos
    file_response = requests.get(download_url, timeout=60)
    # Mais 60 segundos bloqueados
```

**Problema:** Todas as requisições HTTP são síncronas. Durante downloads, Blender fica "travado" (não responde a cliques, não renderiza).

**Recomendação:**
1. Mover I/O para thread separada:
```python
def download_polyhaven_asset(self, asset_id, ...):
    def download_worker():
        # ... código de download ...
        # Atualizar UI via bpy.app.timers no main thread
    
    thread = threading.Thread(target=download_worker, daemon=True)
    thread.start()
    return {"status": "downloading", "progress": 0}
```

2. Ou usar `asyncio` com `aiohttp` (requer mais refactoring)

---

#### PERF-03: Sem cache de assets baixados
**Severidade:** Baixa | **Impacto:** Performance/Custo | **Esforço:** Médio

**Evidência:**
```python
# addon.py: linhas 1170-1175
temp_dir = tempfile.mkdtemp()  # Sempre baixa novamente
# Cleanup: shutil.rmtree(temp_dir)  # Deleta após importar
```

**Problema:** Mesma textura/modelo baixado múltiplas vezes desperdiça banda e tempo.

**Recomendação:**
1. Criar cache persistente: `~/.blender_mcp/cache/`
2. Hash do asset_id como chave
3. TTL configurável (7 dias padrão)
4. Interface para limpar cache no painel

---

#### PERF-04: Serialização JSON grande sem paginação
**Severidade:** Baixa | **Impacto:** Performance | **Esforço:** Pequeno

**Evidência:**
```python
# addon.py: linhas 268-280
for i, obj in enumerate(bpy.context.scene.objects):
    if i >= 10:  # Limitado a 10 mas pode ter 1000s
        break
```

**Problema:** Cenas grandes (>1000 objetos) causam timeout ou crash ao serializar JSON.

**Recomendação:**
1. Implementar paginação: `get_scene_info(limit=10, offset=0)`
2. Retornar apenas objetos visíveis: `if obj.hide_get(): continue`
3. Lazy loading: retornar apenas nomes, detalhes sob demanda

---

### 4. Confiabilidade e Robustez

#### REL-01: Sem circuit breaker para APIs externas
**Severidade:** Média | **Impacto:** Confiabilidade | **Esforço:** Médio

**Evidência:**
```python
# addon.py: linhas 1100-1120
# Retry indefinido se API cair
response = requests.get(api_url, headers=REQ_HEADERS, timeout=30)
```

**Problema:** Se Poly Haven/Sketchfab/Hyper3D estiver down, cada request tenta por 30-60s. Múltiplas tentativas causam cascata de timeouts.

**Recomendação:**
Implementar circuit breaker pattern:
```python
class CircuitBreaker:
    def __init__(self, failure_threshold=5, timeout=60):
        self.failure_count = 0
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    
    def call(self, func):
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.timeout:
                self.state = "HALF_OPEN"
            else:
                raise Exception("Circuit breaker is OPEN")
        
        try:
            result = func()
            self.failure_count = 0
            self.state = "CLOSED"
            return result
        except Exception as e:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.failure_count >= self.failure_threshold:
                self.state = "OPEN"
            raise
```

---

#### REL-02: Tratamento de erro genérico
**Severidade:** Média | **Impacto:** UX/Debugging | **Esforço:** Médio

**Evidência:**
```python
# addon.py: linhas 1710-1716
except Exception as e:
    import traceback
    traceback.print_exc()  # Console apenas, usuário não vê
    return {"error": f"Failed to download model: {str(e)}"}
```

**Problema:** Mensagens genéricas não ajudam usuário a resolver. Ex: "Failed to download model: [Errno 11001] getaddrinfo failed" → usuário não sabe que é problema de DNS.

**Recomendação:**
1. Categorizar erros:
```python
ERROR_MESSAGES = {
    "network": "Sem conexão com a internet. Verifique sua rede.",
    "auth": "API key inválida ou expirada. Atualize nas configurações.",
    "not_found": "Modelo não encontrado ou foi removido.",
    "quota": "Limite de downloads atingido. Tente novamente amanhã.",
    "timeout": "Operação muito lenta. Tente um modelo menor.",
}

def categorize_error(exception):
    if isinstance(exception, requests.exceptions.ConnectionError):
        return "network"
    elif "401" in str(exception) or "403" in str(exception):
        return "auth"
    # ...
```

---

#### REL-03: Falta timeout global e rate limiting no addon
**Severidade:** Média | **Impacto:** Confiabilidade | **Esforço:** Pequeno

**Evidência:**
```python
# addon.py: diversos pontos com timeout hardcoded
timeout=30  # linha 1100
timeout=60  # linha 1165
timeout=60  # linha 1641
# Sem rate limiting no lado cliente
```

**Problema:** Usuário pode disparar 100 requests simultâneos, sobrecarregando APIs ou Blender.

**Recomendação:**
1. Timeout global configurável no painel
2. Semaphore para limitar concurrent requests:
```python
# No início do addon
MAX_CONCURRENT_DOWNLOADS = 3
download_semaphore = threading.Semaphore(MAX_CONCURRENT_DOWNLOADS)

def download_with_limit(url):
    with download_semaphore:
        return requests.get(url, timeout=GLOBAL_TIMEOUT)
```

---

### 5. Segurança

#### SEC-01: API key hardcoded no código
**Severidade:** Alta | **Impacto:** Segurança | **Esforço:** Pequeno

**Evidência:**
```python
# addon.py: linha 29
RODIN_FREE_TRIAL_KEY = "k9TcfFoEhNd9cCPP2guHAHHHkctZHIRhZDywZ1euGUXwihbYLpOjQhofby80NJez"
```

**Problema:** Key pública no GitHub, pode ser revogada ou abusada.

**Recomendação:**
1. **Imediato:** Revogar key atual e gerar nova
2. Mover para variável de ambiente ou servidor proxy que injeta key
3. Adicionar rate limiting no proxy para prevenir abuso

---

#### SEC-02: Zip slip vulnerability parcialmente mitigada
**Severidade:** Baixa | **Impacto:** Segurança | **Esforço:** Pequeno

**Evidência:**
```python
# addon.py: linhas 1654-1681
# Mitigação presente mas pode ser melhorada
if ".." in file_path:
    return {"error": "Security issue: Zip contains files with directory traversal sequence"}
```

**Problema:** Verificação de `..` captura casos óbvios mas pode falhar com encodings incomuns ou links simbólicos.

**Recomendação:**
Usar biblioteca segura:
```python
import zipfile
from pathlib import Path

def safe_extract(zip_path, extract_to):
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            # Resolve path canonically
            target = (Path(extract_to) / info.filename).resolve()
            if not str(target).startswith(str(Path(extract_to).resolve())):
                raise ValueError(f"Zip slip attempt: {info.filename}")
        zf.extractall(extract_to)
```

---

### 6. Arquitetura e Manutenibilidade

#### ARCH-01: Duplicação de lógica de conexão socket
**Severidade:** Baixa | **Impacto:** Manutenibilidade | **Esforço:** Médio

**Evidência:**
```python
# addon.py: BlenderMCPServer gerencia socket
# src/blender_mcp/server.py: BlenderConnection gerencia socket
# Lógica de retry/timeout duplicada
```

**Problema:** Mudanças precisam ser feitas em dois lugares.

**Recomendação:**
Extrair para biblioteca compartilhada ou definir contrato de protocolo claro (JSON-RPC, MessagePack).

---

#### ARCH-02: Acoplamento tight entre GUI e lógica
**Severidade:** Média | **Impacto:** Testabilidade | **Esforço:** Médio

**Evidência:**
```python
# src/blender_mcp/gui.py: linhas 189-210
def _apply_changes(self) -> None:
    # Valida, atualiza environment, configura logging, salva arquivo
    # Tudo no mesmo método, dificulta testar individualmente
```

**Recomendação:**
Separar responsabilidades:
```python
# Camada de serviço
class ConfigService:
    def apply_config(self, config: MCPConfig) -> Result[None, str]:
        # Valida
        # Persiste
        # Configura logging
        # Retorna Result monad

# GUI chama serviço
def _apply_changes(self):
    result = self.config_service.apply_config(self.config)
    if result.is_err():
        self._set_status(result.err(), error=True)
```

---

### 7. CI/CD e Testes

#### TEST-01: Cobertura de testes baixa
**Severidade:** Média | **Impacto:** Qualidade | **Esforço:** Grande

**Evidência:**
```bash
# 7 arquivos de teste encontrados
tests/test_cli.py
tests/test_gui.py
tests/test_logging_config.py
tests/test_server.py
tests/unit/test_sandbox.py
tests/unit/test_validators.py
tests/unit/test_windows_timeout.py

# Ausentes:
# - Testes E2E (MCP client → server → addon)
# - Testes UI (QTest para gui.py)
# - Testes de integração com APIs mockadas
```

**Recomendação:**
1. Adicionar testes E2E com mock do Blender:
```python
def test_polyhaven_download_flow():
    with MockBlenderServer():
        client = MCPClient()
        result = client.call_tool("download_polyhaven_asset", {
            "asset_id": "abandoned_warehouse",
            "asset_type": "hdri",
            "resolution": "4k"
        })
        assert result["status"] == "success"
```

2. Testes UI com QTest:
```python
def test_gui_validation():
    app = QApplication([])
    window = ConfigWindow()
    window.host_edit.setText("")
    window._apply_changes()
    assert "Host não pode ser vazio" in window.status_label.text()
```

---

#### TEST-02: Sem CI automatizado para testes
**Severidade:** Baixa | **Impacto:** Qualidade | **Esforço:** Pequeno

**Evidência:**
```bash
# .github/workflows/ não contém workflow de testes
# Apenas release workflows
```

**Recomendação:**
Adicionar `.github/workflows/test.yml`:
```yaml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      - run: pip install -e .[test]
      - run: pytest --cov=src/blender_mcp --cov-report=xml
      - uses: codecov/codecov-action@v3
```

---

### 8. Documentação

#### DOC-01: Falta documentação de UI/UX patterns
**Severidade:** Baixa | **Impacto:** Onboarding | **Esforço:** Pequeno

**Evidência:**
```markdown
# README.md e ARCHITECTURE.md não mencionam:
# - Layout do painel Blender (screenshot anotado)
# - Fluxo UX típico (wireframe)
# - Guidelines de UI (espaçamento, cores)
```

**Recomendação:**
Adicionar `docs/UI_GUIDELINES.md`:
- Screenshots anotados do painel Blender
- Fluxo passo-a-passo com setas
- Guia de contribuição para UI (onde adicionar novos campos)

---

#### DOC-02: Falta guia de acessibilidade
**Severidade:** Baixa | **Impacto:** Inclusão | **Esforço:** Pequeno

**Recomendação:**
Adicionar `docs/ACCESSIBILITY.md`:
- Como testar com screen reader (NVDA/JAWS no Windows, VoiceOver no Mac)
- Checklist WCAG: contraste, navegação teclado, labels
- Roadmap de melhorias de acessibilidade

---

## C) PLANO DE AÇÃO (BACKLOG EXECUTÁVEL)

### 🚀 Quick Wins (1-7 dias)

#### QW-01: Adicionar tooltips descritivos no addon Blender
**Objetivo:** Melhorar clareza para novos usuários  
**Severidade:** Média | **Impacto:** UX | **Esforço:** Pequeno (2h)

**Escopo:**
- Adicionar `description` em todos os `BoolProperty`/`StringProperty` do addon.py

**Passos:**
1. Editar `addon.py`, seção de registro (linhas 1800-1853)
2. Adicionar `description="..."` em cada prop
3. Testar no Blender: hover sobre campo deve mostrar tooltip

**Critério de aceite:**
- [ ] Todos os campos têm tooltip explicativo
- [ ] Tooltips em português coerente com labels
- [ ] Tooltip aparece ao passar mouse sobre campo

**Riscos:** Nenhum  
**Dependências:** Nenhuma

---

#### QW-02: Mover API key hardcoded para variável de ambiente
**Objetivo:** Reduzir risco de abuso do free trial key  
**Severidade:** Alta | **Impacto:** Segurança | **Esforço:** Pequeno (1h)

**Escopo:**
- Remover `RODIN_FREE_TRIAL_KEY` de `addon.py`
- Buscar de variável de ambiente

**Passos:**
1. Editar `addon.py:29`, trocar por:
```python
RODIN_FREE_TRIAL_KEY = os.getenv("RODIN_FREE_TRIAL_KEY", "")
```
2. Atualizar README com instruções para definir env var
3. Se vazio, mostrar mensagem no painel: "Configure RODIN_FREE_TRIAL_KEY"

**Critério de aceite:**
- [ ] Key não presente no código
- [ ] Se var não definida, addon informa usuário claramente
- [ ] Documentação atualizada

**Riscos:** Usuários confusos se não lerem docs  
**Dependências:** Atualizar README primeiro

---

#### QW-03: Adicionar ícones em mensagens de status (GUI)
**Objetivo:** Melhorar acessibilidade (cor não é única indicação)  
**Severidade:** Alta | **Impacto:** A11y | **Esforço:** Pequeno (1h)

**Escopo:**
- Prefixar mensagens com emoji/ícone

**Passos:**
1. Editar `gui.py:284-287`:
```python
def _set_status(self, message: str, *, error: bool = False) -> None:
    icon = "❌" if error else "✅"
    self.status_label.setText(f"{icon} {message}")
    # ...
```

**Critério de aceite:**
- [ ] Mensagens de erro têm ❌
- [ ] Mensagens de sucesso têm ✅
- [ ] Legível em temas claro e escuro

---

#### QW-04: Adicionar setTabOrder na ConfigWindow
**Objetivo:** Navegação por teclado previsível  
**Severidade:** Alta | **Impacto:** A11y | **Esforço:** Pequeno (30min)

**Escopo:**
- Configurar ordem de tabulação em `gui.py`

**Passos:**
1. Após `_build_ui()`, adicionar:
```python
self.setTabOrder(self.host_edit, self.port_spin)
self.setTabOrder(self.port_spin, self.level_combo)
self.setTabOrder(self.level_combo, self.format_edit)
# ... continuar sequência
```

**Critério de aceite:**
- [ ] Tab navega: host → porta → nível → formato → destino → arquivo → aplicar → testar → restaurar
- [ ] Shift+Tab volta na ordem

---

#### QW-05: Adicionar aviso de segurança para API keys no addon
**Objetivo:** Informar usuários sobre risco de compartilhar .blend  
**Severidade:** Alta | **Impacto:** Segurança | **Esforço:** Pequeno (30min)

**Escopo:**
- Label de aviso no painel Blender

**Passos:**
1. Editar `addon.py`, classe `BLENDERMCP_PT_Panel.draw()`:
```python
if scene.blendermcp_use_hyper3d:
    box = layout.box()
    box.alert = True
    box.label(text="⚠️ API keys são salvas no arquivo .blend", icon='ERROR')
    box.label(text="Não compartilhe este arquivo publicamente")
    layout.prop(scene, "blendermcp_hyper3d_api_key", text="API Key")
```

**Critério de aceite:**
- [ ] Aviso visível em vermelho/amarelo
- [ ] Aparece quando Hyper3D ou Sketchfab habilitados
- [ ] Texto claro e objetivo

---

### 📅 Médio Prazo (1-3 sprints)

#### MP-01: Implementar validação inline no GUI
**Objetivo:** Feedback imediato de erros  
**Severidade:** Média | **Impacto:** UX | **Esforço:** Médio (4h)

**Escopo:** [Veja UX-02 acima]  
**Dependências:** Nenhuma

---

#### MP-02: Adicionar progress bar para downloads
**Objetivo:** Feedback visual durante operações longas  
**Severidade:** Média | **Impacto:** UX | **Esforço:** Grande (8h)

**Escopo:**
- Modal popup com barra de progresso no Blender
- Streaming de downloads com callback

**Passos:**
1. Criar operador modal: `BLENDERMCP_OT_DownloadWithProgress`
2. Usar `requests` com `stream=True` e `iter_content()`
3. Atualizar `context.window_manager.progress_begin()/update()`
4. Permitir cancelar com Esc

**Critério de aceite:**
- [ ] Barra de progresso de 0-100%
- [ ] Mostra velocidade (MB/s) e tempo estimado
- [ ] Esc cancela download
- [ ] Cleanup de arquivos parciais ao cancelar

**Riscos:** Complexidade de threading no Blender  
**Dependências:** Estudo de `bpy.ops.wm.progress_begin/update/end`

---

#### MP-03: Refatorar addon.py em módulos
**Objetivo:** Melhorar manutenibilidade  
**Severidade:** Média | **Impacto:** Manutenibilidade | **Esforço:** Grande (16h)

**Escopo:** [Veja PERF-01 acima]

**Passos:**
1. Criar estrutura de diretórios `addon/`
2. Mover handlers para módulos separados
3. Atualizar imports no `__init__.py`
4. Testar que addon carrega no Blender

**Critério de aceite:**
- [ ] Nenhum arquivo >500 linhas
- [ ] Cada módulo tem responsabilidade única
- [ ] Testes passam
- [ ] Addon funciona no Blender 3.0+

**Riscos:** Quebra de compatibilidade  
**Dependências:** Backup do addon.py original, testes E2E

---

#### MP-04: Implementar circuit breaker para APIs externas
**Objetivo:** Prevenir cascata de falhas  
**Severidade:** Média | **Impacto:** Confiabilidade | **Esforço:** Médio (6h)

**Escopo:** [Veja REL-01 acima]  
**Dependências:** Refactoring de handlers de API

---

#### MP-05: Adicionar cache persistente de assets
**Objetivo:** Reduzir downloads duplicados  
**Severidade:** Baixa | **Impacto:** Performance/UX | **Esforço:** Médio (6h)

**Escopo:** [Veja PERF-03 acima]

**Passos:**
1. Criar `~/.blender_mcp/cache/` no primeiro uso
2. Hash do asset_id + type + resolution → filename
3. Verificar cache antes de download
4. TTL de 7 dias (configurável)
5. Botão "Limpar cache" no painel

**Critério de aceite:**
- [ ] Assets baixados são cacheados
- [ ] Segundo download do mesmo asset é instantâneo
- [ ] Cache respeita TTL
- [ ] Limpeza de cache funciona

---

#### MP-06: Implementar i18n (inglês/português)
**Objetivo:** Suporte a idiomas  
**Severidade:** Baixa | **Impacto:** UX/Acessibilidade cultural | **Esforço:** Médio (8h)

**Escopo:**
- Sistema de tradução no addon e GUI

**Passos:**
1. Criar `translations/en.json` e `translations/pt_BR.json`
2. Função helper: `def _(key): return TRANSLATIONS[CURRENT_LOCALE][key]`
3. Substituir strings hardcoded: `_("use_polyhaven")`
4. Adicionar toggle de idioma no painel
5. Salvar preferência no addon preferences

**Critério de aceite:**
- [ ] Toda UI traduzível
- [ ] Padrão é locale do sistema
- [ ] Toggle manual funciona
- [ ] Documentação em ambos idiomas

---

### 🏗️ Estrutural (Refactors / Hardening)

#### EST-01: Mover I/O de rede para threads assíncronos
**Objetivo:** Eliminar bloqueio da UI do Blender  
**Severidade:** Alta | **Impacto:** Performance/UX | **Esforço:** Grande (16h)

**Escopo:** [Veja PERF-02 acima]

**Passos:**
1. Criar `utils/async_download.py` com threadpool
2. Refatorar handlers para retornar job_id
3. Polling com `get_job_status(job_id)`
4. UI atualiza via `bpy.app.timers`

**Critério de aceite:**
- [ ] Downloads não bloqueiam UI
- [ ] Múltiplos downloads simultâneos (max 3)
- [ ] Cancelamento funciona
- [ ] Sem race conditions

**Riscos:** Complexidade, bugs de threading  
**Dependências:** Testes de stress, revisão de código

---

#### EST-02: Adicionar testes E2E completos
**Objetivo:** Cobertura de fluxos críticos  
**Severidade:** Média | **Impacto:** Qualidade | **Esforço:** Grande (20h)

**Escopo:** [Veja TEST-01 acima]

**Passos:**
1. Criar mock server do Blender
2. Implementar client MCP de teste
3. Escrever cenários:
   - Happy path: download Poly Haven
   - Error path: API down, timeout, invalid key
   - Edge cases: large files, concurrent requests
4. Integrar no CI

**Critério de aceite:**
- [ ] 80% cobertura de linhas
- [ ] Fluxos críticos cobertos
- [ ] CI falha se testes quebram
- [ ] Testes rodam em <5min

---

#### EST-03: Implementar logging estruturado com métricas
**Objetivo:** Observabilidade em produção  
**Severidade:** Média | **Impacto:** Operação | **Esforço:** Médio (8h)

**Escopo:**
- JSON logging com contexto
- Métricas: latência, taxa erro, throughput

**Passos:**
1. Adicionar `structlog` como dependência
2. Wrapper de logging:
```python
logger.info("download_started", 
    asset_id=asset_id, 
    asset_type=asset_type,
    user_id=hash(bpy.context.scene.name))
```
3. Métricas básicas:
   - Contador: `downloads_total{type=hdri, status=success}`
   - Histograma: `download_duration_seconds`
4. Exportar para arquivo JSON rotacionado

**Critério de aceite:**
- [ ] Logs em JSON parseável
- [ ] Cada request tem correlation_id
- [ ] Métricas calculáveis (média latência, % erro)

---

#### EST-04: Design system para GUI PySide6
**Objetivo:** Consistência visual  
**Severidade:** Baixa | **Impacto:** UX/Manutenibilidade | **Esforço:** Médio (6h)

**Escopo:**
- Tokens de design (cores, spacing, typography)
- QSS stylesheet global

**Passos:**
1. Criar `gui/design_tokens.py`:
```python
SPACING_XS = 4
SPACING_SM = 8
SPACING_MD = 16
SPACING_LG = 24
SPACING_XL = 32

COLOR_PRIMARY = "#1976d2"
COLOR_ERROR = "#d32f2f"
COLOR_SUCCESS = "#2e7d32"

FONT_SIZE_BODY = 14
FONT_SIZE_HEADING = 18
```

2. Criar `gui/styles.qss`:
```css
QLineEdit:focus {
    border: 2px solid #1976d2;
    border-radius: 4px;
}

QPushButton {
    padding: 8px 16px;
    background-color: #1976d2;
    color: white;
}
```

3. Aplicar: `app.setStyleSheet(QSS_CONTENT)`

**Critério de aceite:**
- [ ] Todos os valores hardcoded substituídos por tokens
- [ ] Tema consistente em claro/escuro
- [ ] Fácil customizar cores globalmente

---

## D) INSTRUMENTAÇÃO E VALIDAÇÃO

### Como medir melhorias

#### UX/Acessibilidade
**Métricas:**
- [ ] Checklist WCAG 2.1 AA: 100% dos itens aplicáveis
- [ ] Teste com screen reader: 0 erros críticos
- [ ] Navegação por teclado: 100% das ações acessíveis
- [ ] Tempo para completar tarefa comum (ex: configurar e conectar): reduzir de ~5min para ~2min

**Ferramentas:**
- axe DevTools (para web) ou equivalente Qt
- NVDA/JAWS no Windows, VoiceOver no macOS
- Lighthouse Accessibility audit (se houver componente web)

**Checklist:**
```markdown
- [ ] Todas as imagens têm alt text (se aplicável)
- [ ] Labels descritivos em todos os campos
- [ ] Contraste mínimo 4.5:1 (texto) e 3:1 (UI)
- [ ] Foco visível em todos os elementos interativos
- [ ] Sem timeout que force ação rápida
- [ ] Erros identificados claramente e com sugestão de correção
```

---

#### Performance
**Métricas:**
- [ ] Tempo de resposta: `get_scene_info` <500ms (P95)
- [ ] Download Poly Haven 1GB HDRI: <120s (antes: bloqueante; depois: assíncrono com feedback)
- [ ] Latência socket MCP ↔ Blender: <50ms (P95)
- [ ] Uso de memória: ≤100MB (excluindo assets)

**Ferramentas:**
- `cProfile` para hotspots Python
- Blender System Console para logs de tempo
- `time.perf_counter()` em pontos críticos
- Prometheus/Grafana para métricas em produção (se aplicável)

**Benchmark:**
```python
# tests/benchmark/test_performance.py
import time

def test_get_scene_info_performance():
    start = time.perf_counter()
    result = addon.get_scene_info()
    duration = time.perf_counter() - start
    assert duration < 0.5, f"Too slow: {duration}s"
```

---

#### Confiabilidade
**Métricas:**
- [ ] Taxa de erro: <1% para operações normais
- [ ] Taxa de timeout: <5% (com retry)
- [ ] Circuit breaker ativa após 5 falhas consecutivas
- [ ] Recovery time após API externa voltar: <30s

**Testes:**
- Chaos engineering: desligar API externa durante teste
- Load test: 100 requests simultâneos
- Soak test: 24h rodando sem crash/leak

---

#### Code Quality
**Métricas:**
- [ ] Cobertura de testes: >80%
- [ ] Complexidade ciclomática: <10 por função (McCabe)
- [ ] Duplicação: <3%
- [ ] Vulnerabilidades conhecidas: 0 (Snyk/Dependabot)

**Ferramentas:**
- `pytest-cov` para cobertura
- `radon` para complexidade
- `ruff` para linting
- `mypy` para type checking
- Dependabot para dependências

---

### Dados faltantes e onde coletar

#### Uso real (telemetria opcional)
Se implementar telemetria (opt-in):
- Comandos mais usados (top 10)
- Taxa de erro por comando
- Tempo médio por operação
- Configurações mais comuns (Poly Haven vs Hyper3D)

**Onde adicionar:**
```python
# src/blender_mcp/telemetry.py (opt-in)
def track_event(event_name, properties):
    if not user_consented_telemetry():
        return
    # Send to analytics (self-hosted Plausible/Umami)
```

#### User research (qualitativo)
- Entrevistas com 5 usuários reais
- Perguntas:
  - Qual tarefa mais comum?
  - Qual maior frustração?
  - O que falta?
- Documentar em `docs/USER_RESEARCH.md`

---

## APÊNDICES

### A) Priorização Matriz (Impacto × Esforço)

```
Alta Impact, Baixo Esforço (FAZER PRIMEIRO):
- QW-02: Mover API key hardcoded
- QW-03: Adicionar ícones em status
- QW-04: setTabOrder
- QW-05: Aviso segurança API keys

Alta Impact, Médio Esforço:
- MP-02: Progress bar downloads
- MP-04: Circuit breaker

Alta Impact, Alto Esforço:
- EST-01: I/O assíncrono

Média Impact, Baixo Esforço:
- QW-01: Tooltips descritivos

Média Impact, Médio Esforço:
- MP-01: Validação inline
- MP-05: Cache persistente

Baixa Impact, Médio/Alto Esforço:
- MP-03: Refatorar addon.py (importante para manutenção futura)
- EST-04: Design system
```

---

### B) Glossário de Termos

- **Circuit Breaker:** Padrão de design que previne cascata de falhas
- **WCAG:** Web Content Accessibility Guidelines (aplica-se a desktop apps também)
- **Screen Reader:** Software que lê UI para usuários com deficiência visual
- **Zip Slip:** Vulnerabilidade que permite extração de arquivo fora do diretório esperado
- **TTL:** Time To Live (tempo de vida de um cache)
- **MCP:** Model Context Protocol

---

### C) Referências

- [WCAG 2.1 Guidelines](https://www.w3.org/WAI/WCAG21/quickref/)
- [Qt Accessibility](https://doc.qt.io/qt-6/accessible.html)
- [Blender Python API](https://docs.blender.org/api/current/)
- [Circuit Breaker Pattern](https://martinfowler.com/bliki/CircuitBreaker.html)
- [Python asyncio](https://docs.python.org/3/library/asyncio.html)

---

**FIM DA AUDITORIA**

**Próximos passos recomendados:**
1. Revisar este documento com stakeholders
2. Priorizar itens do backlog conforme recursos
3. Implementar Quick Wins primeiro (demonstrar progresso rápido)
4. Configurar métricas e instrumentação
5. Iterar com feedback de usuários reais
