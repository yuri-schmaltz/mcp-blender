# Release and Publishing Guide

Follow these steps to prepare and publish a Blender MCP release to PyPI.

## 1. Prerequisites
- Python 3.11+ installed locally
- An up-to-date `pip`
- Access to the PyPI project with a valid API token

## 2. Prepare the release
1. Update the version in `pyproject.toml`.
2. Add any relevant release notes to `README.md` or a changelog entry.
3. Commit the changes and push them to open a pull request.

## 3. Build and verify
From the repository root:

```bash
python -m pip install --upgrade pip
python -m pip install build twine
python -m build
python -m twine check dist/*
```

The CI workflow runs the same build and metadata checks on pushes and pull requests to ensure the package is ready to publish.

## 4. Publish to PyPI
Upload the release artifacts in `dist/` using Twine:

```bash
python -m twine upload dist/*
```

Use the `PYPI_USERNAME` set to `__token__` and the `PYPI_PASSWORD` set to your API token when prompted, or configure these as environment variables.

## 5. Verify the release
- Confirm the new version appears on [PyPI](https://pypi.org/project/blender-mcp/).
- Optionally install the package from PyPI in a clean environment to confirm the upload:

```bash
python -m pip install --no-cache-dir blender-mcp==<new-version>
```
