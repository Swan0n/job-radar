"""Два способа ходить в сеть: обычный HTTP и настоящий браузер для сайтов за Cloudflare."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36")

HTTP_HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "uk-UA,uk;q=0.9,ru;q=0.8,en-US;q=0.7,en;q=0.6",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Upgrade-Insecure-Requests": "1",
}

# Профиль браузера живёт между запусками: полученный от Cloudflare cookie
# переиспользуется, поэтому челлендж проходится редко.
PROFILE_DIR = Path(__file__).resolve().parent.parent / "data" / "browser_profile"


@asynccontextmanager
async def http_client(timeout: float = 30.0):
    async with httpx.AsyncClient(
        headers=HTTP_HEADERS, timeout=timeout, follow_redirects=True, http2=False
    ) as client:
        yield client


async def get_text(client: httpx.AsyncClient, url: str, *, retries: int = 2,
                   pause: float = 1.0, **kwargs) -> str | None:
    """GET с мягкими повторами. None означает «не смогли», а не «пусто»."""
    for attempt in range(retries + 1):
        try:
            r = await client.get(url, **kwargs)
            if r.status_code == 200:
                return r.text
            if r.status_code in (403, 429, 503):
                log.warning("%s ответил %s (попытка %s)", url, r.status_code, attempt + 1)
                await asyncio.sleep(pause * (attempt + 2))
                continue
            log.warning("%s ответил %s", url, r.status_code)
            return None
        except (httpx.HTTPError, asyncio.TimeoutError) as e:
            log.warning("%s: %s", url, type(e).__name__)
            await asyncio.sleep(pause * (attempt + 1))
    return None


class Browser:
    """
    Один headless-Chromium на весь прогон. Открывать/закрывать его на каждую
    страницу дорого, а Cloudflare ещё и выдаёт новый челлендж каждому новому профилю.
    """

    def __init__(self) -> None:
        self._pw = None
        self._ctx = None

    async def start(self) -> None:
        if self._ctx is not None:
            return
        from playwright.async_api import async_playwright

        PROFILE_DIR.mkdir(parents=True, exist_ok=True)
        self._pw = await async_playwright().start()
        # channel="chromium" — полный браузер, а не headless-shell: последний
        # Cloudflare определяет заметно чаще.
        self._ctx = await self._pw.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            channel="chromium",
            headless=True,
            user_agent=UA,
            locale="uk-UA",
            timezone_id="Europe/Kyiv",
            viewport={"width": 1440, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        await self._ctx.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
        )

    async def get_html(self, url: str, wait_selector: str | None = None,
                       settle_ms: int = 2500, timeout: int = 60000) -> str | None:
        await self.start()
        page = await self._ctx.new_page()
        try:
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=timeout)
            if resp is not None and resp.status >= 400:
                log.warning("браузер: %s вернул %s", url, resp.status)
            if wait_selector:
                try:
                    await page.wait_for_selector(wait_selector, timeout=20000)
                except Exception:
                    # Челлендж Cloudflare решается сам за несколько секунд — подождём и проверим ещё раз.
                    await page.wait_for_timeout(6000)
            await page.wait_for_timeout(settle_ms)
            html = await page.content()
            if "Just a moment" in html or "Checking your browser" in html:
                log.warning("браузер: %s всё ещё на челлендже Cloudflare", url)
                await page.wait_for_timeout(8000)
                html = await page.content()
            return html
        except Exception as e:
            log.warning("браузер: %s — %s: %s", url, type(e).__name__, str(e)[:120])
            return None
        finally:
            await page.close()

    async def close(self) -> None:
        try:
            if self._ctx:
                await self._ctx.close()
            if self._pw:
                await self._pw.stop()
        except Exception:
            pass
        finally:
            self._ctx = None
            self._pw = None
