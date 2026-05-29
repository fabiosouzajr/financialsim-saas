"""Scheduler - APScheduler wiring for background jobs (indicators + backup).

# TODO(Phase 5): centralize db_path/backup_dir in app/config.py
"""

from __future__ import annotations

import asyncio
import json
from datetime import date, timedelta
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler

from app.data.repositories import BusinessRuleRepository
from app.services.backup_service import BackupService
from app.services.indicators_service import IndicatorsService

_BACEN_CODES = ["SELIC_META", "CDI", "IPCA", "TX_BACEN_VEIC"]

_scheduler: BackgroundScheduler | None = None


async def _run_indicators_update(session_factory, bacen_chain) -> None:
    svc = IndicatorsService(session_factory, bacen_chain)
    today = date.today()
    yesterday = today - timedelta(days=1)
    for codigo in _BACEN_CODES:
        await svc.update_indicator(codigo, yesterday, today)


def _run_backup(db_path: Path, backup_dir: Path, session_factory) -> None:
    svc = BackupService(db_path=db_path, backup_dir=backup_dir)
    svc.backup_now()
    with session_factory() as s:
        raw = BusinessRuleRepository(s).get("backup_retencao_dias")
        keep_days = int(raw) if raw else 30
    svc.prune(keep_days=keep_days)


def _indicators_job(session_factory, bacen_chain) -> None:
    asyncio.run(_run_indicators_update(session_factory, bacen_chain))


def _read_time(session_factory, chave: str, fallback: str) -> tuple[int, int]:
    with session_factory() as s:
        raw = BusinessRuleRepository(s).get(chave)
    time_str = json.loads(raw) if raw else fallback
    hour, minute = (int(x) for x in time_str.split(":"))
    return hour, minute


def start_scheduler(
    session_factory,
    bacen_chain,
    db_path: Path,
    backup_dir: Path,
) -> None:
    global _scheduler
    ind_hour, ind_min = _read_time(session_factory, "update_indicadores_horario", "09:00")
    bak_hour, bak_min = _read_time(session_factory, "backup_diario_horario", "23:00")

    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        _indicators_job,
        trigger="cron",
        hour=ind_hour,
        minute=ind_min,
        id="indicators_update",
        args=[session_factory, bacen_chain],
    )
    _scheduler.add_job(
        _run_backup,
        trigger="cron",
        hour=bak_hour,
        minute=bak_min,
        id="daily_backup",
        args=[db_path, backup_dir, session_factory],
    )
    _scheduler.start()


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown()
        _scheduler = None
