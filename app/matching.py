"""
Сборка итогового процента. Навыки, опыт и домен оценивает модель, а условия
(формат, город, деньги) считаются здесь: они проверяемы арифметикой, и это
делает итоговую цифру объяснимой — в карточке видно, из чего она сложилась.
"""
from __future__ import annotations

import re
from typing import Any

from .config import Settings
from .sources.base import detect_format, to_usd

# Дешёвый отсев до обращения к модели: экономит и токены, и время.
JUNIOR_MARKERS = ("junior", "trainee", "intern", "стажер", "стажист", "початків")
SENIOR_MARKERS = ("senior", "lead", "head of", "principal", "staff", "director", "керівник")
SENIORITY_ORDER = {"junior": 1, "middle": 2, "senior": 3, "lead": 4, "head": 5}

# Слова, которые встречаются в названиях любых вакансий и ничего не говорят
# о специализации. Если запрос состоит только из них, опоры для отсева нет.
GENERIC_WORDS = {
    "engineer", "engineering", "developer", "development", "specialist", "expert",
    "senior", "middle", "junior", "lead", "head", "principal", "staff", "manager",
    "інженер", "инженер", "розробник", "разработчик", "спеціаліст", "специалист",
    "фахівець", "менеджер", "and", "the", "for", "with",
}

# Английские корни из запросов и их украинские/русские формы в названиях вакансий.
TRANSLATIONS = {
    "infrastructure": ("інфраструктур", "инфраструктур"),
    "cloud": ("хмарн", "облачн"),
    "platform": ("платформ",),
    "security": ("безпек", "безопасн"),
    "support": ("підтримк", "поддержк"),
    "network": ("мереж", "сетев"),
    "database": ("баз дан", "баз данн"),
    "system": ("системн",),
}

# Короткие технические токены, которые иначе отсеялись бы по длине.
SHORT_TECH = {"aws", "gcp", "sql", "k8s", "eks", "gke", "aks", "sre", "php", "git", "ios", "qa"}

_TOKEN_RE = re.compile(r"[a-zа-яіїєґ0-9+#.]+", re.I)


def relevance_anchors(queries: list[str], profile: dict[str, Any]) -> set[str]:
    """
    Профильные слова, хотя бы одно из которых должно быть в названии.
    Берутся из всех запросов сразу, а не из того, которым нашли вакансию:
    «Infrastructure Support Engineer», найденная по «SRE Engineer», всё равно
    интересна, если среди запросов есть «Infrastructure Engineer».
    """
    anchors: set[str] = set()

    def take(text: str) -> None:
        for token in _TOKEN_RE.findall(text.lower()):
            token = token.strip(".")
            if token in GENERIC_WORDS:
                continue
            if len(token) >= 4 or token in SHORT_TECH:
                anchors.add(token)
                anchors.update(TRANSLATIONS.get(token, ()))

    for query in queries:
        take(query or "")
    structured = profile.get("structured") or {}
    for skill in structured.get("skills") or []:
        take(skill)
    take(structured.get("headline") or "")
    return anchors


def title_is_relevant(title: str, anchors: set[str]) -> bool:
    if not anchors:
        return True                      # опоры нет — не рискуем, пропускаем к модели
    low = title.lower()
    return any(a in low for a in anchors)


def prefilter(vacancy: dict[str, Any], settings: Settings,
              profile: dict[str, Any]) -> tuple[bool, str]:
    """(пропустить_дальше, причина_отказа). Отсекает только очевидное."""
    title = (vacancy.get("title") or "").lower()

    for word in settings.exclude_keywords:
        if word.strip() and word.strip().lower() in title:
            return False, f"стоп-слово «{word}»"

    # Общие борды ищут по словам, а не по смыслу: на «SRE Engineer» они отдают
    # «Інженер-конструктор». Такие названия отсекаем до платной оценки.
    from .sources import REGISTRY
    source = REGISTRY.get(vacancy.get("source") or "")
    if source is not None and getattr(source, "GENERAL_BOARD", False):
        queries = settings.queries or (profile.get("structured") or {}).get("target_roles") or []
        if not title_is_relevant(title, relevance_anchors(queries, profile)):
            return False, "в названии нет ни одного профильного слова"

    grade = (profile.get("structured") or {}).get("seniority", "").lower()
    my_level = SENIORITY_ORDER.get(grade, 0)
    if my_level >= 3 and any(m in title for m in JUNIOR_MARKERS):
        return False, "джуниорская позиция при senior-грейде"
    if my_level and my_level <= 2 and any(m in title for m in SENIOR_MARKERS):
        return False, "позиция сильно выше грейда"

    return True, ""


# Подписи для чипов условий. Пишутся в БД вместе с оценкой, поэтому язык —
# тот, что был выбран в интерфейсе в момент оценки.
COND_TEXT = {
    "ru": {"formats": {"remote": "Удалённо", "hybrid": "Гибрид", "office": "Офис"},
           "bad_format": "формат «{fmt}» не подходит", "city_ok": "город подходит",
           "city": "город: {loc}", "salary": "зарплата {sal}",
           "salary_low": "зарплата ниже ориентира: {sal}"},
    "uk": {"formats": {"remote": "Віддалено", "hybrid": "Гібрид", "office": "Офіс"},
           "bad_format": "формат «{fmt}» не підходить", "city_ok": "місто підходить",
           "city": "місто: {loc}", "salary": "зарплата {sal}",
           "salary_low": "зарплата нижче орієнтира: {sal}"},
    "en": {"formats": {"remote": "Remote", "hybrid": "Hybrid", "office": "Office"},
           "bad_format": "{fmt} format doesn't fit", "city_ok": "city fits",
           "city": "city: {loc}", "salary": "salary {sal}",
           "salary_low": "salary below target: {sal}"},
}


def conditions_score(vacancy: dict[str, Any], settings: Settings) -> tuple[float, list[str], list[str]]:
    """Возвращает (оценка 0-100, что совпало, что не так)."""
    txt = COND_TEXT.get(settings.ui_lang, COND_TEXT["ru"])
    good: list[str] = []
    bad: list[str] = []
    parts: list[float] = []

    # --- формат работы ---
    fmt = "remote" if vacancy.get("remote") else detect_format(
        vacancy.get("location"), (vacancy.get("description") or "")[:600]
    )
    wanted = settings.work_formats or ["remote", "hybrid", "office"]
    if fmt in wanted:
        parts.append(100.0)
        good.append(txt["formats"][fmt])
    else:
        parts.append(15.0)
        bad.append(txt["bad_format"].format(fmt=txt["formats"][fmt].lower()))

    # --- город (для удалёнки не важен) ---
    if fmt == "remote" or not settings.cities:
        parts.append(100.0)
    else:
        location = (vacancy.get("location") or "").lower()
        if any(_city_matches(c, location) for c in settings.cities):
            parts.append(100.0)
            good.append(vacancy.get("location") or txt["city_ok"])
        elif not location:
            parts.append(60.0)
        else:
            parts.append(25.0)
            bad.append(txt["city"].format(loc=vacancy.get("location")))

    # --- деньги: мягкий фильтр, вакансия не прячется ---
    floor = settings.min_salary_usd()
    if not floor:
        parts.append(100.0)
    else:
        top = to_usd(vacancy.get("salary_max") or vacancy.get("salary_min"),
                     vacancy.get("salary_cur"), settings.uah_per_usd)
        if top is None:
            parts.append(65.0)                       # вилка не указана — большинство вакансий в Украине
        elif top >= floor:
            parts.append(100.0)
            good.append(txt["salary"].format(sal=vacancy.get("salary_raw")))
        else:
            ratio = max(0.0, top / floor)
            parts.append(max(10.0, ratio * 70))
            bad.append(txt["salary_low"].format(sal=vacancy.get("salary_raw")))

    return sum(parts) / len(parts), good, bad


def _city_matches(city: str, location: str) -> bool:
    city = city.strip().lower()
    if not city:
        return False
    # «Киев» и «Київ» — один и тот же город
    variants = {city}
    for ru, ua in (("киев", "київ"), ("львов", "львів"), ("харьков", "харків"),
                   ("одесса", "одеса"), ("днепр", "дніпро")):
        if city in (ru, ua):
            variants |= {ru, ua}
    return any(v in location for v in variants)


def combine(llm_score, conditions: float, settings: Settings) -> tuple[float, dict[str, float]]:
    """Складывает четыре измерения по весам из настроек."""
    w = settings.normalized_weights()
    breakdown = {
        "skills": float(_clamp(llm_score.skills_score)),
        "experience": float(_clamp(llm_score.experience_score)),
        "domain": float(_clamp(llm_score.domain_score)),
        "conditions": round(conditions, 1),
    }
    total = sum(breakdown[k] * w[k] for k in w)
    return round(total, 1), breakdown


def _clamp(value: Any) -> int:
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return 0
