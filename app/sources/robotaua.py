"""robota.ua — Angular за Cloudflare. Карточка: alliance-vacancy-card-desktop."""
from __future__ import annotations

import re
from urllib.parse import quote

from .base import (JobPost, clean, detect_remote, extract_text_block,
                   parse_salary)

NAME = "robota.ua"
BASE = "https://robota.ua"
NEEDS_BROWSER = True
# Общий борд со всеми профессиями: его поиск ловит любое «інженер»
GENERAL_BOARD = True

_ID_RE = re.compile(r"/company(\d+)/vacancy(\d+)")
_MONEY_RE = re.compile(r"грн|₴|\$|€", re.I)
_SKIP_SPANS = ("відгукнутись", "увійдіть", "зареєструйтесь", "компанія з відзнакою")


def search_url(query: str, page: int) -> str:
    # Слова в слаге разделяются плюсом: с «%20» или дефисом поиск молча
    # игнорирует второе слово и выдаёт нерелевантное.
    slug = quote(query.strip().replace(" ", "+"), safe="+")
    return f"{BASE}/zapros/{slug}/ukraine" + (f"?page={page}" if page > 1 else "")


async def list_jobs(fetcher, query: str, page: int) -> list[JobPost]:
    html = await fetcher.get_html(
        search_url(query, page), wait_selector="alliance-vacancy-card-desktop"
    )
    return parse_list(html, query)


def parse_list(html: str | None, query: str) -> list[JobPost]:
    if not html:
        return []
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    jobs: list[JobPost] = []

    for card in soup.select("alliance-vacancy-card-desktop"):
        link = card.select_one("a[href*='/vacancy']")
        title_el = card.select_one("h2")
        if not link or not title_el:
            continue
        m = _ID_RE.search(link.get("href", ""))
        if not m:
            continue

        badges = {clean(b.get_text()).lower()
                  for b in card.select("alliance-vac-list-status-label")}

        # Компания живёт в span.santa-mr-20, город — в span, внутри которого
        # лежит пометка «(віддалено)», зарплата — единственный span с валютой.
        comp_el = card.select_one("span.santa-mr-20")
        company = clean(comp_el.get_text()) if comp_el else None

        location = None
        for span in card.select("span"):
            text = clean(span.get_text())
            if text and ("(віддалено)" in text.lower() or "(удаленно)" in text.lower()):
                if text.lower() != "(віддалено)":
                    location = text
                    break
                parent = span.parent
                if parent is not None:
                    location = clean(parent.get_text())
                    break
        if location:
            location = location.replace("(віддалено)", " (віддалено)").strip()

        salary_raw = None
        for span in card.select("span"):
            text = clean(span.get_text())
            low = text.lower()
            if not text or any(s in low for s in _SKIP_SPANS) or text == company:
                continue
            if _MONEY_RE.search(text) and any(ch.isdigit() for ch in text):
                salary_raw = text
                break

        smin, smax, cur = parse_salary(salary_raw)
        jobs.append(JobPost(
            source=NAME,
            external_id=m.group(2),
            url=f"{BASE}/company{m.group(1)}/vacancy{m.group(2)}",
            title=clean(title_el.get_text()),
            company=company,
            location=location,
            remote=detect_remote(location, " ".join(badges)),
            salary_raw=salary_raw,
            salary_min=smin, salary_max=smax, salary_cur=cur,
            query=query,
        ))
    return jobs


async def fetch_detail(fetcher, job: JobPost) -> str | None:
    html = await fetcher.get_html(job.url, wait_selector="alliance-vacancy-description, .santa-typo-regular")
    return extract_text_block(html, ("alliance-vacancy-description",
                                     "[id*='description']", ".santa-mb-40"))
