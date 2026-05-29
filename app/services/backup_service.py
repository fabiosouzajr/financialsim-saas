"""BackupService - thin facade over app.data.backup for UI/scheduler."""

from __future__ import annotations

from pathlib import Path

from app.data.backup import backup_sqlite, list_backups, prune_backups, restore_sqlite


class BackupService:
    def __init__(self, db_path: Path, backup_dir: Path) -> None:
        self.db_path = db_path
        self.backup_dir = backup_dir

    def backup_now(self) -> Path:
        return backup_sqlite(self.db_path, self.backup_dir)

    def list(self) -> list[Path]:
        return list_backups(self.backup_dir)

    def prune(self, keep_days: int) -> int:
        return prune_backups(self.backup_dir, keep_days=keep_days)

    def restore(self, backup_file: Path) -> None:
        restore_sqlite(backup_file, self.db_path)
