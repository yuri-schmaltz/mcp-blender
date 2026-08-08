#!/usr/bin/env bash
# Build a Debian package (`.deb`) for blender-mcp.
#
# This is a hand-rolled builder — no pybuild/dh_python3 dependency chain.
# Rationale: the project doesn't yet have a `debian/` source layout and we
# want the artifact to be auditable line-by-line until we know whether
# shipping as a wheel (PyPI) or as a system package is the right
# distribution channel.
#
# Layout of the resulting .deb:
#   /usr/lib/python3/dist-packages/blender_mcp/        MCP server
#   /usr/lib/python3/dist-packages/addon/              Blender addon
#   /usr/bin/blender-mcp                               console script
#   /usr/bin/blender-mcp-gui                           console script
#   /usr/share/blender/4.5/scripts/addons/modules/mcp_blender/  addon install
#   /usr/share/doc/mcp-blender/{README,CHANGELOG,LICENSE}/
#
# Usage: scripts/build_deb.sh [VERSION]
#   VERSION defaults to the version in pyproject.toml.
#
# Requires: python3, pip, dpkg-deb.

set -euo pipefail

# ---------------------------------------------------------------------------- #
# Config                                                                       #
# ---------------------------------------------------------------------------- #
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
STAGING="${REPO_ROOT}/build-deb-staging"
DIST="${REPO_ROOT}/dist"

PYTHON_MIN="3.10"
PYTHON_BIN="${PYTHON_BIN:-python3}"
PIP_BIN="${PIP_BIN:-pip3}"
BLENDER_TARGET_VERSION="4.5"
BLENDER_ADDON_PATH="/usr/share/blender/${BLENDER_TARGET_VERSION}/scripts/addons/modules/mcp_blender"

# ---------------------------------------------------------------------------- #
# Resolve version                                                               #
# ---------------------------------------------------------------------------- #
VERSION="${1:-}"
if [[ -z "$VERSION" ]]; then
    VERSION="$(grep -E '^version = ' "${REPO_ROOT}/pyproject.toml" | head -1 | sed -E 's/^version = "([^"]+)".*$/\1/')"
fi
if [[ -z "$VERSION" ]]; then
    echo "ERROR: could not determine version. Pass it as arg or set in pyproject.toml." >&2
    exit 1
fi
echo "==> Building mcp-blender v${VERSION} .deb"

# ---------------------------------------------------------------------------- #
# Pre-flight                                                                    #
# ---------------------------------------------------------------------------- #
command -v dpkg-deb >/dev/null || { echo "ERROR: dpkg-deb not found" >&2; exit 1; }
command -v "${PYTHON_BIN}" >/dev/null || { echo "ERROR: ${PYTHON_BIN} not found" >&2; exit 1; }
command -v "${PIP_BIN}" >/dev/null || { echo "ERROR: ${PIP_BIN} not found" >&2; exit 1; }

# ---------------------------------------------------------------------------- #
# Build the wheel (idempotent — reuses what `python -m build` produced)        #
# ---------------------------------------------------------------------------- #
if [[ ! -f "${DIST}/blender_mcp-${VERSION}-py3-none-any.whl" ]]; then
    echo "==> Building wheel via 'python -m build'"
    mkdir -p "${DIST}"
    cd "${REPO_ROOT}"
    "${PYTHON_BIN}" -m build --wheel
fi

WHEEL_PATH="$(ls "${DIST}"/blender_mcp-${VERSION}-py3-none-any.whl 2>/dev/null | head -1)"
if [[ -z "${WHEEL_PATH}" ]]; then
    echo "ERROR: wheel not found at ${DIST}/blender_mcp-${VERSION}-py3-none-any.whl" >&2
    exit 1
fi
echo "==> Using wheel: ${WHEEL_PATH}"

# ---------------------------------------------------------------------------- #
# Reset staging                                                                 #
# ---------------------------------------------------------------------------- #
echo "==> Resetting staging at ${STAGING}"
rm -rf "${STAGING}"
mkdir -p "${STAGING}"/{DEBIAN,usr/lib/python3/dist-packages,usr/bin,usr/share/doc/mcp-blender}

# ---------------------------------------------------------------------------- #
# Install the wheel into the staging dir                                       #
# ---------------------------------------------------------------------------- #
echo "==> Installing wheel into staging (no deps, --no-deps; system already has them)"
"${PIP_BIN}" install \
    --target "${STAGING}/usr/lib/python3/dist-packages" \
    --no-deps \
    --no-compile \
    --quiet \
    "${WHEEL_PATH}"

# ---------------------------------------------------------------------------- #
# Create the entry-point scripts in /usr/bin                                    #
# ---------------------------------------------------------------------------- #
echo "==> Generating /usr/bin entry points"
cat > "${STAGING}/usr/bin/blender-mcp" <<EOF
#!/usr/bin/env python3
"""Entry point for the blender-mcp FastMCP server."""
import sys
from blender_mcp.cli import main

if __name__ == "__main__":
    sys.exit(main())
EOF
cat > "${STAGING}/usr/bin/blender-mcp-gui" <<EOF
#!/usr/bin/env python3
"""Entry point for the blender-mcp PySide6 configuration GUI."""
import sys
from blender_mcp.gui import main

if __name__ == "__main__":
    sys.exit(main())
EOF
chmod 0755 "${STAGING}/usr/bin/blender-mcp" "${STAGING}/usr/bin/blender-mcp-gui"

# ---------------------------------------------------------------------------- #
# Symlink the addon into the Blender addons tree                                #
# ---------------------------------------------------------------------------- #
echo "==> Linking addon to ${BLENDER_ADDON_PATH}"
mkdir -p "${STAGING}${BLENDER_ADDON_PATH}"
# The wheel installs the addon at <staging>/usr/lib/python3/dist-packages/addon
# but Blender's Extension Mode looks under scripts/addons/modules/<bl_idname>.
# A symlink keeps the two in sync (one source of truth in the wheel).
ln -s \
    "/usr/lib/python3/dist-packages/addon" \
    "${STAGING}${BLENDER_ADDON_PATH}/addon"

# ---------------------------------------------------------------------------- #
# Copy docs (README, CHANGELOG, LICENSE) into /usr/share/doc                    #
# ---------------------------------------------------------------------------- #
echo "==> Copying documentation"
for doc in README.md CHANGELOG.md LICENSE; do
    if [[ -f "${REPO_ROOT}/${doc}" ]]; then
        cp "${REPO_ROOT}/${doc}" "${STAGING}/usr/share/doc/mcp-blender/${doc}"
    fi
done
# Compress the doc files (Debian policy: shipped gzipped by default)
gzip -9 -f "${STAGING}/usr/share/doc/mcp-blender/"*.md "${STAGING}/usr/share/doc/mcp-blender}/"LICENSE 2>/dev/null || true

# ---------------------------------------------------------------------------- #
# DEBIAN/control                                                                #
# ---------------------------------------------------------------------------- #
INSTALLED_SIZE="$(du -sk "${STAGING}" | awk '{print $1}')"
cat > "${STAGING}/DEBIAN/control" <<EOF
Package: mcp-blender
Version: ${VERSION}
Section: graphics
Priority: optional
Architecture: all
Depends: python3 (>= ${PYTHON_MIN}), python3-pip
Recommends: blender (>= 4.0), python3-requests, python3-litellm
Maintainer: Yuri Schmaltz <yuri.schmaltz@gmail.com>
Homepage: https://github.com/yuri-schmaltz/mcp_blender
Description: MCP server + Blender addon for AI-assisted 3D workflow
 blender-mcp is a Model Context Protocol integration for Blender. It
 connects Blender to local large language models via the MCP, enabling
 assistants running on your own hardware to automate Blender workflows:
 scene creation, prompt-assisted 3D modelling, asset integration from
 Poly Haven / Sketchfab / AmbientCG, and procedural material setup.
 .
 This package ships two components:
  * A FastMCP server (blender-mcp CLI command) that talks to the addon
    over a local TCP socket.
  * A Blender addon (mcp_blender) that registers a socket server inside
    Blender and routes MCP commands to handler functions.
 .
 See /usr/share/doc/mcp-blender/README.md for setup instructions.
Installed-Size: ${INSTALLED_SIZE}
EOF

# ---------------------------------------------------------------------------- #
# DEBIAN/postinst — refresh byte-compiled files                                 #
# ---------------------------------------------------------------------------- #
cat > "${STAGING}/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if which py3compile >/dev/null 2>&1; then
    py3compile -p mcp-blender /usr/lib/python3/dist-packages/blender_mcp 2>/dev/null || true
fi
echo "mcp-blender installed. Run 'blender-mcp --doctor' to verify your setup."
echo "Enable the addon in Blender Preferences → Add-ons → 'MCP Server for Blender'."
EOF
chmod 0755 "${STAGING}/DEBIAN/postinst"

# ---------------------------------------------------------------------------- #
# DEBIAN/prerm                                                                   #
# ---------------------------------------------------------------------------- #
cat > "${STAGING}/DEBIAN/prerm" <<'EOF'
#!/bin/sh
set -e
if which py3clean >/dev/null 2>&1; then
    py3clean -p mcp-blender /usr/lib/python3/dist-packages/blender_mcp 2>/dev/null || true
fi
EOF
chmod 0755 "${STAGING}/DEBIAN/prerm"

# ---------------------------------------------------------------------------- #
# Build the .deb                                                                #
# ---------------------------------------------------------------------------- #
OUT_DEB="${DIST}/mcp-blender_${VERSION}_all.deb"
mkdir -p "${DIST}"
echo "==> dpkg-deb --build ${STAGING} ${OUT_DEB}"
dpkg-deb --build --root-owner-group "${STAGING}" "${OUT_DEB}"

# ---------------------------------------------------------------------------- #
# Inspect                                                                      #
# ---------------------------------------------------------------------------- #
echo
echo "==> Built ${OUT_DEB}"
echo "    size: $(du -h "${OUT_DEB}" | awk '{print $1}')"
echo "    md5:    $(md5sum "${OUT_DEB}" | awk '{print $1}')"
echo "    sha256: $(sha256sum "${OUT_DEB}" | awk '{print $1}')"
echo "    contents (first 25):"
dpkg-deb --contents "${OUT_DEB}" > /tmp/contents.list
head -25 /tmp/contents.list
rm /tmp/contents.list
echo "    ..."
echo
echo "==> Done. To install: sudo apt install ${OUT_DEB}"
