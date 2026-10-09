"""Слой Claude: разбор резюме, оценка совпадения, кавер-леттеры."""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

# Оценка вакансий — массовая операция, письма — штучная и качественная.
# Обе модели меняются в настройках, если захочется дешевле.
DEFAULT_SCORING_MODEL = "claude-sonnet-5"
DEFAULT_LETTER_MODEL = "claude-sonnet-5"

_client = None


def client():
    global _client
    if _client is None:
        import anthropic
        # Пробелы и переносы строк вокруг ключа дают 401 «API key is invalid».
        key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip() or None
        _client = anthropic.AsyncAnthropic(api_key=key)
    return _client


PLACEHOLDERS = {"", "sk-ant-...", "your-api-key", "sk-ant-xxx"}


def has_api_key() -> bool:
    """Заглушка из .env.example — это отсутствие ключа, а не ключ."""
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        value = (os.environ.get(name) or "").strip()
        if value and value not in PLACEHOLDERS and not value.endswith("..."):
            return True
    return False


# --------------------------------------------------------------- схемы ответа

class ResumeProfile(BaseModel):
    full_name: str | None = None
    headline: str = Field(description="Роль одной строкой, например «Senior Python Developer»")
    years_experience: float = Field(description="Суммарный релевантный опыт в годах")
    seniority: str = Field(description="junior | middle | senior | lead | head")
    skills: list[str] = Field(description="Технологии и инструменты из резюме")
    domains: list[str] = Field(description="Индустрии: финтех, e-commerce, геймдев и т.д.")
    languages: list[str] = Field(description="Языки с уровнем, например «English B2»")
    target_roles: list[str] = Field(description="3-6 поисковых запросов для джоб-бордов")
    summary: str = Field(description="2-3 предложения о кандидате, по-русски")


class VacancyScore(BaseModel):
    ref: str = Field(description="Идентификатор вакансии из запроса, без изменений")
    skills_score: int = Field(description="0-100: покрытие требований навыками кандидата")
    experience_score: int = Field(description="0-100: соответствие грейду и годам опыта")
    domain_score: int = Field(description="0-100: близость индустрии")
    matched: list[str] = Field(description="До 6 совпадений, коротко, на языке из инструкции")
    missing: list[str] = Field(description="До 4 нехваток, коротко, на языке из инструкции")
    red_flags: list[str] = Field(description="Тревожные сигналы: неоплачиваемый тест, серая схема и т.п.")
    summary: str = Field(description="Одно предложение-вердикт на языке из инструкции")
    vacancy_language: str = Field(description="Язык текста вакансии: uk | ru | en")


class BatchScores(BaseModel):
    results: list[VacancyScore]


# ---------------------------------------------------------------- разбор резюме

RESUME_SYSTEM = """Ты разбираешь резюме соискателя и превращаешь его в структурированный профиль.
Считай только реальный релевантный опыт: учёба и пет-проекты в years_experience не входят.
В target_roles дай запросы так, как их вбивают в поиск на джоб-бордах Украины
(work.ua, robota.ua, djinni.co, dou.ua) — коротко, без грейда, и на том языке,
на котором такие вакансии обычно публикуют."""


async def parse_resume(raw_text: str, model: str = DEFAULT_SCORING_MODEL) -> dict[str, Any]:
    resp = await client().messages.parse(
        model=model,
        max_tokens=4000,
        system=RESUME_SYSTEM,
        messages=[{"role": "user", "content": f"Текст резюме:\n\n{raw_text[:40000]}"}],
        output_format=ResumeProfile,
    )
    return resp.parsed_output.model_dump()


# ------------------------------------------------------------------- оценка

SCORING_SYSTEM = """Ты оцениваешь, насколько вакансии подходят конкретному кандидату.

Три независимые оценки на каждую вакансию, от 0 до 100:
- skills_score: какая доля требований закрыта опытом кандидата. Родственный стек
  засчитывай частично (Django вместо FastAPI — это почти совпадение, а Java вместо
  Python — нет).
- experience_score: соответствие грейду и годам. Кандидат сильно выше требований —
  это тоже минус: такие вакансии ему неинтересны, ставь не выше 60.
- domain_score: близость индустрии. Нет данных об индустрии — ставь 50.

Будь честным и придирчивым. Завышенные оценки вредят: кандидат потратит время на
отклик, который никуда не приведёт. Если в вакансии требуется то, чего у кандидата
нет совсем, это должно ронять skills_score, а не прятаться в missing.

matched, missing, red_flags и summary пиши {lang} и по делу, без воды.
Поле ref копируй из запроса в точности."""


def _profile_block(profile: dict[str, Any]) -> str:
    s = profile.get("structured") or {}
    parts = [
        f"Роль: {s.get('headline', '—')}",
        f"Грейд: {s.get('seniority', '—')}, опыт {s.get('years_experience', '—')} лет",
        f"Навыки: {', '.join(s.get('skills') or []) or '—'}",
        f"Индустрии: {', '.join(s.get('domains') or []) or '—'}",
        f"Языки: {', '.join(s.get('languages') or []) or '—'}",
        f"Кратко: {s.get('summary', '—')}",
        "",
        "Полный текст резюме:",
        (profile.get("raw_text") or "")[:20000],
    ]
    return "\n".join(parts)


def _vacancy_block(v: dict[str, Any], max_desc: int = 3000) -> str:
    desc = (v.get("description") or "").strip()[:max_desc]
    return "\n".join([
        f"<вакансия ref=\"{v['id']}\">",
        f"Должность: {v.get('title')}",
        f"Компания: {v.get('company') or '—'}",
        f"Локация: {v.get('location') or '—'}",
        f"Зарплата: {v.get('salary_raw') or 'не указана'}",
        f"Источник: {v.get('source')}",
        f"Описание: {desc or 'описание не загрузилось'}",
        "</вакансия>",
    ])


# в каком виде язык подставляется в SCORING_SYSTEM
SCORING_LANG = {"ru": "по-русски", "uk": "по-украински", "en": "по-английски"}


async def score_vacancies(profile: dict[str, Any], vacancies: list[dict[str, Any]],
                          model: str = DEFAULT_SCORING_MODEL,
                          effort: str = "low", lang: str = "ru") -> list[VacancyScore]:
    """Оценивает пачку вакансий одним запросом. Профиль кэшируется между вызовами."""
    if not vacancies:
        return []

    blocks = "\n\n".join(_vacancy_block(v) for v in vacancies)
    resp = await client().messages.parse(
        model=model,
        max_tokens=16000,
        system=[
            {"type": "text", "text": SCORING_SYSTEM.replace(
                "{lang}", SCORING_LANG.get(lang, SCORING_LANG["ru"]))},
            # Профиль одинаков во всех запросах прогона — держим его в кэше.
            {"type": "text", "text": f"Профиль кандидата:\n{_profile_block(profile)}",
             "cache_control": {"type": "ephemeral"}},
        ],
        messages=[{"role": "user", "content":
                   f"Оцени {len(vacancies)} вакансий. Верни ровно по одному результату на каждую.\n\n{blocks}"}],
        output_config={"effort": effort},
        output_format=BatchScores,
    )
    return resp.parsed_output.results


# ------------------------------------------------------------- кавер-леттер

LETTER_SYSTEM = """Ты пишешь сопроводительное письмо от лица кандидата под конкретную вакансию.

Требования:
- Пиши на языке вакансии: украинская — украинским, английская — английским, русская — русским.
- 140-200 слов. Три абзаца: зачем пишешь и чем зацепила вакансия; два-три конкретных
  факта из опыта, отвечающих её требованиям; короткое завершение с готовностью обсудить.
- Опирайся только на факты из резюме. Не выдумывай компании, цифры и достижения.
- Никаких «Уважаемый HR-менеджер», «командный игрок», «стрессоустойчивый» и прочих штампов.
- Если чего-то из требований у кандидата нет, не ври и не извиняйся — просто не упоминай.
- Верни только текст письма, без темы, подписи и пояснений."""


async def write_cover_letter(profile: dict[str, Any], vacancy: dict[str, Any],
                             model: str = DEFAULT_LETTER_MODEL,
                             extra_hint: str | None = None) -> str:
    user = [
        f"Вакансия:\n{_vacancy_block(vacancy, max_desc=6000)}",
        f"\nКандидат:\n{_profile_block(profile)}",
    ]
    if extra_hint:
        user.append(f"\nДополнительно учти: {extra_hint}")

    async with client().messages.stream(
        model=model,
        max_tokens=2000,
        system=[
            {"type": "text", "text": LETTER_SYSTEM},
            {"type": "text", "text": f"Профиль кандидата:\n{_profile_block(profile)}",
             "cache_control": {"type": "ephemeral"}},
        ],
        messages=[{"role": "user", "content": "\n".join(user)}],
        output_config={"effort": "medium"},
    ) as stream:
        msg = await stream.get_final_message()

    return "\n".join(b.text for b in msg.content if b.type == "text").strip()
