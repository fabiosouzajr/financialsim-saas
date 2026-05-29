#!/usr/bin/env python3
"""Sync finacialsim_core from the desktop repo.

Usage:
    FINACIALSIM_DESKTOP_PATH=/path/to/finacialsim python scripts/sync_core.py
"""
import os
import shutil
from pathlib import Path

desktop = Path(os.environ["FINACIALSIM_DESKTOP_PATH"]).resolve()
dest = Path(__file__).parent.parent / "packages" / "finacialsim_core" / "finacialsim_core"

EXCLUDED = {"cache.py", "cached.py", "__pycache__"}


def _ensure_init(directory: Path) -> None:
    init = directory / "__init__.py"
    if not init.exists():
        init.write_text("")


def sync_flat(src_dir: Path, dst_dir: Path) -> None:
    """Copy *.py files from src_dir directly into dst_dir (no subdirectory)."""
    dst_dir.mkdir(parents=True, exist_ok=True)
    for f in src_dir.iterdir():
        if f.is_file() and f.name not in EXCLUDED and not f.name.startswith("."):
            shutil.copy2(f, dst_dir / f.name)
            print(f"  {f.name}")


def sync_tree(src_dir: Path, dst_dir: Path) -> None:
    """Recursively copy a directory, skipping EXCLUDED files."""
    dst_dir.mkdir(parents=True, exist_ok=True)
    _ensure_init(dst_dir)
    for item in src_dir.iterdir():
        if item.name in EXCLUDED or item.name.startswith("."):
            continue
        if item.is_dir():
            sync_tree(item, dst_dir / item.name)
        else:
            shutil.copy2(item, dst_dir / item.name)
            print(f"  {item.relative_to(src_dir.parent)}")


print("=== Syncing finacialsim_core ===")

print("\n[core] flat files:")
sync_flat(desktop / "app" / "core", dest)

print("\n[integrations]:")
sync_tree(desktop / "app" / "integrations", dest / "integrations")

print("\n[reports]:")
sync_tree(desktop / "app" / "reports", dest / "reports")

print("\n[utils]:")
(dest / "utils").mkdir(exist_ok=True)
_ensure_init(dest / "utils")
src_dv = desktop / "app" / "utils" / "document_validation.py"
if src_dv.exists():
    shutil.copy2(src_dv, dest / "utils" / "document_validation.py")
    print(f"  document_validation.py")

print("\n[tests/core]:")
tests_src = desktop / "tests" / "unit" / "core"
if tests_src.exists():
    tests_dst = Path(__file__).parent.parent / "packages" / "finacialsim_core" / "tests" / "core"
    sync_tree(tests_src, tests_dst)
    _ensure_init(tests_dst.parent)
else:
    print("  (skipped — tests/unit/core not found in source)")

print("\n=== Done ===")
print(f"Destination: {dest}")
