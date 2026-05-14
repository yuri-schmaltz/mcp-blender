# Troubleshooting Guide

This guide covers common issues and solutions for BlenderMCP.

## Connection Issues

### Blender Cannot Connect to Server

**Symptoms:**
- Error: "Connection refused" or "Cannot connect to server"
- Timeout errors when executing tools

**Solutions:**

1. **Verify server is running:**
   ```bash
   # Check if server process is active
   ps aux | grep blender-mcp
   
   # Or check port availability
   netstat -tlnp | grep 9876
   ```

2. **Check host/port configuration:**
   ```bash
   # Start server with explicit configuration
   blender-mcp --host localhost --port 9876
   ```

3. **Firewall issues (Windows/macOS):**
   - Allow Python through firewall
   - Try using `127.0.0.1` instead of `localhost`

4. **Blender addon not configured:**
   - Open Blender → Edit → Preferences → Add-ons
   - Find "BlenderMCP" and expand settings
   - Verify Host and Port match server configuration

### Server Crashes on Startup

**Symptoms:**
- Immediate exit with error message
- Port already in use errors

**Solutions:**

1. **Port conflict:**
   ```bash
   # Find process using port 9876
   lsof -i :9876  # Linux/macOS
   netstat -ano | findstr :9876  # Windows
   
   # Kill the process or use different port
   blender-mcp --port 9877
   ```

2. **Missing dependencies:**
   ```bash
   pip install --upgrade blender-mcp
   ```

3. **Check logs:**
   ```bash
   # Enable debug logging
   blender-mcp --log-level DEBUG
   ```

## API Integration Issues

### Poly Haven Assets Not Loading

**Symptoms:**
- Empty results from `list_poly_haven_assets`
- Download failures

**Solutions:**

1. **Rate limiting:**
   - Wait 5-10 seconds between requests
   - Circuit breaker may have tripped (wait 30s)

2. **Network issues:**
   ```bash
   curl https://api.polyhaven.com/health
   ```

3. **Invalid asset type:**
   - Valid types: `hdris`, `textures`, `models`

### Hyper3D Rodin Generation Fails

**Symptoms:**
- Job stuck in "processing" state
- API returns 4xx errors

**Solutions:**

1. **API key validation:**
   - Ensure key is set in environment: `export RODIN_API_KEY=your_key`
   - Key must be at least 32 characters

2. **Image requirements:**
   - Format: PNG or JPEG
   - Size: < 10MB recommended
   - Resolution: At least 512x512

3. **Job polling:**
   - Jobs can take 2-5 minutes
   - Use `get_rodin_job_status` to check progress

### Sketchfab Download Issues

**Symptoms:**
- Authentication errors
- Download timeout

**Solutions:**

1. **API token:**
   - Get token from Sketchfab account settings
   - Set: `export SKETCHFAB_TOKEN=your_token`

2. **Large models:**
   - Increase timeout: Edit `server.py` DEFAULT_SOCKET_TIMEOUT
   - Use lower resolution variants

## Security & Sandboxing

### Code Execution Blocked

**Symptoms:**
- Error: "Code execution blocked: forbidden operation"
- Tools involving Python code fail

**Allowed Operations:**
- Basic math and string operations
- Safe built-in functions
- Data manipulation

**Blocked Operations:**
- File system access (`open()`, `os.*`)
- Network calls (`requests`, `socket`)
- Dynamic code execution (`eval()`, `exec()`)
- Subprocess spawning

**Solution:**
- Review code for forbidden operations
- Use dedicated tools for file/network operations
- Contact maintainer to request safe operation whitelisting

### Health Check Warnings

**Symptoms:**
- Log warnings about connection health
- Status shows "degraded" or "unhealthy"

**Solutions:**

1. **Slow responses:**
   - Reduce concurrent operations
   - Check Blender performance
   - Increase health check interval in config

2. **Frequent disconnections:**
   - Verify network stability
   - Check Blender crash logs
   - Reduce socket timeout if too aggressive

## Performance Issues

### Slow Tool Execution

**Causes:**
- Network latency
- Large asset downloads
- Complex Blender operations

**Solutions:**

1. **Optimize network:**
   - Use localhost when possible
   - Reduce retry attempts in config

2. **Asset caching:**
   - Reuse downloaded assets
   - Implement local cache layer

3. **Batch operations:**
   - Combine multiple operations in single call
   - Use Blender's batch processing features

### High Memory Usage

**Symptoms:**
- Server memory grows over time
- OOM errors on large operations

**Solutions:**

1. **Image handling:**
   - Process images in chunks
   - Clear temporary files regularly

2. **Connection pooling:**
   - Reuse connections where possible
   - Close idle connections

## Development & Debugging

### Enable Debug Mode

```bash
# Full debug output
blender-mcp --log-level DEBUG --log-file blender-mcp.log

# View logs in real-time
tail -f blender-mcp.log
```

### Test Connection Manually

```python
import socket
import json

# Test socket connection
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect(('localhost', 9876))
sock.sendall(json.dumps({"test": "ping"}).encode())
response = sock.recv(4096)
print(response.decode())
sock.close()
```

### Run Tests

```bash
# All tests
pytest tests/ -v

# With coverage
pytest tests/ --cov=src/blender_mcp --cov-report=html

# Specific test file
pytest tests/unit/test_circuit_breaker.py -v
```

## Common Error Codes

| Error | Meaning | Solution |
|-------|---------|----------|
| `connection_refused` | Server not running | Start server with `blender-mcp` |
| `timeout` | Operation took too long | Increase timeout or optimize operation |
| `circuit_open` | Too many failures | Wait for circuit breaker reset (30s) |
| `validation_failed` | Invalid input | Check parameter types and values |
| `sandbox_violation` | Forbidden operation | Remove blocked code patterns |
| `auth_required` | Missing credentials | Set API key in environment |

## Getting Help

1. **Check existing issues:** https://github.com/modelcontextprotocol/blender-mcp/issues
2. **Review documentation:** README.md, ARCHITECTURE.md, SECURITY.md
3. **Enable debug logging** and include logs in bug reports
4. **Provide environment details:**
   - Python version: `python --version`
   - OS and version
   - Blender version
   - blender-mcp version: `blender-mcp --version`

## Contributing Fixes

If you identify a recurring issue:

1. Document the workaround
2. Create a test case that reproduces the issue
3. Submit a PR with fix and test
4. Update this troubleshooting guide

---

**Last Updated:** 2025-01-14  
**Version:** 1.2.1
