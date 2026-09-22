"""Общая модель вакансии и разбор «грязных» полей из разметки сайтов."""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from typing import Any

# Сайты щедры на неразрывные и тонкие пробелы внутри чисел.
SPACES = "    ⁠"
_SPACE_RE = re.compile(f"[{SPACES}]")

REMOTE_MARKERS = (
    "дистанційно", "дистанционно", "віддалено", "удалённо", "удаленно",
    "remote", "тільки віддалено", "work from home", "повністю віддалено",
)
HYBRID_MARKERS = ("гібрид", "гибрид", "hybrid", "змішаний")


@dataclass
class JobPost:
    source: str
    external_id: str
    url: str
    title: str
    company: str | None = None
    location: str | None = None
    remote: bool = False
    salary_raw: str | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_cur: str | None = None
    posted_at: str | None = None          # ISO-строка
    description: str | None = None
    query: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["remote"] = int(self.remote)
        return d


def clean(text: str | None) -> str:
    """Схлопывает пробелы и убирает типографский мусор."""
    if not text:
        return ""
    text = _SPACE_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def detect_remote(*chunks: str | None) -> bool:
    blob = " ".join(clean(c).lower() for c in chunks if c)
    return any(m in blob for m in REMOTE_MARKERS)


def detect_format(*chunks: str | None) -> str:
    """remote | hybrid | office — как сайт описывает формат работы."""
    blob = " ".join(clean(c).lower() for c in chunks if c)
    if any(m in blob for m in HYBRID_MARKERS):
        return "hybrid"
    if any(m in blob for m in REMOTE_MARKERS):
        return "remote"
    return "office"


_CUR_PATTERNS = [
    (re.compile(r"грн|₴|uah", re.I), "UAH"),
    (re.compile(r"\$|usd|долар|долл", re.I), "USD"),
    (re.compile(r"€|eur|євро|евро", re.I), "EUR"),
]


def parse_salary(raw: str | None) -> tuple[float | None, float | None, str | None]:
    """
    Достаёт вилку из строк вида «130 000 – 220 000 грн», «$3000-5000», «від 40000 грн».
    Возвращает (min, max, валюта). Djinni-шные «$$$$» — это скрытая вилка, не число.
    """
    if not raw:
        return None, None, None
    text = clean(raw)
    if not text or re.fullmatch(r"\$+", text):
        return None, None, None

    currency = None
    for pattern, code in _CUR_PATTERNS:
        if pattern.search(text):
            currency = code
            break

    # числа от 3 знаков: зарплаты меньше 100 в любой валюте нам не интересны
    numbers = [float(n) for n in re.findall(r"\d{3,7}", text.replace(" ", ""))]
    numbers = [n for n in numbers if n >= 100]
    if not numbers:
        return None, None, currency

    if len(numbers) == 1:
        # «від 40000» — нижняя граница, «до 40000» — верхняя
        if re.search(r"\bдо\b|\bup to\b", text, re.I):
            return None, numbers[0], currency
        return numbers[0], None, currency
    return min(numbers), max(numbers), currency


def to_usd(amount: float | None, currency: str | None, uah_per_usd: float) -> float | None:
    if amount is None:
        return None
    cur = (currency or "").upper()
    if cur == "UAH":
        return amount / max(uah_per_usd, 1.0)
    if cur == "EUR":
        return amount * 1.08
    return amount


_REL_RE = re.compile(r"(\d+)\s*(хвилин|минут|годин|час|день|дн|дня|днів|тижн|недел|місяц|месяц)", re.I)


def parse_relative_date(text: str | None) -> str | None:
    """«2 години тому», «3 дні тому» → ISO-дата. Нужна там, где нет машинной даты."""
    if not text:
        return None
    t = clean(text).lower()
    now = datetime.now(timezone.utc)
    if "сьогодні" in t or "сегодня" in t or "today" in t:
        return now.date().isoformat()
    if "вчора" in t or "вчера" in t or "yesterday" in t:
        return (now - timedelta(days=1)).date().isoformat()
    m = _REL_RE.search(t)
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    delta = {
        "хвилин": timedelta(minutes=n), "минут": timedelta(minutes=n),
        "годин": timedelta(hours=n), "час": timedelta(hours=n),
        "день": timedelta(days=n), "дн": timedelta(days=n),
        "дня": timedelta(days=n), "днів": timedelta(days=n),
        "тижн": timedelta(weeks=n), "недел": timedelta(weeks=n),
        "місяц": timedelta(days=30 * n), "месяц": timedelta(days=30 * n),
    }.get(unit, timedelta())
    return (now - delta).date().isoformat()


def is_fresh(posted_at: str | None, max_age_days: int) -> bool:
    """Нет даты — считаем свежей: лучше лишняя вакансия, чем потерянная."""
    if not posted_at:
        return True
    try:
        d = datetime.fromisoformat(posted_at.replace("Z", "+00:00"))
    except ValueError:
        return True
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - d).days <= max_age_days


# ------------------------------------------------------- извлечение описания

_JUNK_TAGS = ("script", "style", "nav", "header", "footer", "noscript", "form", "svg")


def extract_text_block(html: str | None, selectors: tuple[str, ...]) -> str | None:
    """
    Тянет текст описания по списку селекторов, а если ни один не подошёл —
    берёт самый «мясистый» блок страницы. Вёрстка сайтов меняется,
    и жёсткая привязка к одному селектору ломает парсер целиком.
    """
    if not html:
        return None
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    for tag in soup(list(_JUNK_TAGS)):
        tag.decompose()

    for sel in selectors:
        node = soup.select_one(sel)
        if node:
            text = node.get_text("\n", strip=True)
            if len(text) > 120:
                return _tidy(text)

    best, best_len = None, 0
    for node in soup.select("div, section, article"):
        if len(node.find_all(["div", "section", "article"])) > 3:
            continue
        text = node.get_text("\n", strip=True)
        if len(text) > best_len:
            best, best_len = text, len(text)
    return _tidy(best) if best and best_len > 120 else None


def _tidy(text: str) -> str:
    lines = [_SPACE_RE.sub(" ", ln).strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    return "\n".join(lines)[:12000]
