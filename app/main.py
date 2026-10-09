"""HTTP-слой: отдаёт интерфейс и обслуживает его запросы."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# override=True: ключ из .env важнее старого ANTHROPIC_API_KEY из ~/.zshrc.
load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)

from . import db, llm, resume, scheduler          # noqa: E402
from .config import ALL_SOURCES, Settings         # noqa: E402
from .pipeline import PROGRESS, run_scan          # noqa: E402

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("job-radar")

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


def current_settings() -> Settings:
    return Settings.from_dict(db.load_settings_raw())


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    settings = current_settings()
    scheduler.start(settings)
    task = asyncio.create_task(scheduler.catch_up_if_needed(settings))
    yield
    task.cancel()


app = FastAPI(title="Job Radar", lifespan=lifespan)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


# ------------------------------------------------------------------ состояние

@app.get("/api/state")
async def state() -> dict[str, Any]:
    settings = current_settings()
    profile = db.load_profile()
    resume_file = resume.find_resume_file()
    return {
        "settings": settings.to_dict(),
        "all_sources": ALL_SOURCES,
        "profile": (profile or {}).get("structured"),
        "profile_file": (profile or {}).get("source_file"),
        "resume_file_present": resume_file.name if resume_file else None,
        "has_api_key": llm.has_api_key(),
        "counts": db.counts_by_tab(settings.threshold, settings.secondary_threshold),
        "unscored": db.unscored_count(),
        "last_run": db.last_run(),
        "next_run": scheduler.next_run_iso(),
        "progress": PROGRESS.snapshot(),
    }


@app.get("/api/progress")
async def progress() -> dict[str, Any]:
    return PROGRESS.snapshot()


# ------------------------------------------------------------------ вакансии

TABS = {
    "primary":   lambda s: dict(min_score=s.threshold, max_score=101),
    "secondary": lambda s: dict(min_score=s.secondary_threshold, max_score=s.threshold),
    "saved":     lambda s: dict(min_score=0, statuses=["saved"]),
    "applied":   lambda s: dict(min_score=0, statuses=["applied", "interview"]),
    "hidden":    lambda s: dict(min_score=0, statuses=["hidden"]),
    "all":       lambda s: dict(min_score=0),
}

VISIBLE = ["new", "saved", "applied", "interview", "rejected"]


@app.get("/api/vacancies")
async def vacancies(tab: str = "primary", search: str | None = None,
                    source: str | None = None, sort: str = "score",
                    limit: int = 300) -> dict[str, Any]:
    settings = current_settings()
    if tab not in TABS:
        raise HTTPException(400, f"неизвестная вкладка: {tab}")
    if sort not in ("score", "new"):
        raise HTTPException(400, f"неизвестная сортировка: {sort}")

    params = TABS[tab](settings)
    params.setdefault("statuses", VISIBLE)
    items = db.list_vacancies(
        search=search or None,
        sources=[source] if source else None, sort=sort,
        limit=min(limit, 500), **params,
    )
    return {"items": items, "count": len(items)}


@app.get("/api/vacancies/{vacancy_id}")
async def vacancy(vacancy_id: int) -> dict[str, Any]:
    row = db.get_vacancy(vacancy_id)
    if not row:
        raise HTTPException(404, "вакансия не найдена")
    letter = db.get_cover_letter(vacancy_id)
    return {"vacancy": row, "cover_letter": letter}


class StatusPayload(BaseModel):
    status: str
    note: str | None = None


@app.post("/api/vacancies/{vacancy_id}/status")
async def set_status(vacancy_id: int, payload: StatusPayload) -> dict[str, Any]:
    try:
        db.set_status(vacancy_id, payload.status, payload.note)
    except ValueError as e:
        raise HTTPException(400, str(e))
    settings = current_settings()
    return {"ok": True, "counts": db.counts_by_tab(settings.threshold, settings.secondary_threshold)}


# -------------------------------------------------------------- кавер-леттеры

class CoverPayload(BaseModel):
    hint: str | None = None
    regenerate: bool = False


@app.post("/api/vacancies/{vacancy_id}/cover")
async def cover(vacancy_id: int, payload: CoverPayload) -> dict[str, Any]:
    existing = db.get_cover_letter(vacancy_id)
    if existing and not payload.regenerate:
        return {"text": existing["text"], "cached": True}

    vac = db.get_vacancy(vacancy_id)
    if not vac:
        raise HTTPException(404, "вакансия не найдена")
    profile = db.load_profile()
    if not profile:
        raise HTTPException(400, "Резюме не загружено")
    if not llm.has_api_key():
        raise HTTPException(400, "Нет ключа ANTHROPIC_API_KEY — впиши его в файл .env")

    settings = current_settings()
    try:
        text = await llm.write_cover_letter(profile, vac, model=settings.letter_model,
                                            extra_hint=payload.hint)
    except Exception as e:
        raise HTTPException(502, f"Claude не ответил: {type(e).__name__}: {str(e)[:200]}")

    db.save_cover_letter(vacancy_id, text, lang="auto")
    return {"text": text, "cached": False}


# ------------------------------------------------------------------ настройки

@app.post("/api/settings")
async def save_settings(payload: dict[str, Any]) -> dict[str, Any]:
    settings = Settings.from_dict({**(db.load_settings_raw() or {}), **payload})
    db.save_settings_raw(settings.to_dict())
    scheduler.reschedule(settings)
    return {"ok": True, "settings": settings.to_dict(),
            "counts": db.counts_by_tab(settings.threshold, settings.secondary_threshold),
            "next_run": scheduler.next_run_iso()}


# --------------------------------------------------------------------- резюме

@app.post("/api/resume/reload")
async def reload_resume() -> dict[str, Any]:
    path = resume.find_resume_file()
    if not path:
        raise HTTPException(400, "В папке resume/ нет файла PDF, DOCX, TXT или MD")
    if not llm.has_api_key():
        raise HTTPException(400, "Нет ключа ANTHROPIC_API_KEY — впиши его в файл .env")

    try:
        raw = resume.extract_text(path)
    except Exception as e:
        raise HTTPException(400, str(e))

    settings = current_settings()
    try:
        structured = await llm.parse_resume(raw, model=settings.scoring_model)
    except Exception as e:
        raise HTTPException(502, f"Claude не разобрал резюме: {type(e).__name__}: {str(e)[:200]}")

    db.save_profile(raw, structured, path.name)

    # Первый раз подставляем запросы из резюме, дальше не трогаем выбор пользователя.
    if not settings.queries and structured.get("target_roles"):
        settings.queries = structured["target_roles"][:6]
        db.save_settings_raw(settings.to_dict())

    return {"ok": True, "profile": structured, "file": path.name,
            "settings": settings.to_dict()}


# ---------------------------------------------------------------------- скан

@app.post("/api/scan")
async def scan(first_run: bool = False) -> JSONResponse:
    if PROGRESS.running:
        return JSONResponse({"ok": False, "error": "Прогон уже идёт"}, status_code=409)

    async def runner() -> None:
        try:
            await run_scan(first_run=first_run)
        except Exception as e:
            log.error("прогон не удался: %s: %s", type(e).__name__, e)

    asyncio.create_task(runner())
    return JSONResponse({"ok": True, "started": True})
