"""
Полный прогон: собрать вакансии со всех источников, отсеять очевидное,
догрузить описания выживших, оценить моделью и сохранить.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Callable

from . import db, llm
from .config import Settings
from .fetcher import Browser, http_client
from .matching import combine, conditions_score, prefilter
from .notify import macos_notification
from .sources import REGISTRY
from .sources.base import JobPost, is_fresh

log = logging.getLogger(__name__)

SCORE_BATCH = 6          # вакансий в одном запросе к модели
HTTP_CONCURRENCY = 3     # вежливость к сайтам важнее скорости
PAUSE_BETWEEN_PAGES = 1.2


class Progress:
    """Состояние текущего прогона — его показывает интерфейс."""

    def __init__(self) -> None:
        self.running = False
        # stage — ключ этапа, params — подстановки; текст собирает интерфейс на своём языке
        self.stage = "idle"
        self.params: dict[str, Any] = {}
        self.found = 0
        self.scored = 0
        self.errors: list[str] = []

    def set(self, stage: str, **params: Any) -> None:
        self.stage, self.params = stage, params
        log.info("[%s] %s", stage, params)

    def snapshot(self) -> dict[str, Any]:
        return {"running": self.running, "stage": self.stage, "params": self.params,
                "found": self.found, "scored": self.scored, "errors": self.errors[-8:]}


PROGRESS = Progress()


def _round_robin(by_source: dict[str, list[int]]) -> list[int]:
    """Берёт по одной вакансии из каждого источника, пока они не кончатся."""
    queues = [list(ids) for ids in by_source.values()]
    order: list[int] = []
    while any(queues):
        for queue in queues:
            if queue:
                order.append(queue.pop(0))
    return order


def _lookback_days(settings: Settings, first_run: bool) -> int:
    """
    Насколько глубоко собирать. Прогоны идут вручную и нерегулярно, поэтому
    смотрим назад до прошлого успешного прогона с запасом в пару дней, а не на
    фиксированную неделю: иначе после двухнедельного перерыва половина вакансий
    прошла бы мимо.
    """
    last = db.last_successful_run_at()
    if first_run or last is None:
        return settings.first_scan_days
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    days = (datetime.now(timezone.utc) - last).days + 2
    return max(2, min(days, settings.first_scan_days))


def _queries(settings: Settings, profile: dict[str, Any]) -> list[str]:
    if settings.queries:
        return [q for q in settings.queries if q.strip()]
    roles = (profile.get("structured") or {}).get("target_roles") or []
    return [r for r in roles if r.strip()][:6]


async def collect(settings: Settings, profile: dict[str, Any],
                  max_age_days: int) -> list[JobPost]:
    """Обходит источники и возвращает сырой список без дублей."""
    queries = _queries(settings, profile)
    if not queries:
        raise ValueError("Не заданы поисковые запросы: добавь их в настройках "
                         "или загрузи резюме, чтобы я взял их оттуда.")

    found: dict[tuple[str, str], JobPost] = {}
    browser: Browser | None = None

    async with http_client() as http:
        try:
            for name in settings.enabled_sources():
                module = REGISTRY.get(name)
                if module is None:
                    continue
                if module.NEEDS_BROWSER and browser is None:
                    PROGRESS.set("browser")
                    browser = Browser()
                    await browser.start()

                fetcher = browser if module.NEEDS_BROWSER else http
                for query in queries:
                    for page in range(1, settings.max_pages_per_query + 1):
                        PROGRESS.set("collect", source=name, query=query, page=page)
                        try:
                            jobs = await module.list_jobs(fetcher, query, page)
                        except Exception as e:
                            msg = f"{name}/{query}/стр.{page}: {type(e).__name__}"
                            PROGRESS.errors.append(msg)
                            log.warning("%s — %s", msg, str(e)[:200])
                            break
                        if not jobs:
                            break
                        for job in jobs:
                            if is_fresh(job.posted_at, max_age_days):
                                found.setdefault((job.source, job.external_id), job)
                        PROGRESS.found = len(found)
                        await asyncio.sleep(PAUSE_BETWEEN_PAGES)
        finally:
            if browser is not None:
                await browser.close()

    return list(found.values())


async def fetch_details(jobs: list[dict[str, Any]], settings: Settings) -> None:
    """Догружает полные описания. Только для тех, кто прошёл предварительный отсев."""
    browser: Browser | None = None
    semaphore = asyncio.Semaphore(HTTP_CONCURRENCY)

    async with http_client() as http:
        try:
            for job in jobs:
                module = REGISTRY.get(job["source"])
                if module is None:
                    continue
                if module.NEEDS_BROWSER and browser is None:
                    browser = Browser()
                    await browser.start()

                post = JobPost(source=job["source"], external_id=job["external_id"],
                               url=job["url"], title=job["title"],
                               description=job.get("description"))
                try:
                    if module.NEEDS_BROWSER:
                        text = await module.fetch_detail(browser, post)
                    else:
                        async with semaphore:
                            text = await module.fetch_detail(http, post)
                except Exception as e:
                    log.warning("описание %s не загрузилось: %s", job["url"], type(e).__name__)
                    text = None

                if text and len(text) > len(job.get("description") or ""):
                    db.set_description(job["id"], text)
                    job["description"] = text
        finally:
            if browser is not None:
                await browser.close()


async def score_all(vacancies: list[dict[str, Any]], profile: dict[str, Any],
                    settings: Settings) -> int:
    """Оценивает пачками. Ошибка одной пачки не должна ронять прогон целиком."""
    model = getattr(settings, "scoring_model", llm.DEFAULT_SCORING_MODEL)
    scored = 0

    for start in range(0, len(vacancies), SCORE_BATCH):
        chunk = vacancies[start:start + SCORE_BATCH]
        PROGRESS.set("score", done=start + len(chunk), total=len(vacancies))
        try:
            results = await llm.score_vacancies(profile, chunk, model=model,
                                                lang=settings.ui_lang)
        except Exception as e:
            msg = f"оценка пачки: {type(e).__name__}: {str(e)[:120]}"
            PROGRESS.errors.append(msg)
            log.warning(msg)
            continue

        by_ref = {str(r.ref): r for r in results}
        for vac in chunk:
            result = by_ref.get(str(vac["id"]))
            if result is None:
                continue
            cond, good, bad = conditions_score(vac, settings)
            total, breakdown = combine(result, cond, settings)
            db.save_match(
                vacancy_id=vac["id"], score=total, breakdown=breakdown,
                matched=(result.matched or []) + good,
                missing=(result.missing or []) + bad,
                summary=result.summary or "", red_flags=result.red_flags or [],
                model=model,
            )
            scored += 1
            PROGRESS.scored = scored

    return scored


async def run_scan(first_run: bool = False) -> dict[str, Any]:
    if PROGRESS.running:
        raise RuntimeError("Прогон уже идёт")

    PROGRESS.running = True
    PROGRESS.found = PROGRESS.scored = 0
    PROGRESS.errors = []
    run_id = db.start_run()
    settings = Settings.from_dict(db.load_settings_raw())
    stats: dict[str, Any] = {}

    try:
        profile = db.load_profile()
        if not profile or not profile.get("structured"):
            raise ValueError("Резюме не загружено — без него оценивать не с чем.")
        if not llm.has_api_key():
            raise ValueError("Нет ключа ANTHROPIC_API_KEY: впиши его в файл .env.")

        max_age = _lookback_days(settings, first_run)
        posts = await collect(settings, profile, max_age)
        PROGRESS.set("save", n=len(posts))

        new_ids: list[int] = []
        for post in posts:
            vid, is_new = db.upsert_vacancy(post.to_dict())
            if is_new:
                new_ids.append(vid)

        # Оцениваем всё, что ещё без оценки, а не только новинки этого прогона:
        # так подхватываются вакансии, чья оценка сорвалась в прошлый раз.
        # Порядок — по кругу между источниками, иначе один источник съедает
        # весь бюджет и остальные не оцениваются никогда.
        pending = [db.get_vacancy(i) for i in _round_robin(db.unscored_ids_by_source())]
        pending = [v for v in pending if v]

        kept, dropped = [], 0
        for vac in pending:
            ok, _ = prefilter(vac, settings, profile)
            if ok:
                kept.append(vac)
            else:
                dropped += 1
        kept = kept[:settings.max_details_per_run]

        PROGRESS.set("details", n=len(kept))
        await fetch_details(kept, settings)

        scored = await score_all(kept, profile, settings)

        counts = db.counts_by_tab(settings.threshold, settings.secondary_threshold)
        stats = {"собрано": len(posts), "новых": len(new_ids), "отсеяно_сразу": dropped,
                 "оценено": scored, "подходящих": counts["primary"],
                 "почти_подходящих": counts["secondary"],
                 "ждут_оценки": db.unscored_count()}
        db.finish_run(run_id, True, stats)

        if settings.notify_macos:
            fresh_good = _count_fresh_good(new_ids, settings.threshold)
            if fresh_good:
                await macos_notification(
                    "Найдены новые вакансии",
                    f"{fresh_good} подходящих на {settings.threshold}% и выше",
                    subtitle="Job Radar",
                )
        PROGRESS.set("done", scored=scored, good=counts["primary"])
        return stats

    except Exception as e:
        db.finish_run(run_id, False, stats, f"{type(e).__name__}: {e}")
        PROGRESS.set("error", message=str(e)[:200])
        PROGRESS.errors.append(str(e)[:200])
        raise
    finally:
        PROGRESS.running = False


def _count_fresh_good(new_ids: list[int], threshold: int) -> int:
    if not new_ids:
        return 0
    with db.connect() as conn:
        marks = ",".join("?" * len(new_ids))
        row = conn.execute(
            f"SELECT COUNT(*) FROM matches WHERE score >= ? AND vacancy_id IN ({marks})",
            [threshold, *new_ids],
        ).fetchone()
    return int(row[0])
