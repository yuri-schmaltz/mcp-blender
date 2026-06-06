#!/usr/bin/env python3
import json
import os
import shutil
import subprocess
import sys


def print_header(text):
    print("\n" + "=" * 60)
    print(f" {text}".center(60))
    print("=" * 60 + "\n")


def check_command(cmd):
    return shutil.which(cmd) is not None


def run_command(cmd):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return True, result.stdout.strip()
    except subprocess.CalledProcessError as e:
        return False, e.stderr.strip()
    except Exception as e:
        return False, str(e)


def get_blender_command():
    """Detect blender command, prioritizing native, then flatpak."""
    # 1. Native blender in PATH
    if check_command("blender"):
        return ["blender"], "Native"

    # 2. Flatpak blender
    if check_command("flatpak"):
        # Check if org.blender.Blender is installed
        ok, output = run_command(["flatpak", "list", "--ref"])
        if ok and "org.blender.Blender" in output:
            return ["flatpak", "run", "--command=blender", "org.blender.Blender"], "Flatpak"

    return None, None


def main():
    print_header("Blender MCP v2.0.0 - Unified Installer")

    # 1. System Dependency Checks
    print("[1/4] Checking system dependencies...")

    uv_available = check_command("uv")
    if uv_available:
        print("  [OK] 'uv' found.")
    else:
        print("  [WARN] 'uv' not found. We recommend installing it: https://astral.sh/uv")
        print("         Falling back to standard 'pip' checks.")

    blender_cmd, blender_type = get_blender_command()
    if blender_cmd:
        _, blender_ver = run_command(blender_cmd + ["--version"])
        ver_str = blender_ver.splitlines()[0] if blender_ver else "Unknown"
        print(f"  [OK] Blender found ({blender_type}): {ver_str}")
    else:
        print("  [WARN] 'blender' not found in PATH or Flatpak. Ensure you have Blender installed.")

    # 2. Blender environment check
    print("\n[2/4] Validating Blender Python environment...")
    if blender_cmd:
        # Check for 'requests' in Blender
        check_script = "import importlib.util; print('OK' if importlib.util.find_spec('requests') else 'MISSING')"
        ok, output = run_command(blender_cmd + ["--background", "--python-expr", check_script])
        if ok and "OK" in output:
            print("  [OK] 'requests' library available in Blender.")
        else:
            print("  [ACTION REQUIRED] 'requests' is missing in Blender.")
            if blender_type == "Flatpak":
                print(
                    "                    Special Note for Flatpak: Run 'Install Dependencies' inside "
                )
                print("                    the Blender MCP panel, as the sandbox is restricted.")
            else:
                print(
                    "                    Run 'Install Dependencies' inside the Blender MCP panel."
                )
    else:
        print("  [SKIP] Skipping Blender environment check (blender not found).")

    # 3. Project initialization
    print("\n[3/4] Preparing project...")
    if uv_available:
        print("  Running 'uv sync'...")
        ok, _ = run_command(["uv", "sync"])
        if ok:
            print("  [OK] Dependencies synced.")
        else:
            print("  [ERROR] 'uv sync' failed. Check your network.")
    else:
        print("  [SKIP] Standard pip mode. Ensure 'mcp' is installed.")

    # 4. MCP Client Config Generator
    print_header("MCP Configuration")
    print("Select your LLM client to generate a configuration snippet:")
    print("1) Claude Desktop")
    print("2) Cursor")
    print("3) LM Studio")
    print("4) Custom (Generic JSON)")
    print("5) Skip")

    choice = input("\nEnter choice (1-5): ")
    if choice in ["1", "2", "3", "4"]:
        targets = {"1": "claude", "2": "cursor", "3": "lm-studio", "4": "custom"}
        client = targets[choice]

        # Path to this repo
        repo_path = os.path.abspath(os.path.dirname(__file__))

        # Simple snippet generation logic (similar to helpers.py)
        if client == "claude":
            snippet = {
                "mcpServers": {
                    "blender": {
                        "command": "uv",
                        "args": ["--directory", repo_path, "run", "blender-mcp"],
                    }
                }
            }
            print("\nAdd this to your claude_desktop_config.json:")
            print(json.dumps(snippet, indent=2))
        else:
            print(f"\nConfiguration for {client} involves using the folder: {repo_path}")
            print("Command: uv run blender-mcp")

    print_header("Installation Complete!")
    print("Next steps:")
    if blender_type == "Flatpak":
        print("1. Open Blender (Flatpak).")
        print("2. Install the addon: Edit > Preferences > Addons > Install.")
        print("   Note: For Flatpak, the config path is typically:")
        print("   ~/.var/app/org.blender.Blender/config/blender/<versao>/scripts/addons/")
    else:
        print("1. Open Blender.")
        print("2. Install the addon: Edit > Preferences > Addons > Install (select addon/ folder).")
    print("3. Connect and start creating!")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInstallation cancelled.")
        sys.exit(1)
