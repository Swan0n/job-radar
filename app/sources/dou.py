"""jobs.dou.ua — RSS. Полное описание приходит прямо в ленте, детальная страница не нужна."""
from __future__ import annotations

import html
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import quote, urlsplit, urlunsplit

from .base import JobPost, clean, detect_remote, parse_salary

NAME = "dou.ua"
BASE = "https://jobs.dou.ua"
NEEDS_BROWSER = False

_ID_RE = re.compile(r"/vacancies/(\d+)")
# «Senior Platform Engineer в Vira Games, віддалено» — хвост после последнего « в »
_TITLE_RE = re.compile(r"^(.*?)\s+в\s+([^,]+)(?:,\s*(.*))?$")


def search_url(query: str, page: int) -> str:
    # У ленты нет постраничности: она всегда отдаёт свежий срез по запросу.
    return f"{BASE}/vacancies/feeds/?search={quote(query)}"


async def list_jobs(fetcher, query: str, page: int) -> list[JobPost]:
    if page > 1:
        return []
    from ..fetcher import get_text
    xml = await get_text(fetcher, search_url(query, page))
    return parse_feed(xml, query)


_SALARY_PART_RE = re.compile(r"\d.*([$€]|грн)|([$€]|грн).*\d", re.I)


def split_salary(location: str | None) -> tuple[str | None, str | None]:
    """
    В ленте DOU вилка стоит в заголовке после компании: «в Partner Dev, до $1500,
    віддалено». Регулярка заголовка кладёт её в локацию — вынимаем обратно.
    Возвращает (локация без вилки, вилка).
    """
    if not location:
        return location, None
    parts = [clean(html.unescape(p)) for p in location.split(",")]
    salary = [p for p in parts if _SALARY_PART_RE.search(p)]
    if not salary:
        return location, None
    rest = [p for p in parts if p not in salary]
    return (", ".join(rest) or None), clean(salary[0])


def parse_feed(xml: str | None, query: str) -> list[JobPost]:
    if not xml:
        return []
    import feedparser
    from bs4 import BeautifulSoup

    feed = feedparser.parse(xml)
    jobs: list[JobPost] = []

    for entry in feed.entries:
        link = getattr(entry, "link", "")
        m = _ID_RE.search(link)
        if not m:
            continue
        parts = urlsplit(link)
        clean_url = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))

        # лента экранирует сущности дважды: после разбора остаются «&amp;», «&nbsp;»
        raw_title = clean(html.unescape(getattr(entry, "title", "")))
        title, company, location = raw_title, None, None
        tm = _TITLE_RE.match(raw_title)
        if tm:
            title = clean(tm.group(1))
            company = clean(tm.group(2))
            location = clean(tm.group(3) or "") or None

        description = None
        if getattr(entry, "description", None):
            description = clean(BeautifulSoup(entry.description, "lxml").get_text("\n"))[:12000]

        posted = None
        if getattr(entry, "published", None):
            try:
                posted = parsedate_to_datetime(entry.published).date().isoformat()
            except (TypeError, ValueError):
                posted = None

        # Вилку берём только из заголовка: в описании «$» чаще про другое
        # («$150M Series D», «$880 млн оцінки»).
        location, salary_raw = split_salary(location)
        smin, smax, cur = parse_salary(salary_raw)

        jobs.append(JobPost(
            source=NAME,
            external_id=m.group(1),
            url=clean_url,
            title=title,
            company=company,
            location=location,
            remote=detect_remote(location, raw_title, (description or "")[:400]),
            salary_raw=salary_raw,
            salary_min=smin, salary_max=smax, salary_cur=cur,
            posted_at=posted,
            description=description,
            query=query,
        ))
    return jobs


async def fetch_detail(fetcher, job: JobPost) -> str | None:
    return job.description   # уже есть из ленты
