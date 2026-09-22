"""djinni.co — обычный HTTP. Карточка: div.job-item."""
from __future__ import annotations

import logging
import re
from urllib.parse import quote

from .base import (JobPost, clean, detect_remote, extract_text_block,
                   parse_relative_date, parse_salary)

log = logging.getLogger(__name__)

NAME = "djinni.co"
BASE = "https://djinni.co"
NEEDS_BROWSER = False

_ID_RE = re.compile(r"/jobs/(\d+)")
_SALARY_RE = re.compile(r"\$\s?\d[\d\s\-–—to]*\d*|\$+")


# Djinni ищет не по свободному тексту, а по своему справочнику специализаций:
# неизвестный слаг он молча игнорирует и отдаёт вообще все вакансии. Пары ниже
# проверены запросами к сайту; порядок важен — сначала более частные совпадения.
KEYWORD_MAP: tuple[tuple[str, str], ...] = (
    ("qa automation", "qa_automation"), ("automation qa", "qa_automation"),
    ("aqa", "qa_automation"), ("manual qa", "qa_manual"), ("qa manual", "qa_manual"),
    ("data scien", "data_science"), ("machine learning", "data_science"),
    ("data analyst", "data_analyst"), ("data engineer", "data_engineer"),
    ("product manager", "product_manager"), ("product owner", "product_manager"),
    ("project manager", "project_manager"), ("delivery manager", "project_manager"),
    ("business analyst", "business_analyst"), ("system analyst", "business_analyst"),
    ("node", "node_js"), ("devops", "dev_ops"), ("sre", "dev_ops"),
    ("django", "python"), ("flask", "python"), ("fastapi", "python"), ("python", "python"),
    ("spring", "java"), ("java", "java"),
    ("typescript", "javascript"), ("javascript", "javascript"),
    ("react", "react"), ("golang", "golang"), ("laravel", "php"), ("php", "php"),
    ("dotnet", "dotnet"), (".net", "dotnet"), ("c#", "dotnet"),
    ("rails", "ruby"), ("ruby", "ruby"), ("rust", "rust"), ("kotlin", "kotlin"),
    ("flutter", "flutter"), ("scala", "scala"), ("android", "android"),
    ("swift", "ios"), ("ios", "ios"), ("unity", "unity"), ("c++", "cpp"),
    ("embedded", "embedded"), ("gamedev", "gamedev"), ("game", "gamedev"),
    ("security", "security"), ("infosec", "security"),
    ("architect", "architect"), ("tech lead", "lead"), ("team lead", "lead"),
    ("design", "design"), ("ui/ux", "design"), ("marketing", "marketing"),
    ("sales", "sales"), ("recruit", "hr"), ("support", "support"),
    ("database", "sql_dba"), ("dba", "sql_dba"), ("sql", "sql_dba"),
    ("analyst", "data_analyst"), ("\bqa\b", "qa_manual"), ("\bhr\b", "hr"),
    ("\bgo\b", "golang"), ("\bml\b", "data_science"), ("\blead\b", "lead"),
)


def to_keyword(query: str) -> str | None:
    """Свободный запрос -> слаг Djinni. None означает «такой специализации у них нет»."""
    text = query.lower().strip()
    for needle, slug in KEYWORD_MAP:
        if needle.startswith("\\b"):
            if re.search(needle, text):
                return slug
        elif needle in text:
            return slug
    return None


def search_url(query: str, page: int) -> str:
    keyword = to_keyword(query)
    path = f"{BASE}/jobs/keyword-{keyword}/" if keyword else f"{BASE}/jobs/"
    return path + (f"?page={page}" if page > 1 else "")


async def list_jobs(fetcher, query: str, page: int) -> list[JobPost]:
    from ..fetcher import get_text
    if to_keyword(query) is None:
        # Иначе Djinni вернул бы весь свой список без фильтра, и мы бы
        # потратили токены на оценку заведомо чужих вакансий.
        log.info("djinni: «%s» не ложится на их справочник специализаций — пропускаю", query)
        return []
    html = await get_text(fetcher, search_url(query, page))
    return parse_list(html, query)


def parse_list(html: str | None, query: str) -> list[JobPost]:
    if not html:
        return []
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    jobs: list[JobPost] = []

    for card in soup.select("div.job-item"):
        link = card.select_one("a.job_item__header-link")
        if not link:
            continue
        href = link.get("href", "")
        m = _ID_RE.search(href)
        if not m:
            continue

        title_el = card.select_one("h2.job-item__position, h2")
        title = clean(title_el.get_text()) if title_el else clean(link.get_text())

        # В шапке карточки по порядку: название, компания, вилка.
        header = card.select_one("header") or card
        comp_el = header.select_one("span.font-weight-500, span.small.text-gray-800")
        company = clean(comp_el.get_text()) if comp_el else None

        sal_el = header.select_one("span.text-body-tertiary")
        sal_text = clean(sal_el.get_text()) if sal_el else ""
        # «$$$$» — это скрытая вилка, а не сумма: числа в ней нет.
        salary_raw = sal_text if any(c.isdigit() for c in sal_text) else None

        card_text = clean(card.get_text(" "))
        # «6 років досвіду», «Англійська — B2» пригодятся при оценке совпадения.
        meta = [clean(s.get_text()) for s in card.select("span.text-nowrap")]

        loc_el = card.select_one("span.location-text, .job-item__country")
        location = clean(loc_el.get_text()) if loc_el else None
        if not location:
            m_loc = re.search(r"(Тільки віддалено|Віддалено|Офіс|Гібрид)[^·]*", card_text, re.I)
            location = clean(m_loc.group(0)) if m_loc else None

        date_el = card.select_one("span.mr-2.nobr, span[title]")
        posted = parse_relative_date(clean(date_el.get_text()) if date_el else None)

        smin, smax, cur = parse_salary(salary_raw)
        jobs.append(JobPost(
            source=NAME,
            external_id=m.group(1),
            url=f"{BASE}{href}" if href.startswith("/") else href,
            title=title,
            company=company,
            location=location,
            remote=detect_remote(location, card_text[:400]),
            salary_raw=salary_raw,
            salary_min=smin, salary_max=smax, salary_cur=cur or ("USD" if salary_raw else None),
            posted_at=posted,
            description=" · ".join(meta) or None,
            query=query,
        ))
    return jobs


async def fetch_detail(fetcher, job: JobPost) -> str | None:
    from ..fetcher import get_text
    html = await get_text(fetcher, job.url)
    return extract_text_block(html, (".job-post__description", ".job-post-description",
                                     "div.mb-4.job-post__description", "[class*='description']"))
