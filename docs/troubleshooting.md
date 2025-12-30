# troubleshooting.md - Scripts e dicas para troubleshooting

## Logs
- Verifique logs em `stdout` ou arquivo (dependendo do setup).
- Use níveis DEBUG/INFO para rastrear eventos.

## Scripts úteis
```python
# Exibir métricas atuais
from addon.utils.metrics import metrics
print(metrics.report())

# Limpar cache
from addon.utils.cache import AssetCache
cache = AssetCache()
cache.clear()

# Testar conexão socket
import socket
s = socket.socket()
s.connect(("localhost", 9876))
s.close()
```

## Dicas
- Se o servidor não inicia, verifique se a porta 9876 está livre.
- Para erros de asset, limpe o cache e tente novamente.
- Para debugging de UI, ative o modo de desenvolvedor do Blender.

> Atualize este troubleshooting a cada novo cenário identificado.
