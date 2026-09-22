"""
LinkedIn — только публичный гостевой эндпоинт, тот же, что отдаёт вакансии
незалогиненному посетителю. Без входа в аккаунт пользователя: так его аккаунт
ничем не рискует. Источник хрупкий — LinkedIn периодически меняет разметку,
поэтому при сбое он просто выключается, не роняя остальной прогон.
"""
from __future__ import annotations

import re
from urllib.parse import quote

from .base import JobPost, clean, detect_remote, extract_text_block, parse_salary

NAME = "linkedin"
GUEST = "https://www.linkedin.com/jobs-guest/jobs/api"
NEEDS_BROWSER = False
PAGE_SIZE = 10

_URN_RE = re.compile(r"jobPosting:(\d+)")


def search_url(query: str, page: int, location: str = "Ukraine") -> str:
    start = (page - 1) * PAGE_SIZE
    return (f"{GUEST}/seeMoreJobPostings/search?keywords={quote(query)}"
            f"&location={quote(location)}&start={start}")


async def list_jobs(fetcher, query: str, page: int) -> list[JobPost]:
    from ..fetcher import get_text
    html = await get_text(fetcher, search_url(query, page))
    return parse_list(html, query)


def parse_list(html: str | None, query: str) -> list[JobPost]:
    if not html:
        return []
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    jobs: list[JobPost] = []

    for card in soup.select("div.base-card, li div.base-search-card"):
        urn = card.get("data-entity-urn") or ""
        m = _URN_RE.search(urn)
        link_el = card.select_one("a.base-card__full-link, a[href*='/jobs/view/']")
        if not link_el:
            continue
        href = (link_el.get("href") or "").split("?")[0]
        job_id = m.group(1) if m else (re.search(r"-(\d+)$", href).group(1)
                                       if re.search(r"-(\d+)$", href) else None)
        if not job_id:
            continue

        title_el = card.select_one("h3.base-search-card__title, h3")
        comp_el = card.select_one("h4.base-search-card__subtitle a, h4")
        loc_el = card.select_one("span.job-search-card__location")
        time_el = card.select_one("time")
        sal_el = card.select_one("span.job-search-card__salary-info")

        salary_raw = clean(sal_el.get_text()) if sal_el else None
        smin, smax, cur = parse_salary(salary_raw)
        location = clean(loc_el.get_text()) if loc_el else None

        jobs.append(JobPost(
            source=NAME,
            external_id=job_id,
            url=href,
            title=clean(title_el.get_text()) if title_el else "",
            company=clean(comp_el.get_text()) if comp_el else None,
            location=location,
            remote=detect_remote(location, clean(title_el.get_text()) if title_el else ""),
            salary_raw=salary_raw,
            salary_min=smin, salary_max=smax, salary_cur=cur,
            posted_at=time_el.get("datetime") if time_el else None,
            query=query,
        ))
    return [j for j in jobs if j.title]


async def fetch_detail(fetcher, job: JobPost) -> str | None:
    """Гостевой эндпоинт описания — тоже без авторизации."""
    from ..fetcher import get_text
    html = await get_text(fetcher, f"{GUEST}/jobPosting/{job.external_id}")
    return extract_text_block(html, (".show-more-less-html__markup",
                                     ".description__text", "section.description"))
