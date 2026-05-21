"""
SubprocessTokenProvider — Harvest reCAPTCHA tokens from a separate Chrome instance.

Uses real Chrome (not Playwright Chromium) via CDP, same approach as BrowserManager.
A separate Chrome process with injected cookies harvests reCAPTCHA tokens,
while httpx sends the actual API request → context separation → Google accepts.

Flow:
  1. Extract cookies from the main CDP Chrome (logged-in session)
  2. Launch a SECOND real Chrome (different port, temp profile)
  3. Connect via CDP, inject cookies → navigate to video-fx
  4. Harvest reCAPTCHA token → return for use with httpx
"""

from __future__ import annotations

import asyncio
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, Playwright, Browser, BrowserContext, Page
from utils.logger import log
from utils.platform import find_chrome, get_subprocess_flags, hide_window


_ANTI_DETECT_JS = """
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    window.chrome = { runtime: {} };
    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
    Object.defineProperty(navigator, 'languages', { get: () => ['vi-VN', 'vi', 'en-US', 'en'] });
"""

_RECAPTCHA_JS = """async (action) => {
    let siteKey = null;
    const scripts = document.querySelectorAll('script[src*="recaptcha"]');
    for (const s of scripts) {
        const m = s.src.match(/[?&]render=([^&]+)/);
        if (m) { siteKey = m[1]; break; }
    }
    if (!siteKey) return {error: 'no_site_key'};

    if (typeof grecaptcha !== 'undefined' && grecaptcha.enterprise) {
        try {
            const token = await grecaptcha.enterprise.execute(
                siteKey, {action: action}
            );
            if (token) return {token, key: siteKey};
        } catch(e) {
            return {error: e.message};
        }
    }
    return {error: 'grecaptcha_not_available'};
}"""

VIDEO_FX_URL = "https://labs.google/fx/tools/video-fx"
_CDP_PORT = 9333


class SubprocessTokenProvider:
    """Harvest reCAPTCHA tokens from a separate real Chrome via CDP."""

    __static_attributes__ = (
        '_browser', '_chrome_proc', '_context', '_page', '_playwright', '_temp_profile'
    )

    def __init__(self):
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._chrome_proc = None
        self._temp_profile = None

    @property
    def is_running(self) -> bool:
        return (
            self._browser is not None
            and self._page is not None
            and not self._page.is_closed()
        )

    async def start(self, cookies: list[dict]) -> None:
        """Launch a separate real Chrome and connect via CDP."""
        chrome = find_chrome()
        if not chrome:
            raise RuntimeError('Chrome not found for SubprocessTokenProvider')

        log.info('SubprocessTokenProvider: starting real Chrome...')

        self._playwright = await async_playwright().start()
        self._temp_profile = tempfile.mkdtemp(prefix='vidgen_recaptcha_')

        cmd = [
            chrome,
            f'--user-data-dir={self._temp_profile}',
            f'--remote-debugging-port={_CDP_PORT}',
            '--disable-gpu',
            '--no-first-run',
            '--no-default-browser-check',
            '--disable-default-apps',
            '--disable-blink-features=AutomationControlled',
            '--window-size=1,1',
            '--window-position=-10000,-10000',
        ]

        self._chrome_proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **get_subprocess_flags(),
        )

        cdp_url = f'http://127.0.0.1:{_CDP_PORT}'

        for attempt in range(20):
            await asyncio.sleep(0.5)
            try:
                self._browser = await self._playwright.chromium.connect_over_cdp(cdp_url)
                log.info(
                    f'SubprocessTokenProvider: connected to Chrome CDP (port={_CDP_PORT}, '
                    f'pid={self._chrome_proc.pid})'
                )
                hide_window(self._chrome_proc.pid)
                break
            except Exception:
                if attempt == 19:
                    raise RuntimeError(
                        'SubprocessTokenProvider: cannot connect to Chrome CDP'
                    )

        contexts = self._browser.contexts
        if contexts:
            self._context = contexts[0]
        else:
            self._context = await self._browser.new_context()

        await self._context.add_init_script(_ANTI_DETECT_JS)

        if cookies:
            await self._context.add_cookies(cookies)
            log.info(f'SubprocessTokenProvider: injected {len(cookies)} cookies')

        self._page = await self._context.new_page()
        await self._page.goto(
            VIDEO_FX_URL,
            wait_until='domcontentloaded',
            timeout=20000,
        )

        await asyncio.sleep(3)

        for i in range(30):
            has = await self._page.evaluate(
                "typeof grecaptcha !== 'undefined' && (!!grecaptcha.enterprise || !!grecaptcha.execute)"
            )
            if has:
                log.info(f'SubprocessTokenProvider: grecaptcha loaded after {i * 0.5}s')
                break
            await asyncio.sleep(0.5)

        log.info('SubprocessTokenProvider: ready')

    async def get_token(self, action: str = 'VIDEO_GENERATION') -> str:
        """Harvest reCAPTCHA token from the separate Chrome."""
        if not self.is_running:
            log.warning('SubprocessTokenProvider: not running')
            return ''

        try:
            log.info(f'SubprocessTokenProvider: harvesting token (action={action})...')

            await self._page.reload(wait_until='domcontentloaded', timeout=20000)
            await asyncio.sleep(2)

            for i in range(30):
                has = await self._page.evaluate(
                    "typeof grecaptcha !== 'undefined' && (!!grecaptcha.enterprise || !!grecaptcha.execute)"
                )
                if has:
                    break
                await asyncio.sleep(0.5)

            result = await self._page.evaluate(_RECAPTCHA_JS, action)

            if result and isinstance(result, dict) and result.get('token'):
                log.info(
                    f"SubprocessTokenProvider: got token (key={result['key'][:10]}...): "
                    f"{result['token'][:20]}..."
                )
                return result['token']

            log.warning(f'SubprocessTokenProvider: failed — {result}')
            return ''
        except Exception as e:
            log.error(f'SubprocessTokenProvider: error — {e}')
            return ''

    async def refresh_cookies(self, cookies: list[dict]) -> None:
        """Update cookies when the main browser session is renewed."""
        if not self._context:
            return
        try:
            await self._context.clear_cookies()
            if cookies:
                await self._context.add_cookies(cookies)
            log.info(f'SubprocessTokenProvider: refreshed {len(cookies)} cookies')
        except Exception as e:
            log.warning(f'SubprocessTokenProvider: refresh_cookies error — {e}')

    async def stop(self) -> None:
        """Cleanup: close browser, kill Chrome, stop Playwright."""
        log.info('SubprocessTokenProvider: stopping...')

        for resource, name in [
            (self._page, 'page'),
            (self._context, 'context'),
            (self._browser, 'browser'),
        ]:
            if resource:
                try:
                    await resource.close()
                except Exception:
                    pass

        if self._chrome_proc:
            try:
                from utils.platform import kill_process_tree
                kill_process_tree(self._chrome_proc.pid)
            except Exception:
                try:
                    self._chrome_proc.kill()
                except Exception:
                    pass

        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass

        if self._temp_profile:
            import shutil
            shutil.rmtree(self._temp_profile, ignore_errors=True)

        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None
        self._chrome_proc = None
        self._temp_profile = None

        log.info('SubprocessTokenProvider: stopped')