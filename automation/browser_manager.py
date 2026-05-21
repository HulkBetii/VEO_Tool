"""VidGen AI — Browser manager using real Chrome headless + CDP.

Strategy:
  - Login: Chrome subprocess (visible) → user logs in → closes Chrome
  - Generate/Renew: Chrome subprocess (headless) + Playwright connects via CDP
  - Same Chrome binary + same profile = cookies work
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import time
from pathlib import Path
from typing import Optional

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from config.constants import BROWSER_PROFILE_DIR
from utils.logger import log
from utils.platform import (
    find_chrome,
    get_subprocess_flags,
    hide_chromium_taskbar_icons,
    hide_window,
    kill_process_on_port,
    kill_process_tree,
)


class BrowserManager:
    """Manages Chrome headless processes + Playwright CDP connections."""

    GOOGLE_FLOW_URL = "https://labs.google/fx/tools/video-fx"
    GOOGLE_IMAGE_URL = "https://labs.google/fx/tools/image-fx"

    def __init__(self):
        self._playwright = None
        self._playwrights = {}
        self._browsers = {}
        self._chrome_procs = {}
        self._pages = {}
        self._ref_counts = {}
        self._ports = {}
        self._profiles = {}
        self._next_port = 9222
        self._lock = asyncio.Lock()

    async def stop(self):
        """Close all browser connections and Chrome processes."""
        for account_id in list(self._browsers.keys()):
            await self.close_context(account_id)
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        log.info("Browser manager stopped")

    def _get_port(self, account_id: int) -> int:
        """Get a unique debugging port for an account."""
        if account_id not in self._ports:
            self._ports[account_id] = self._next_port
            self._next_port += 1
        return self._ports[account_id]

    async def get_or_create_context(
        self,
        account_id: int,
        email: str,
        proxy: Optional[str] = None,
        cookie_path: Optional[str] = None,
    ) -> BrowserContext:
        """Launch Playwright Chromium with cookies from Chrome login profile.

        Login happens in real Chrome (user sees browser, logs in manually).
        Cookies are exported to cookies_export.json in the profile dir.
        For tasks, we use Playwright's bundled Chromium + injected cookies.
        This avoids Chrome subprocess issues (port conflicts, profile locks).
        """
        self._ref_counts[account_id] = self._ref_counts.get(account_id, 0) + 1
        self._ensure_taskbar_sweeper()

        if account_id in self._browsers:
            contexts = self._browsers[account_id].contexts
            if contexts:
                return contexts[0]

        if account_id not in self._playwrights:
            log.info(f"Starting Playwright for account {account_id}...")
            self._playwrights[account_id] = await async_playwright().start()

        import json as _json

        cookies = []
        if cookie_path and Path(cookie_path).exists():
            cookies_file = Path(cookie_path) / "cookies_export.json"
            if cookies_file.exists():
                try:
                    with open(cookies_file, "r", encoding="utf-8") as f:
                        cookies = _json.load(f)
                    log.info(f"Loaded {len(cookies)} cookies from {cookies_file}")
                except Exception as e:
                    log.warning(f"Failed to load cookies: {e}")

        if not cookies:
            raise RuntimeError(f"No cookies for {email}. Please login/renew account first.")

        self._profiles[account_id] = cookie_path or ""
        pw = self._playwrights[account_id]

        log.info(f"Launching Chromium for {email}...")
        chrome_exe = find_chrome()
        if chrome_exe:
            log.info(f"Using system Chrome: {chrome_exe}")
        else:
            log.info("System Chrome not found, fallback to bundled chromium")

        browser = await pw.chromium.launch(
            headless=False,
            executable_path=chrome_exe,
            args=[
                "--window-position=-10000,-10000",
                "--window-size=1,1",
                "--disable-gpu",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-default-apps",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--disable-extensions",
                "--disable-features=TranslateUI,GlobalMediaControls",
            ],
        )
        self._browsers[account_id] = browser

        context = await browser.new_context()
        await context.add_init_script(
            """
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['vi-VN', 'vi', 'en-US', 'en'] });
        """
        )
        await context.add_cookies(cookies)
        log.info(f"Chromium ready for {email} ({len(cookies)} cookies injected)")
        self._ensure_taskbar_sweeper()
        return context

    def _ensure_taskbar_sweeper(self):
        """Start the background taskbar sweeper if it's not running.

        Each worker QThread has its OWN asyncio event loop. A sweeper
        task created in worker 1's loop dies when that loop shuts down
        — the next worker must therefore start a fresh sweeper in its
        own loop. We key sweepers by event-loop id so multiple workers
        can have their own sweeper concurrently without stomping each
        other.
        """
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            log.debug("_ensure_taskbar_sweeper called outside event loop")
            return None

        if not hasattr(self, "_taskbar_sweepers"):
            self._taskbar_sweepers = {}

        loop_id = id(current_loop)
        existing = self._taskbar_sweepers.get(loop_id)
        if existing is not None and not existing.done():
            return None

        try:
            task = current_loop.create_task(self._taskbar_sweep_loop())
            self._taskbar_sweepers[loop_id] = task
            log.debug(f"Taskbar sweeper started for loop {loop_id}")
        except Exception as e:
            log.warning(f"Could not start taskbar sweeper: {e}")
        return None

    async def _taskbar_sweep_loop(self):
        """Continuously strip taskbar buttons from our Chromium windows.

        Fast cadence for the first 10 seconds after the first browser
        comes up (catches delayed window creation + renderer/profile
        popups), then slows to 2s intervals. Exits cleanly once every
        browser we tracked is gone.
        """
        loop = asyncio.get_running_loop()
        fast_sweeps_left = 20
        idle_sweeps = 0

        while True:
            try:
                await loop.run_in_executor(None, hide_chromium_taskbar_icons)
            except RuntimeError as e:
                if "after shutdown" in str(e):
                    log.debug("Taskbar sweeper: event loop shutting down, exit")
                    return None
                log.debug(f"Taskbar sweep failed: {e}")
            except Exception as e:
                log.debug(f"Taskbar sweep failed: {e}")

            if not self._browsers:
                idle_sweeps += 1
                if idle_sweeps >= 3:
                    log.debug("Taskbar sweeper: no more browsers, stopping")
                    return None
            else:
                idle_sweeps = 0

            if fast_sweeps_left > 0:
                fast_sweeps_left -= 1
                await asyncio.sleep(0.5)
            else:
                await asyncio.sleep(2)

    async def get_page(
        self,
        account_id: int,
        email: str,
        proxy: Optional[str] = None,
        url: str = None,
        cookie_path: Optional[str] = None,
    ) -> Page:
        """Get or create a page for an account, navigate to URL."""
        context = await self.get_or_create_context(account_id, email, proxy, cookie_path)
        need_new_page = False

        if account_id not in self._pages or self._pages[account_id].is_closed():
            need_new_page = True
        else:
            try:
                await self._pages[account_id].evaluate("1+1")
            except Exception:
                log.warning(f"Page stale for account_id={account_id}, reconnecting...")
                need_new_page = True
                if account_id in self._browsers:
                    try:
                        await self._browsers[account_id].close()
                    except Exception:
                        pass
                    del self._browsers[account_id]
                    del self._pages[account_id]
                    self._kill_chrome(account_id)
                    context = await self.get_or_create_context(account_id, email, proxy, cookie_path)

        if need_new_page:
            pages = context.pages
            if pages:
                page = pages[0]
            else:
                page = await context.new_page()
            self._pages[account_id] = page

        page = self._pages[account_id]
        if url:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        return page

    async def close_context(self, account_id: int):
        """Close CDP connection and kill Chrome process.

        Uses ref counting: only actually closes when no more tasks
        are using this browser (ref count reaches 0).
        """
        self._ref_counts[account_id] = self._ref_counts.get(account_id, 1) - 1
        if self._ref_counts[account_id] > 0:
            log.info(
                f"Browser for account_id={account_id} still in use "
                f"({self._ref_counts[account_id]} tasks remaining), keeping alive"
            )
            return None

        self._ref_counts.pop(account_id, None)

        if account_id in self._pages:
            try:
                if not self._pages[account_id].is_closed():
                    await self._pages[account_id].close()
            except Exception:
                pass
            del self._pages[account_id]

        if account_id in self._browsers:
            try:
                await self._browsers[account_id].close()
            except Exception:
                pass
            del self._browsers[account_id]

        self._kill_chrome(account_id)

        if account_id in self._profiles:
            prof = Path(self._profiles[account_id])
            for lock_name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
                lock_file = prof / lock_name
                if not lock_file.exists():
                    continue
                try:
                    lock_file.unlink()
                except Exception:
                    pass

        if account_id in self._playwrights:
            try:
                await self._playwrights[account_id].stop()
            except Exception:
                pass
            del self._playwrights[account_id]

        log.info(f"Closed browser for account_id={account_id}")
        return None

    def _kill_chrome(self, account_id: int):
        """Kill the Chrome process and free its port."""
        if account_id in self._chrome_procs:
            proc = self._chrome_procs.pop(account_id)
            if not kill_process_tree(proc.pid):
                try:
                    proc.kill()
                except Exception:
                    pass

        if account_id in self._ports:
            kill_process_on_port(self._ports[account_id])
            time.sleep(2)
        return None

    def is_context_open(self, account_id: int) -> bool:
        return account_id in self._browsers

    @property
    def active_count(self) -> int:
        return len(self._browsers)
