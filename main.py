import sys
from pathlib import Path

# Ensure local src/ is on sys.path when running from a clone without installation.
PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"

if SRC_DIR.exists():
    sys.path.insert(0, str(SRC_DIR))


def main(argv=None):
    from blender_mcp.cli import main as cli_main

    return cli_main(argv)


if __name__ == "__main__":
    main()
