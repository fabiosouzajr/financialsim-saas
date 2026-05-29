from __future__ import annotations

import gzip
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path


def backup_sqlite(db_path: Path, backup_dir: Path) -> Path:
    """Create a compressed, transaction-safe backup of the SQLite DB."""
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S_%f")
    tmp_path = backup_dir / f"finacialsim_{timestamp}.sqlite"
    gz_path = backup_dir / f"finacialsim_{timestamp}.sqlite.gz"

    src = sqlite3.connect(str(db_path))
    dst = sqlite3.connect(str(tmp_path))
    try:
        with dst:
            src.backup(dst)
    finally:
        src.close()
        dst.close()

    with open(tmp_path, "rb") as f_in, gzip.open(gz_path, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)
    tmp_path.unlink()
    return gz_path


def restore_sqlite(backup_file: Path, target_db: Path) -> None:
    """Restore a .sqlite.gz backup to target_db, overwriting it."""
    target_db.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(backup_file, "rb") as f_in, open(target_db, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)
    conn = sqlite3.connect(str(target_db))
    try:
        result = conn.execute("PRAGMA integrity_check").fetchone()
        if result[0] != "ok":
            raise RuntimeError(f"Restored DB failed integrity check: {result[0]}")
    finally:
        conn.close()


def list_backups(backup_dir: Path) -> list[Path]:
    """Return *.sqlite.gz files sorted newest-first."""
    if not backup_dir.exists():
        return []
    files = list(backup_dir.glob("*.sqlite.gz"))
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


def prune_backups(backup_dir: Path, keep_days: int = 30) -> int:
    """Delete backups older than keep_days. Returns number deleted."""
    cutoff = datetime.now().timestamp() - keep_days * 86400
    deleted = 0
    for f in list_backups(backup_dir):
        if f.stat().st_mtime < cutoff:
            f.unlink()
            deleted += 1
    return deleted
