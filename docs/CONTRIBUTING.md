# Contributing to BlenderMCP

Thank you for considering contributing to BlenderMCP! This document provides guidelines and instructions for contributing.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Making Changes](#making-changes)
- [Testing](#testing)
- [Pull Request Process](#pull-request-process)
- [Coding Standards](#coding-standards)

## Code of Conduct

- Be respectful and inclusive
- Focus on constructive feedback
- Welcome newcomers and help them learn
- Keep discussions professional and on-topic

## Getting Started

1. **Fork the repository** on GitHub
2. **Clone your fork** locally:
   ```bash
   git clone https://github.com/YOUR_USERNAME/blender-mcp.git
   cd blender-mcp
   ```
3. **Set up upstream remote**:
   ```bash
   git remote add upstream https://github.com/modelcontextprotocol/blender-mcp.git
   ```
4. **Create a branch** for your feature:
   ```bash
   git checkout -b feature/your-feature-name
   ```

## Development Setup

### Prerequisites

- Python 3.10+
- pip or uv
- Blender 3.0+ (for addon testing)

### Install Dependencies

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in development mode
pip install -e ".[dev,test,gui]"
```

### Verify Setup

```bash
# Run tests
pytest tests/ -v

# Check code quality
ruff check src/ tests/
ruff format --check src/ tests/

# Type checking
mypy src/blender_mcp/ --ignore-missing-imports
```

## Making Changes

### Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/) format:

```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks

**Examples:**
```
feat(server): add circuit breaker for PolyHaven API
fix(addon): resolve connection timeout on Windows
docs(readme): update installation instructions
test(circuit_breaker): add unit tests for recovery scenario
```

### Branch Naming

- `feature/description` - New features
- `fix/description` - Bug fixes
- `docs/description` - Documentation updates
- `refactor/description` - Code improvements

## Testing

### Running Tests

```bash
# All tests
pytest tests/ -v

# With coverage
pytest tests/ --cov=src/blender_mcp --cov-report=html

# Specific test file
pytest tests/unit/test_circuit_breaker.py -v

# Integration tests
pytest tests/integration/ -v
```

### Writing Tests

- **Unit tests**: Test individual functions/classes in isolation
- **Integration tests**: Test component interactions
- **Test naming**: `test_<function>_<scenario>_<expected_result>`

Example:
```python
def test_circuit_breaker_opens_after_failures():
    """Circuit should open after reaching failure threshold."""
    breaker = CircuitBreaker(name="test", failure_threshold=3)
    
    # Simulate failures
    for _ in range(3):
        with pytest.raises(CircuitBreakerError):
            breaker.call(failing_function)
    
    assert breaker.state == CircuitState.OPEN
```

### Coverage Requirements

- New features should include tests
- Aim for >80% coverage on new code
- Critical paths must be tested
- Edge cases and error conditions

## Pull Request Process

### Before Submitting

1. **Update documentation** if behavior changes
2. **Add tests** for new functionality
3. **Run all tests** and ensure they pass
4. **Check code quality**:
   ```bash
   ruff check src/ tests/
   ruff format src/ tests/
   mypy src/blender_mcp/ --ignore-missing-imports
   ```
5. **Squash commits** if multiple small fixes

### PR Description Template

```markdown
## Description
Brief description of changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
- [ ] Tests added/updated
- [ ] Manual testing performed
- [ ] All existing tests pass

## Checklist
- [ ] Code follows project guidelines
- [ ] Self-review completed
- [ ] Comments added where necessary
- [ ] Documentation updated
```

### Review Process

1. Maintainers will review within 3-5 days
2. Address feedback promptly
3. CI checks must pass
4. At least one approval required for merge

## Coding Standards

### Style Guide

- Follow [PEP 8](https://pep8.org/)
- Use [ruff](https://github.com/astral-sh/ruff) for linting
- Line length: 100 characters max
- Use type hints (gradual typing accepted)

### Code Organization

```
src/blender_mcp/
├── server.py           # MCP server implementation
├── cli.py              # Command-line interface
├── gui.py              # GUI configuration tool
├── logging_config.py   # Logging setup
├── shared/             # Shared utilities
│   ├── validators.py   # Input validation
│   ├── sandbox.py      # Code execution sandbox
│   ├── retry.py        # Retry patterns
│   └── circuit_breaker.py
└── security/           # Security modules
```

### Best Practices

1. **Error Handling**:
   - Use specific exception types
   - Log errors with context
   - Provide helpful error messages

2. **Security**:
   - Validate all inputs
   - Use sandbox for code execution
   - Never store secrets in code
   - Follow principle of least privilege

3. **Performance**:
   - Use async/await for I/O operations
   - Implement caching where appropriate
   - Avoid blocking operations in main thread

4. **Documentation**:
   - Docstrings for public APIs
   - Inline comments for complex logic
   - Update README for user-facing changes

## Areas Needing Contribution

### High Priority

- [ ] Type annotations for server.py
- [ ] Integration with more external APIs
- [ ] Performance optimizations for large assets
- [ ] Enhanced error recovery mechanisms

### Medium Priority

- [ ] Additional test coverage (target: 80%)
- [ ] CI/CD pipeline improvements
- [ ] Docker containerization
- [ ] Plugin system for extensibility

### Nice to Have

- [ ] Web-based configuration UI
- [ ] Asset preview thumbnails
- [ ] Batch operation support
- [ ] Multi-language support

## Questions?

- Open an issue for discussion
- Join our [Discord](https://discord.gg/z5apgR8TFU)
- Check existing documentation

---

**Thank you for contributing to BlenderMCP!** 🎉
