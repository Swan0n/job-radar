"""
Необязательный ежедневный запуск. По умолчанию выключен: прогоны идут только
по кнопке. Если включить, то Mac ночью спит или выключен, поэтому одного cron
мало: при старте проверяем, был ли сегодняшний прогон, и если момент уже
прошёл, а прогона не было — догоняем.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from . import db
from .config import Settings

log = logging.getLogger(__name__)
_scheduler: AsyncIOScheduler | None = None
JOB_ID = "daily-scan"


def _parse_time(value: str) -> dtime:
    try:
        hour, minute = (int(x) for x in value.split(":", 1))
        return dtime(hour=hour % 24, minute=minute % 60)
    except (ValueError, AttributeError):
        return dtime(hour=9)


async def _scan_job(first_run: bool = False) -> None:
    from .pipeline import run_scan
    try:
        await run_scan(first_run=first_run)
    except Exception as e:
        log.error("прогон по расписанию не удался: %s: %s", type(e).__name__, e)


def _apply(settings: Settings) -> None:
    """Ставит или снимает ежедневный запуск в зависимости от настроек."""
    if _scheduler is None:
        return
    if not settings.auto_schedule:
        if _scheduler.get_job(JOB_ID):
            _scheduler.remove_job(JOB_ID)
        log.info("автообновление выключено — прогоны только вручную")
        return

    tz = ZoneInfo(settings.timezone)
    moment = _parse_time(settings.schedule_time)
    _scheduler.add_job(
        _scan_job, CronTrigger(hour=moment.hour, minute=moment.minute, timezone=tz),
        id=JOB_ID, replace_existing=True, misfire_grace_time=3600,
    )
    log.info("расписание: ежедневно в %02d:%02d (%s)", moment.hour, moment.minute, settings.timezone)


def start(settings: Settings) -> AsyncIOScheduler:
    global _scheduler
    _scheduler = AsyncIOScheduler(timezone=ZoneInfo(settings.timezone))
    _scheduler.start()
    _apply(settings)
    return _scheduler


def reschedule(settings: Settings) -> None:
    _apply(settings)


def next_run_iso() -> str | None:
    if _scheduler is None:
        return None
    job = _scheduler.get_job(JOB_ID)
    return job.next_run_time.isoformat() if job and job.next_run_time else None


def missed_today(settings: Settings) -> bool:
    """Момент запуска сегодня уже прошёл, а успешного прогона с тех пор не было."""
    tz = ZoneInfo(settings.timezone)
    now = datetime.now(tz)
    moment = _parse_time(settings.schedule_time)
    today_at = now.replace(hour=moment.hour, minute=moment.minute, second=0, microsecond=0)
    if now < today_at:
        return False
    last = db.last_successful_run_at()
    return last is None or last.astimezone(tz) < today_at


async def catch_up_if_needed(settings: Settings, delay: float = 8.0) -> None:
    """Небольшая пауза, чтобы интерфейс успел подняться раньше тяжёлого прогона."""
    if not settings.auto_schedule or not missed_today(settings):
        return
    if db.last_successful_run_at() is None:
        log.info("успешных прогонов ещё не было — первый запуск сделаем вручную из интерфейса")
        return
    await asyncio.sleep(delay)
    log.info("догоняем пропущенный запуск за сегодня")
    await _scan_job()
