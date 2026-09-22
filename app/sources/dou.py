"""jobs.dou.ua — RSS. Полное описание приходит прямо в ленте, детальная страница не нужна."""
from __future__ import annotations

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

        raw_title = clean(getattr(entry, "title", ""))
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

        salary_raw = None
        sm = re.search(r"\$\s?\d[\d\s\-–—]*\d*", description or "")
        if sm:
            salary_raw = clean(sm.group(0))
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
