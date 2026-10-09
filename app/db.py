"""SQLite-хранилище. Один файл data/jobs.db, без внешней СУБД."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "jobs.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS vacancies (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source        TEXT NOT NULL,
    external_id   TEXT NOT NULL,
    url           TEXT NOT NULL,
    title         TEXT NOT NULL,
    company       TEXT,
    location      TEXT,
    remote        INTEGER DEFAULT 0,
    salary_raw    TEXT,
    salary_min    REAL,
    salary_max    REAL,
    salary_cur    TEXT,
    posted_at     TEXT,
    description   TEXT,
    query         TEXT,
    first_seen    TEXT NOT NULL,
    last_seen     TEXT NOT NULL,
    UNIQUE(source, external_id)
);

CREATE TABLE IF NOT EXISTS matches (
    vacancy_id    INTEGER PRIMARY KEY REFERENCES vacancies(id) ON DELETE CASCADE,
    score         REAL NOT NULL,
    breakdown     TEXT NOT NULL,   -- JSON: под-оценки по каждому измерению
    matched       TEXT,            -- JSON: что совпало
    missing       TEXT,            -- JSON: чего не хватает
    summary       TEXT,            -- короткий вердикт на русском
    red_flags     TEXT,            -- JSON
    model         TEXT,
    scored_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS statuses (
    vacancy_id    INTEGER PRIMARY KEY REFERENCES vacancies(id) ON DELETE CASCADE,
    status        TEXT NOT NULL DEFAULT 'new',
    note          TEXT,
    updated_at    TEXT NOT NULL,
    applied_at    TEXT             -- когда откликнулся; переживает переход в interview/rejected
);

CREATE TABLE IF NOT EXISTS cover_letters (
    vacancy_id    INTEGER PRIMARY KEY REFERENCES vacancies(id) ON DELETE CASCADE,
    text          TEXT NOT NULL,
    lang          TEXT,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS profile (
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    raw_text      TEXT,
    structured    TEXT,            -- JSON: навыки, годы, грейд, домены
    source_file   TEXT,
    updated_at    TEXT
);

CREATE TABLE IF NOT EXISTS app_settings (
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    data          TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at    TEXT NOT NULL,
    finished_at   TEXT,
    ok            INTEGER,
    stats         TEXT,
    error         TEXT
);

CREATE INDEX IF NOT EXISTS idx_vac_source   ON vacancies(source);
CREATE INDEX IF NOT EXISTS idx_vac_seen     ON vacancies(first_seen);
CREATE INDEX IF NOT EXISTS idx_match_score  ON matches(score);
CREATE INDEX IF NOT EXISTS idx_status       ON statuses(status);
"""

# Статусы трекера. 'hidden' убирает вакансию из всех вкладок кроме «Скрытые».
STATUSES = ["new", "saved", "applied", "interview", "rejected", "hidden"]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(statuses)")}
        if "applied_at" not in cols:
            conn.execute("ALTER TABLE statuses ADD COLUMN applied_at TEXT")
            # для старых откликов точной даты нет — берём время последней смены статуса
            conn.execute("UPDATE statuses SET applied_at = updated_at "
                         "WHERE status IN ('applied', 'interview')")


# ---------------------------------------------------------------- настройки

def load_settings_raw() -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT data FROM app_settings WHERE id = 1").fetchone()
    return json.loads(row["data"]) if row else None


def save_settings_raw(data: dict[str, Any]) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO app_settings (id, data, updated_at) VALUES (1, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at",
            (json.dumps(data, ensure_ascii=False), now()),
        )


# ------------------------------------------------------------------ профиль

def load_profile() -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM profile WHERE id = 1").fetchone()
    if not row:
        return None
    return {
        "raw_text": row["raw_text"],
        "structured": json.loads(row["structured"]) if row["structured"] else {},
        "source_file": row["source_file"],
        "updated_at": row["updated_at"],
    }


def save_profile(raw_text: str, structured: dict[str, Any], source_file: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO profile (id, raw_text, structured, source_file, updated_at) "
            "VALUES (1, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET "
            "raw_text = excluded.raw_text, structured = excluded.structured, "
            "source_file = excluded.source_file, updated_at = excluded.updated_at",
            (raw_text, json.dumps(structured, ensure_ascii=False), source_file, now()),
        )


# ----------------------------------------------------------------- вакансии

def upsert_vacancy(v: dict[str, Any]) -> tuple[int, bool]:
    """Возвращает (id, впервые_ли_увидели). Повторная встреча только двигает last_seen."""
    ts = now()
    with connect() as conn:
        row = conn.execute(
            "SELECT id FROM vacancies WHERE source = ? AND external_id = ?",
            (v["source"], v["external_id"]),
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE vacancies SET last_seen = ?, url = ?, title = ?, company = ?, "
                "location = ?, remote = ?, salary_raw = ?, salary_min = ?, salary_max = ?, "
                "salary_cur = ?, posted_at = COALESCE(?, posted_at), "
                "description = COALESCE(?, description) WHERE id = ?",
                (ts, v["url"], v["title"], v.get("company"), v.get("location"),
                 int(v.get("remote", 0)), v.get("salary_raw"), v.get("salary_min"),
                 v.get("salary_max"), v.get("salary_cur"), v.get("posted_at"),
                 v.get("description"), row["id"]),
            )
            return row["id"], False

        cur = conn.execute(
            "INSERT INTO vacancies (source, external_id, url, title, company, location, "
            "remote, salary_raw, salary_min, salary_max, salary_cur, posted_at, description, "
            "query, first_seen, last_seen) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (v["source"], v["external_id"], v["url"], v["title"], v.get("company"),
             v.get("location"), int(v.get("remote", 0)), v.get("salary_raw"),
             v.get("salary_min"), v.get("salary_max"), v.get("salary_cur"),
             v.get("posted_at"), v.get("description"), v.get("query"), ts, ts),
        )
        vid = int(cur.lastrowid)
        conn.execute(
            "INSERT OR IGNORE INTO statuses (vacancy_id, status, updated_at) VALUES (?, 'new', ?)",
            (vid, ts),
        )
        return vid, True


def set_description(vacancy_id: int, description: str) -> None:
    with connect() as conn:
        conn.execute("UPDATE vacancies SET description = ? WHERE id = ?", (description, vacancy_id))


def save_match(vacancy_id: int, score: float, breakdown: dict, matched: list,
               missing: list, summary: str, red_flags: list, model: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO matches (vacancy_id, score, breakdown, matched, missing, summary, "
            "red_flags, model, scored_at) VALUES (?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(vacancy_id) DO UPDATE SET score = excluded.score, "
            "breakdown = excluded.breakdown, matched = excluded.matched, "
            "missing = excluded.missing, summary = excluded.summary, "
            "red_flags = excluded.red_flags, model = excluded.model, scored_at = excluded.scored_at",
            (vacancy_id, score, json.dumps(breakdown, ensure_ascii=False),
             json.dumps(matched, ensure_ascii=False), json.dumps(missing, ensure_ascii=False),
             summary, json.dumps(red_flags, ensure_ascii=False), model, now()),
        )


def unscored_vacancy_ids(limit: int = 500) -> list[int]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT v.id FROM vacancies v LEFT JOIN matches m ON m.vacancy_id = v.id "
            "WHERE m.vacancy_id IS NULL "
            "ORDER BY COALESCE(v.posted_at, v.first_seen) DESC, v.id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [r["id"] for r in rows]


def unscored_ids_by_source() -> dict[str, list[int]]:
    """
    Неоценённые вакансии, разложенные по источникам. Нужно именно так:
    все записи одного прогона получают одинаковую метку времени с точностью
    до секунды, поэтому общая сортировка по дате вырождается в порядок
    вставки, и последний обойдённый источник забирает весь бюджет оценки.
    """
    with connect() as conn:
        rows = conn.execute(
            "SELECT v.id, v.source FROM vacancies v LEFT JOIN matches m ON m.vacancy_id = v.id "
            "WHERE m.vacancy_id IS NULL "
            "ORDER BY COALESCE(v.posted_at, v.first_seen) DESC, v.id DESC"
        ).fetchall()
    out: dict[str, list[int]] = {}
    for row in rows:
        out.setdefault(row["source"], []).append(row["id"])
    return out


def unscored_count() -> int:
    with connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM vacancies v LEFT JOIN matches m ON m.vacancy_id = v.id "
            "WHERE m.vacancy_id IS NULL"
        ).fetchone()
    return int(row[0])


def get_vacancy(vacancy_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM vacancies WHERE id = ?", (vacancy_id,)).fetchone()
    return dict(row) if row else None


def list_vacancies(min_score: float = 0, max_score: float = 101,
                   statuses: Iterable[str] | None = None,
                   sources: Iterable[str] | None = None,
                   search: str | None = None, since: str | None = None,
                   sort: str = "score", limit: int = 500) -> list[dict[str, Any]]:
    sql = [
        "SELECT v.*, m.score, m.breakdown, m.matched, m.missing, m.summary, m.red_flags,",
        "       s.status, s.note, s.applied_at, (c.vacancy_id IS NOT NULL) AS has_letter",
        "FROM vacancies v",
        "JOIN matches m ON m.vacancy_id = v.id",
        "LEFT JOIN statuses s ON s.vacancy_id = v.id",
        "LEFT JOIN cover_letters c ON c.vacancy_id = v.id",
        "WHERE m.score >= ? AND m.score < ?",
    ]
    args: list[Any] = [min_score, max_score]
    if statuses:
        marks = ",".join("?" * len(list(statuses)))
        sql.append(f"AND COALESCE(s.status,'new') IN ({marks})")
        args.extend(statuses)
    if sources:
        srcs = list(sources)
        sql.append(f"AND v.source IN ({','.join('?' * len(srcs))})")
        args.extend(srcs)
    if search:
        sql.append("AND (v.title LIKE ? OR v.company LIKE ? OR v.description LIKE ?)")
        like = f"%{search}%"
        args.extend([like, like, like])
    if since:
        sql.append("AND v.first_seen >= ?")
        args.append(since)
    if sort == "new":
        sql.append("ORDER BY v.first_seen DESC, m.score DESC LIMIT ?")
    else:
        sql.append("ORDER BY m.score DESC, v.first_seen DESC LIMIT ?")
    args.append(limit)

    with connect() as conn:
        rows = conn.execute(" ".join(sql), args).fetchall()

    out = []
    for r in rows:
        d = dict(r)
        for key in ("breakdown", "matched", "missing", "red_flags"):
            try:
                d[key] = json.loads(d[key]) if d.get(key) else ([] if key != "breakdown" else {})
            except (json.JSONDecodeError, TypeError):
                d[key] = [] if key != "breakdown" else {}
        d["status"] = d.get("status") or "new"
        d["has_letter"] = bool(d.get("has_letter"))
        out.append(d)
    return out


def set_status(vacancy_id: int, status: str, note: str | None = None) -> str | None:
    """Меняет статус и возвращает дату отклика (applied_at), если она есть."""
    if status not in STATUSES:
        raise ValueError(f"недопустимый статус: {status}")
    ts = now()
    with connect() as conn:
        conn.execute(
            "INSERT INTO statuses (vacancy_id, status, note, updated_at, applied_at) "
            "VALUES (?,?,?,?,?) "
            "ON CONFLICT(vacancy_id) DO UPDATE SET status = excluded.status, "
            "note = COALESCE(excluded.note, statuses.note), updated_at = excluded.updated_at, "
            # дата отклика ставится один раз, сохраняется при отказе и сбрасывается,
            # если статус откатили назад (new/saved/hidden)
            "applied_at = CASE "
            "  WHEN excluded.status IN ('applied', 'interview') "
            "    THEN COALESCE(statuses.applied_at, excluded.applied_at) "
            "  WHEN excluded.status = 'rejected' THEN statuses.applied_at "
            "  ELSE NULL END",
            (vacancy_id, status, note, ts, ts if status in ("applied", "interview") else None),
        )
        row = conn.execute("SELECT applied_at FROM statuses WHERE vacancy_id = ?",
                           (vacancy_id,)).fetchone()
    return row["applied_at"]


def get_cover_letter(vacancy_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM cover_letters WHERE vacancy_id = ?", (vacancy_id,)).fetchone()
    return dict(row) if row else None


def save_cover_letter(vacancy_id: int, text: str, lang: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO cover_letters (vacancy_id, text, lang, created_at) VALUES (?,?,?,?) "
            "ON CONFLICT(vacancy_id) DO UPDATE SET text = excluded.text, "
            "lang = excluded.lang, created_at = excluded.created_at",
            (vacancy_id, text, lang, now()),
        )


# --------------------------------------------------------------------- прогоны

def start_run() -> int:
    with connect() as conn:
        cur = conn.execute("INSERT INTO runs (started_at) VALUES (?)", (now(),))
        return int(cur.lastrowid)


def finish_run(run_id: int, ok: bool, stats: dict[str, Any], error: str | None = None) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE runs SET finished_at = ?, ok = ?, stats = ?, error = ? WHERE id = ?",
            (now(), int(ok), json.dumps(stats, ensure_ascii=False), error, run_id),
        )


def last_run() -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        return None
    d = dict(row)
    try:
        d["stats"] = json.loads(d["stats"]) if d.get("stats") else {}
    except json.JSONDecodeError:
        d["stats"] = {}
    return d


def last_successful_run_at() -> datetime | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT finished_at FROM runs WHERE ok = 1 ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if not row or not row["finished_at"]:
        return None
    try:
        return datetime.fromisoformat(row["finished_at"])
    except ValueError:
        return None


def counts_by_tab(threshold: int, secondary: int) -> dict[str, int]:
    with connect() as conn:
        def one(sql: str, args: tuple = ()) -> int:
            return int(conn.execute(sql, args).fetchone()[0])

        visible = "COALESCE(s.status,'new') != 'hidden'"
        base = f"FROM matches m JOIN vacancies v ON v.id = m.vacancy_id LEFT JOIN statuses s ON s.vacancy_id = v.id WHERE {visible}"
        return {
            "primary":   one(f"SELECT COUNT(*) {base} AND m.score >= ?", (threshold,)),
            "secondary": one(f"SELECT COUNT(*) {base} AND m.score >= ? AND m.score < ?", (secondary, threshold)),
            "saved":     one(f"SELECT COUNT(*) {base} AND s.status = 'saved'"),
            "applied":   one(f"SELECT COUNT(*) {base} AND s.status IN ('applied','interview')"),
            "hidden":    one("SELECT COUNT(*) FROM statuses WHERE status = 'hidden'"),
            "total":     one("SELECT COUNT(*) FROM vacancies"),
        }
