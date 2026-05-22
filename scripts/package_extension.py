#!/usr/bin/env python3
"""
Package the Blender MCP addon as a standard Blender Extension zip archive.
Usage:
    python scripts/package_extension.py
"""

import os
import zipfile
import shutil
from pathlib import Path

def parse_manifest(manifest_path: Path) -> dict:
    """Simple parser for blender_manifest.toml to extract version and id."""
    metadata = {}
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest file not found: {manifest_path}")
    
    with open(manifest_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                metadata[key] = val
    return metadata

def main():
    repo_root = Path(__file__).resolve().parent.parent
    manifest_path = repo_root / "blender_manifest.toml"
    
    print(f"Reading manifest from {manifest_path}...")
    metadata = parse_manifest(manifest_path)
    
    ext_id = metadata.get("id", "mcp_blender")
    ext_version = metadata.get("version", "0.0.0")
    print(f"Detected extension ID: {ext_id}")
    print(f"Detected extension version: {ext_version}")
    
    dist_dir = repo_root / "dist"
    dist_dir.mkdir(exist_ok=True)
    
    zip_filename = f"{ext_id}_{ext_version}.zip"
    zip_filepath = dist_dir / zip_filename
    
    print(f"Packaging extension to {zip_filepath}...")
    
    # Files and directories to package
    included_files = [
        "blender_manifest.toml",
        "__init__.py",
        "addon.py",
        "LICENSE",
        "README.md",
    ]
    
    included_dirs = [
        "addon",
        "src",
        "translations",
    ]
    
    # Exclude patterns
    exclude_dirs = {"__pycache__", ".git", ".github", ".venv", ".pytest_cache"}
    exclude_extensions = {".pyc", ".pyo", ".git", ".gitignore", ".env", ".lock"}
    
    count_files = 0
    with zipfile.ZipFile(zip_filepath, "w", zipfile.ZIP_DEFLATED) as zip_file:
        # 1. Package single files
        for fname in included_files:
            file_path = repo_root / fname
            if file_path.exists():
                print(f"  Adding file: {fname}")
                zip_file.write(file_path, fname)
                count_files += 1
            else:
                print(f"  Warning: Expected file {fname} not found!")
        
        # 2. Package directories
        for dname in included_dirs:
            dir_path = repo_root / dname
            if not dir_path.exists():
                print(f"  Warning: Expected directory {dname} not found!")
                continue
                
            for root, dirs, files in os.walk(dir_path):
                # Filter out excluded directories in-place to prevent walking them
                dirs[:] = [d for d in dirs if d not in exclude_dirs]
                
                for file in files:
                    file_path = Path(root) / file
                    if file_path.suffix in exclude_extensions or file.startswith("."):
                        continue
                        
                    # Calculate path relative to repository root for correct zip structuring
                    rel_path = file_path.relative_to(repo_root)
                    print(f"  Adding file: {rel_path}")
                    zip_file.write(file_path, rel_path)
                    count_files += 1
                    
    print(f"Successfully packaged {count_files} files into {zip_filepath}")
    print("Release package is ready.")

if __name__ == "__main__":
    main()
