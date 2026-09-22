"""work.ua — за Cloudflare, ходим браузером. Карточка списка: div.job-link."""
from __future__ import annotations

import re
from urllib.parse import quote

from .base import (JobPost, clean, detect_remote, extract_text_block,
                   parse_salary)

NAME = "work.ua"
BASE = "https://www.work.ua"
NEEDS_BROWSER = True
# Общий борд со всеми профессиями: его поиск ловит любое «інженер»
GENERAL_BOARD = True

_ID_RE = re.compile(r"/jobs/(\d+)")
_MONEY_RE = re.compile(r"грн|₴|\$|€|usd|eur", re.I)


def search_url(query: str, page: int) -> str:
    return f"{BASE}/jobs/?search={quote(query)}" + (f"&page={page}" if page > 1 else "")


async def list_jobs(fetcher, query: str, page: int) -> list[JobPost]:
    html = await fetcher.get_html(search_url(query, page), wait_selector="div.job-link")
    return parse_list(html, query)


def parse_list(html: str | None, query: str) -> list[JobPost]:
    if not html:
        return []
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    jobs: list[JobPost] = []

    for card in soup.select("div.job-link"):
        link = card.select_one("h2 a[href*='/jobs/']")
        if not link:
            continue
        href = link.get("href", "")
        m = _ID_RE.search(href)
        if not m:
            continue

        # Карточка делит поля по классам: строки без mt-sm — это зарплата и
        # компания, строки с mt-sm — формат/город, опыт и прочие пометки.
        head = [clean(d.get_text(" ")) for d in card.select("div.text-indent")
                if "mt-sm" not in (d.get("class") or [])]
        tail = [clean(d.get_text(" ")) for d in card.select("div.text-indent.mt-sm")]

        # Блок без mt-sm — это либо [зарплата, компания], либо только [компания].
        # Строка про деньги не всегда содержит число: там бывает
        # «За результатами співбесіди», и её нельзя принимать за название компании.
        company = head[-1] if head else None
        salary_line = head[0] if len(head) > 1 else None
        salary_raw = None
        if salary_line and any(c.isdigit() for c in salary_line):
            # «40 500 – 49 000 грн · Після всіх відрахувань» — пояснение в карточке лишнее
            salary_raw = salary_line.split("·")[0].strip()
        if company:
            company = re.sub(r"\s*,\s*(Агенція|Агентство)\s*$", "", company).strip()

        location = tail[0] if tail else None
        extra = " · ".join(tail[1:]) if len(tail) > 1 else ""

        smin, smax, cur = parse_salary(salary_raw)
        jobs.append(JobPost(
            source=NAME,
            external_id=m.group(1),
            url=f"{BASE}/jobs/{m.group(1)}/",
            title=clean(link.get_text()),
            company=company,
            location=location,
            remote=detect_remote(location, extra),
            salary_raw=salary_raw,
            salary_min=smin, salary_max=smax, salary_cur=cur,
            description=extra or None,   # до загрузки детальной страницы
            query=query,
        ))
    return jobs


async def fetch_detail(fetcher, job: JobPost) -> str | None:
    html = await fetcher.get_html(job.url, wait_selector="#job-description, .card-hover")
    return extract_text_block(html, ("#job-description", "div#job-description",
                                     ".card.card-indent", "div[id='job-description']"))
