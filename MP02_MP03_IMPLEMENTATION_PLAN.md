# MP-02 e MP-03: Plano de Implementação Detalhado

**Data:** 2025-12-22  
**Status:** Planejamento detalhado para implementação futura

---

## MP-02: Integração Completa de Progress Bars (4h restantes)

### Status Atual
✅ **Fundação Completa:**
- Classe `ProgressTracker` implementada e testada
- Cálculo automático de progresso %, velocidade, ETA
- Sistema de callbacks para atualizações de UI
- 16 testes passando

❌ **Pendente:**
- Integração nos downloads do Poly Haven
- Integração nos downloads do Sketchfab
- UI de progresso no Blender
- Suporte para cancelamento

### Implementação Necessária

#### 1. Modificar Downloads para Streaming (2h)

**Arquivo:** `addon.py`

**Função: `download_polyhaven_asset()` (linha 550)**

```python
# ANTES (linha 577-582):
response = requests.get(file_url, headers=REQ_HEADERS)
if response.status_code != 200:
    return {"error": f"Failed to download HDRI: {response.status_code}"}

with open(tmp_path, 'wb') as f:
    f.write(response.content)

# DEPOIS:
import sys
sys.path.append(os.path.dirname(__file__))
from blender_mcp.progress import get_progress_tracker

# Iniciar tracking
tracker = get_progress_tracker()
operation_id = f"polyhaven_{asset_id}_{resolution}"

# Download com streaming
response = requests.get(file_url, headers=REQ_HEADERS, stream=True)
if response.status_code != 200:
    return {"error": f"Failed to download HDRI: {response.status_code}"}

total_size = int(response.headers.get('content-length', 0))
progress = tracker.start_operation(operation_id, total_size)

downloaded = 0
with open(tmp_path, 'wb') as f:
    for chunk in response.iter_content(chunk_size=8192):
        if chunk:
            f.write(chunk)
            downloaded += len(chunk)
            tracker.update_progress(operation_id, downloaded)

tracker.complete_operation(operation_id)
```

**Locais a modificar:**
1. `download_polyhaven_asset()` - HDRI download (linha 577)
2. `download_polyhaven_asset()` - Textures download (linha 677)
3. `download_sketchfab_model()` - Model download (linha 1750)
4. `import_generated_asset()` - Hyper3D download (linha 1401)

#### 2. Criar Operador Modal no Blender (1h)

**Novo arquivo:** `addon.py` (adicionar após linha 1887)

```python
class BLENDERMCP_OT_DownloadWithProgress(bpy.types.Operator):
    """Download asset with progress bar."""
    bl_idname = "blendermcp.download_with_progress"
    bl_label = "Download Asset"
    
    operation_id: bpy.props.StringProperty()
    
    _timer = None
    _progress = 0
    
    def modal(self, context, event):
        if event.type == 'TIMER':
            # Atualizar progresso
            from blender_mcp.progress import get_progress_tracker
            tracker = get_progress_tracker()
            progress_info = tracker.get_progress(self.operation_id)
            
            if progress_info is None:
                self.cancel(context)
                return {'CANCELLED'}
            
            # Atualizar barra de progresso do Blender
            self._progress = progress_info.progress_percent
            context.window_manager.progress_update(int(self._progress))
            
            # Verificar se completou
            if progress_info.status == 'completed':
                context.window_manager.progress_end()
                self.report({'INFO'}, "Download complete!")
                return {'FINISHED'}
            elif progress_info.status == 'error':
                context.window_manager.progress_end()
                self.report({'ERROR'}, f"Download failed: {progress_info.error_message}")
                return {'CANCELLED'}
        
        # Permitir cancelamento com ESC
        elif event.type == 'ESC':
            from blender_mcp.progress import get_progress_tracker
            tracker = get_progress_tracker()
            tracker.cancel_operation(self.operation_id)
            context.window_manager.progress_end()
            self.report({'WARNING'}, "Download cancelled")
            return {'CANCELLED'}
        
        return {'RUNNING_MODAL'}
    
    def execute(self, context):
        # Iniciar barra de progresso
        context.window_manager.progress_begin(0, 100)
        
        # Registrar timer
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)
        
        return {'RUNNING_MODAL'}
    
    def cancel(self, context):
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
```

**Registrar operador:**
```python
# Na função register() (adicionar após linha 1969):
bpy.utils.register_class(BLENDERMCP_OT_DownloadWithProgress)

# Na função unregister() (adicionar após linha 1991):
bpy.utils.unregister_class(BLENDERMCP_OT_DownloadWithProgress)
```

#### 3. Testes e Validação (1h)

**Criar:** `tests/integration/test_progress_downloads.py`

```python
"""Testes de integração para downloads com progresso."""

import pytest
from unittest.mock import Mock, patch
from blender_mcp.progress import get_progress_tracker


def test_polyhaven_download_tracks_progress():
    """Download do Poly Haven deve usar progress tracker."""
    tracker = get_progress_tracker()
    
    # Mock do requests para simular download
    with patch('requests.get') as mock_get:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {'content-length': '1000'}
        mock_response.iter_content = lambda chunk_size: [b'x' * 100 for _ in range(10)]
        mock_get.return_value = mock_response
        
        # Executar download (precisa estar integrado)
        # ... código de teste ...
        
        # Verificar que progresso foi rastreado
        operations = tracker.get_all_operations()
        assert len(operations) > 0


def test_download_cancellation():
    """Deve permitir cancelar download em progresso."""
    tracker = get_progress_tracker()
    
    operation_id = "test_cancel"
    tracker.start_operation(operation_id, 10000)
    
    # Simular cancelamento
    tracker.cancel_operation(operation_id)
    
    progress = tracker.get_progress(operation_id)
    assert progress.status == 'cancelled'
```

---

## MP-03: Refatoração em Módulos (16h)

### Status Atual
❌ **Não Iniciado** - addon.py tem 1999 linhas em arquivo único

### Arquitetura Proposta

```
addon/
├── __init__.py                  # Registro principal (100 linhas)
├── server.py                    # BlenderMCPServer (200 linhas)
├── handlers/
│   ├── __init__.py
│   ├── scene.py                 # Operações de cena (150 linhas)
│   ├── polyhaven.py             # Poly Haven API (400 linhas)
│   ├── hyper3d.py               # Hyper3D/Rodin (350 linhas)
│   └── sketchfab.py             # Sketchfab API (350 linhas)
├── ui/
│   ├── __init__.py
│   ├── panel.py                 # BLENDERMCP_PT_Panel (100 linhas)
│   └── operators.py             # Operadores (200 linhas)
└── utils/
    ├── __init__.py
    ├── cache.py                 # AssetCache (90 linhas - já existe)
    ├── progress.py              # ProgressTracker (link simbólico)
    └── constants.py             # Constantes compartilhadas (50 linhas)
```

### Implementação Passo a Passo

#### Fase 1: Preparação (2h)

1. **Criar estrutura de diretórios:**
```bash
mkdir -p addon/handlers addon/ui addon/utils
touch addon/__init__.py
touch addon/handlers/__init__.py
touch addon/ui/__init__.py
touch addon/utils/__init__.py
```

2. **Configurar imports:**
```python
# addon/__init__.py
bl_info = {
    "name": "Blender MCP",
    "author": "BlenderMCP",
    "version": (1, 2),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > BlenderMCP",
    "description": "Connect Blender to local LLM clients via MCP",
    "category": "Interface",
}

from . import server
from .ui import panel, operators
from .handlers import scene, polyhaven, hyper3d, sketchfab

def register():
    """Registrar todos os módulos."""
    server.register()
    panel.register()
    operators.register()

def unregister():
    """Desregistrar todos os módulos."""
    operators.unregister()
    panel.unregister()
    server.unregister()
```

#### Fase 2: Extrair Server (3h)

**Arquivo:** `addon/server.py`

Mover a classe `BlenderMCPServer` (linhas 118-548 do addon.py atual):

```python
"""MCP Server implementation for Blender."""

import socket
import json
import threading
import bpy

from .handlers import scene, polyhaven, hyper3d, sketchfab


class BlenderMCPServer:
    """Socket server que expõe operações do Blender via MCP."""
    
    def __init__(self, port=9876):
        self.port = port
        # ... resto da implementação ...
    
    def handle_request(self, data):
        """Rotear requisições para handlers apropriados."""
        tool = data.get("tool")
        
        # Scene operations
        if tool == "get_scene_info":
            return scene.get_scene_info()
        elif tool == "get_object_info":
            return scene.get_object_info(data.get("name"))
        
        # Poly Haven
        elif tool == "download_polyhaven_asset":
            return polyhaven.download_asset(**data.get("params", {}))
        
        # Hyper3D
        elif tool in ["create_rodin_job", "get_rodin_status"]:
            return hyper3d.handle_request(tool, data.get("params", {}))
        
        # Sketchfab
        elif tool == "download_sketchfab_model":
            return sketchfab.download_model(data.get("uid"))
        
        return {"error": f"Unknown tool: {tool}"}
```

#### Fase 3: Extrair Handlers (6h)

**Arquivo:** `addon/handlers/scene.py`

```python
"""Scene information and manipulation handlers."""

import bpy


def get_scene_info():
    """Get current scene information."""
    scene = bpy.context.scene
    return {
        "name": scene.name,
        "frame_current": scene.frame_current,
        "frame_start": scene.frame_start,
        "frame_end": scene.frame_end,
        "objects": [obj.name for obj in scene.objects]
    }


def get_object_info(object_name):
    """Get information about a specific object."""
    # ... implementação ...
```

**Arquivo:** `addon/handlers/polyhaven.py`

```python
"""Poly Haven API integration."""

import bpy
import requests
import tempfile

from ..utils.cache import _asset_cache
from ..utils.progress import get_progress_tracker


def download_asset(asset_id, asset_type, resolution="1k", file_format=None):
    """Download asset from Poly Haven with progress tracking."""
    # ... implementação completa ...
```

**Arquivo:** `addon/handlers/hyper3d.py`
**Arquivo:** `addon/handlers/sketchfab.py`

Similar para Hyper3D e Sketchfab.

#### Fase 4: Extrair UI (3h)

**Arquivo:** `addon/ui/panel.py`

```python
"""Blender UI panel for MCP configuration."""

import bpy
from ..utils.cache import _asset_cache


class BLENDERMCP_PT_Panel(bpy.types.Panel):
    """Panel principal no sidebar do Blender."""
    # ... implementação ...
```

**Arquivo:** `addon/ui/operators.py`

```python
"""Blender operators for MCP actions."""

import bpy


class BLENDERMCP_OT_StartServer(bpy.types.Operator):
    """Start MCP server."""
    # ... implementação ...


class BLENDERMCP_OT_StopServer(bpy.types.Operator):
    """Stop MCP server."""
    # ... implementação ...


# ... outros operadores ...


def register():
    bpy.utils.register_class(BLENDERMCP_OT_StartServer)
    bpy.utils.register_class(BLENDERMCP_OT_StopServer)
    # ...


def unregister():
    bpy.utils.unregister_class(BLENDERMCP_OT_StopServer)
    bpy.utils.unregister_class(BLENDERMCP_OT_StartServer)
    # ...
```

#### Fase 5: Atualizar Testes (2h)

Todos os testes precisam ser atualizados para imports novos:

```python
# ANTES:
from addon import BlenderMCPServer

# DEPOIS:
from addon.server import BlenderMCPServer
```

**Arquivos a atualizar:**
- `tests/test_addon.py`
- `tests/unit/test_*.py`
- Todos os mocks e fixtures

---

## Checklist de Implementação

### MP-02: Progress Bars (4h)

- [ ] **Download Streaming (1.5h)**
  - [ ] Modificar `download_polyhaven_asset()` - HDRI
  - [ ] Modificar `download_polyhaven_asset()` - Textures
  - [ ] Modificar `download_sketchfab_model()`
  - [ ] Modificar `import_generated_asset()` - Hyper3D

- [ ] **Blender Modal Operator (1h)**
  - [ ] Criar `BLENDERMCP_OT_DownloadWithProgress`
  - [ ] Implementar timer e atualização de progresso
  - [ ] Implementar cancelamento com ESC
  - [ ] Registrar/desregistrar operador

- [ ] **Integração e Testes (1.5h)**
  - [ ] Testar download com progresso no Blender
  - [ ] Testar cancelamento
  - [ ] Verificar cleanup de arquivos parciais
  - [ ] Escrever testes de integração

### MP-03: Refatoração (16h)

- [ ] **Preparação (2h)**
  - [ ] Criar estrutura de diretórios
  - [ ] Configurar `__init__.py` principal
  - [ ] Planejar divisão de código

- [ ] **Extrair Server (3h)**
  - [ ] Mover `BlenderMCPServer` para `addon/server.py`
  - [ ] Atualizar roteamento de requisições
  - [ ] Testar que servidor ainda funciona

- [ ] **Extrair Handlers (6h)**
  - [ ] Criar `addon/handlers/scene.py` (1h)
  - [ ] Criar `addon/handlers/polyhaven.py` (2h)
  - [ ] Criar `addon/handlers/hyper3d.py` (2h)
  - [ ] Criar `addon/handlers/sketchfab.py` (1h)

- [ ] **Extrair UI (3h)**
  - [ ] Criar `addon/ui/panel.py` (1.5h)
  - [ ] Criar `addon/ui/operators.py` (1.5h)

- [ ] **Atualizar Testes (2h)**
  - [ ] Atualizar todos os imports
  - [ ] Verificar que todos os testes passam
  - [ ] Adicionar testes de módulos

---

## Riscos e Mitigações

### MP-02
**Risco:** Download streaming pode não funcionar com todas as APIs  
**Mitigação:** Testar com cada API individualmente, manter fallback

**Risco:** Modal operator pode bloquear UI  
**Mitigação:** Usar timer curto (0.1s) e processar em chunks

### MP-03
**Risco:** Imports circulares entre módulos  
**Mitigação:** Definir hierarquia clara, usar imports tardios quando necessário

**Risco:** Addon não carrega no Blender após refatoração  
**Mitigação:** Testar carregamento após cada etapa, manter backup

**Risco:** Testes quebram com novos imports  
**Mitigação:** Atualizar testes incrementalmente, usar busca/substituição

---

## Próximos Passos Recomendados

1. **Começar com MP-02** - Mais impacto imediato para usuários
2. **Validar MP-02 em produção** - Garantir que funciona bem
3. **Depois fazer MP-03** - Melhora manutenibilidade
4. **Integrar circuit breakers** nos downloads durante MP-02
5. **Integrar cache** nos downloads durante MP-02

---

## Tempo Total Estimado

- **MP-02:** 4 horas
- **MP-03:** 16 horas
- **Total:** 20 horas

**Com o que já foi feito:** 28h + 20h = **48h total** (100% completo)

---

**Preparado por:** Sistema de Análise Automatizada  
**Data:** 22 de dezembro de 2025  
**Status:** Plano detalhado pronto para execução
