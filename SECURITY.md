# Security Documentation for BlenderMCP

## Overview

BlenderMCP implements multiple layers of security to protect users when executing code and interacting with external services. This document outlines the security measures, policies, and best practices.

## 🔒 Security Layers

### 1. Code Sandboxing

The `sandbox.py` module provides a secure execution environment for user-provided Python code:

**Restricted Operations:**
- ❌ OS module access (prevents system commands)
- ❌ Subprocess execution (prevents spawning processes)
- ❌ File system operations (prevents reading/writing files)
- ❌ eval/exec functions (prevents dynamic code execution)
- ❌ Import statements (prevents loading arbitrary modules)

**Safe Builtins Only:**
```python
SAFE_BUILTINS = {
    'abs', 'all', 'any', 'bool', 'chr', 'complex', 'dict', 'divmod',
    'enumerate', 'float', 'format', 'hex', 'int', 'len', 'list', 'map',
    'max', 'min', 'oct', 'ord', 'pow', 'print', 'range', 'reversed',
    'round', 'set', 'slice', 'sorted', 'str', 'sum', 'tuple', 'type',
    'zip', '__import__', 'None', 'True', 'False'
}
```

**Rate Limiting:**
- Prevents DoS attacks via rapid code execution
- Configurable requests per second limit
- Automatic throttling of excessive requests

**Execution Timeout:**
- Default timeout: 5 seconds
- Prevents infinite loops
- Platform-specific implementation (signal-based on Unix, timer-based on Windows)

### 2. Input Validation

All user inputs are validated before processing:

**Port Validation:**
- Range: 1024-65535 (non-privileged ports only)
- Type checking (must be integer)

**API Key Validation:**
- Minimum length requirements
- Placeholder detection (rejects "your_api_key", "xxx", etc.)
- Empty string rejection

**Asset ID Validation:**
- Alphanumeric characters only
- Maximum length enforcement
- Path traversal prevention

**File Path Validation:**
- Absolute paths required
- Temporary directory restrictions
- Existence checks when required
- Null byte rejection

**Hostname Validation:**
- IP address format validation
- Hostname format validation
- Localhost acceptance
- Invalid character rejection

### 3. Network Security

**Socket Connection Safety:**
- Connection timeouts prevent hanging
- Retry logic with exponential backoff
- Graceful reconnection on failure
- Proper socket cleanup on disconnect

**API Communication:**
- HTTPS required for external APIs (Poly Haven, Rodin, Sketchfab)
- API key authentication
- Request/response validation
- Error handling without information leakage

### 4. Error Handling

**Secure Error Messages:**
- No stack traces exposed to users
- Generic error messages for security-sensitive failures
- Detailed logging for debugging (server-side only)

**Bare Except Blocks:**
- Intentional in addon.py for Blender stability
- Prevents crashes from propagating to Blender
- Logged internally for debugging

## ⚙️ Configuration Best Practices

### Secure Default Configuration

```json
{
    "blender_host": "localhost",
    "blender_port": 6789,
    "log_level": "INFO",
    "sandbox_timeout": 5,
    "rate_limit_per_second": 10,
    "connect_attempts": 3,
    "backoff_seconds": 1.0
}
```

### Environment Variables

```bash
# Required for API integrations
export POLYHAVEN_API_KEY="your_secure_key"
export HYPER3D_API_KEY="your_secure_key"
export SKETCHFAB_API_KEY="your_secure_key"

# Optional configuration
export BLENDER_HOST="localhost"
export BLENDER_PORT="6789"
export LOG_LEVEL="INFO"
```

### Production Checklist

- [ ] Never commit API keys to version control
- [ ] Use environment variables or secure secret management
- [ ] Restrict Blender connection to localhost when possible
- [ ] Enable INFO or WARNING log level in production
- [ ] Review sandbox permissions before allowing custom code
- [ ] Monitor rate limiting logs for abuse patterns
- [ ] Keep dependencies updated (run `pip install --upgrade blender-mcp`)

## 🚨 Troubleshooting Security Issues

### Connection Refused Errors

**Symptoms:**
```
Failed to connect to Blender at localhost:6789
```

**Solutions:**
1. Verify Blender addon is enabled
2. Check firewall settings for port 6789
3. Ensure host is set to "localhost" or "127.0.0.1"
4. Try a different port (e.g., 6790)

### Sandbox Execution Failures

**Symptoms:**
```
SecurityError: Import of 'os' is not allowed
```

**Solutions:**
1. Review code for restricted imports
2. Use safe builtins instead
3. Consider if operation should be done server-side instead

### Rate Limit Exceeded

**Symptoms:**
```
RateLimitError: Too many requests
```

**Solutions:**
1. Reduce request frequency
2. Increase rate_limit_per_second in config (if appropriate)
3. Implement client-side caching

### Timeout Errors

**Symptoms:**
```
TimeoutError: Operation timed out after 5 seconds
```

**Solutions:**
1. Optimize code to run faster
2. Increase sandbox_timeout in config
3. Break complex operations into smaller chunks

## 📋 Security Audit Trail

### Logging

All security-relevant events are logged:

```python
# Example log entries
[WARNING] Failed to connect to Blender at localhost:6789 on attempt 1/3
[ERROR] Giving up on Blender connection after 3 attempts
[INFO] Connected to Blender at localhost:6789 on attempt 2/3
[WARNING] Rate limit exceeded for user request
[ERROR] SecurityError: Attempted import of 'os' module blocked
```

### Log Configuration

```python
from blender_mcp.logging_config import configure_logging

configure_logging(
    level="INFO",  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    log_file="/var/log/blender_mcp.log"  # Optional
)
```

## 🔐 Secret Management

### Development

Use `.env` file (add to `.gitignore`):

```bash
# .env
POLYHAVEN_API_KEY=your_key_here
HYPER3D_API_KEY=your_key_here
SKETCHFAB_API_KEY=your_key_here
```

Load with python-dotenv:

```python
from dotenv import load_dotenv
load_dotenv()
```

### Production

**Recommended approaches:**
1. **Environment variables** (system-level)
2. **Secret managers**: AWS Secrets Manager, HashiCorp Vault
3. **CI/CD secrets**: GitHub Secrets, GitLab CI Variables
4. **Container secrets**: Docker secrets, Kubernetes Secrets

**Never:**
- ❌ Commit secrets to git
- ❌ Hardcode in source files
- ❌ Share in chat/logs
- ❌ Use default/placeholder values in production

## 🛡️ Threat Model

### Protected Against

✅ Code injection attacks (via sandboxing)
✅ Path traversal attacks (via input validation)
✅ DoS via infinite loops (via timeouts)
✅ DoS via rapid requests (via rate limiting)
✅ Privilege escalation (via non-root ports)
✅ Information leakage (via secure error handling)
✅ Man-in-the-middle (via HTTPS for APIs)

### Known Limitations

⚠️ **Blender Addon Trust**: The addon runs with full Blender privileges
⚠️ **Local Network**: Assumes localhost connection is trusted
⚠️ **API Keys**: Security depends on proper key management
⚠️ **User Code**: Sandboxed but still executes Python (CPU/Memory usage)

### Recommendations

1. **Isolate Blender**: Run Blender in a dedicated user account
2. **Network Isolation**: Use firewall rules to restrict connections
3. **Resource Limits**: Set CPU/memory limits for Blender process
4. **Regular Audits**: Review logs for suspicious activity
5. **Update Frequently**: Keep package and dependencies current

## 📞 Security Contact

For security vulnerabilities or concerns:
- Open an issue on GitHub (without sensitive details)
- Email: [project maintainer email]
- Do NOT disclose publicly until fixed

---

**Last Updated**: 2025-01-XX
**Version**: 1.2.1
