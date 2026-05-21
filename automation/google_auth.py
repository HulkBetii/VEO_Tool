"""VidGen AI — Google account authentication.

Handles Google login flow via Playwright and session validation.
Persistent session + cookie check.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from playwright.async_api import BrowserContext, Page

from automation.browser_manager import BrowserManager
from models.account import Account
from models.database import Database
from utils.logger import log


class GoogleAuth:
    """Google authentication manager."""

    ACCOUNTS_URL = "https://accounts.google.com"
    FLOW_URL = "https://labs.google/fx/tools/video-fx"
    MYACCOUNT_URL = "https://myaccount.google.com"

    def __init__(self, browser_mgr: BrowserManager, db: Database):
        self._browser = browser_mgr
        self._db = db

    async def login_account(self, account: Account) -> bool:
        """Open browser for manual Google login.

        Returns True if login was successful.
        """
        log.info(f"Starting login for {account.email}...")
        page = await self._browser.get_page(
            account_id=account.id,
            email=account.email,
            proxy=account.proxy,
            cookie_path=account.cookie_path,
            url=self.ACCOUNTS_URL,
        )

        if await self._is_logged_in(page, account.email):
            log.info(f"Already logged in: {account.email}")
            await self._update_session_info(account, page)
            return True

        log.info(f"Navigating to Google login for {account.email}")
        await page.goto(self.ACCOUNTS_URL, wait_until="domcontentloaded")
        log.info("Waiting for manual login completion...")

        try:
            await page.wait_for_url("**/myaccount.google.com/**", timeout=300000)
            log.info(f"Login successful: {account.email}")
            await self._update_session_info(account, page)
            return True
        except Exception:
            await page.goto(self.MYACCOUNT_URL, wait_until="domcontentloaded")
            if not await self._is_logged_in(page, account.email):
                log.error(f"Login timeout/failed for {account.email}")
                return False
            await self._update_session_info(account, page)
            return True

    async def check_session(self, account: Account) -> bool:
        """Check if account session is still valid."""
        try:
            page = await self._browser.get_page(
                account_id=account.id,
                email=account.email,
                proxy=account.proxy,
                cookie_path=account.cookie_path,
                url=self.FLOW_URL,
            )
            await page.wait_for_load_state("domcontentloaded", timeout=15000)

            current_url = page.url
            if "accounts.google.com" in current_url:
                log.warning(f"Session expired for {account.email}")
                return False

            logged_in = await self._is_flow_accessible(page)
            if logged_in:
                log.info(f"Session valid for {account.email}")
                return True

            log.warning(f"Session invalid for {account.email}")
            return False
        except Exception as e:
            log.error(f"Session check failed for {account.email}: {e}")
            return False

    async def get_account_credits(self, account: Account) -> Optional[int]:
        """Fetch remaining credits from Flow API."""
        try:
            page = await self._browser.get_page(
                account_id=account.id,
                email=account.email,
                proxy=account.proxy,
                cookie_path=account.cookie_path,
            )
            if "labs.google" not in page.url:
                await page.goto(self.FLOW_URL, wait_until="domcontentloaded")

            credits = await page.evaluate(
                """
                () => {
                    try {
                        // Try to find credit info in page data
                        const scripts = document.querySelectorAll('script');
                        for (const s of scripts) {
                            const text = s.textContent;
                            if (text.includes('remainingCredits') || text.includes('credit')) {
                                const match = text.match(/remainingCredits['":\\s]*(\\d+)/);
                                if (match) return parseInt(match[1]);
                            }
                        }
                        return null;
                    } catch (e) {
                        return null;
                    }
                }
            """
            )
            if credits is not None:
                log.info(f"Credits for {account.email}: {credits}")
                self._db.update_account_credit(account.id, credits)
            return credits
        except Exception as e:
            log.error(f"Failed to get credits for {account.email}: {e}")
            return None

    async def get_account_tier(self, account: Account) -> Optional[str]:
        """Detect account tier from Flow API response."""
        try:
            page = await self._browser.get_page(
                account_id=account.id,
                email=account.email,
                proxy=account.proxy,
                cookie_path=account.cookie_path,
            )
            if "labs.google" not in page.url:
                await page.goto(self.FLOW_URL, wait_until="domcontentloaded")

            tier = await page.evaluate(
                """
                () => {
                    try {
                        const scripts = document.querySelectorAll('script');
                        for (const s of scripts) {
                            const text = s.textContent;
                            if (text.includes('PAYGATE_TIER')) {
                                const match = text.match(/PAYGATE_TIER_\\w+/);
                                if (match) return match[0];
                            }
                        }
                        return 'FREE';
                    } catch (e) {
                        return 'FREE';
                    }
                }
            """
            )
            return tier
        except Exception as e:
            log.error(f"Failed to get tier for {account.email}: {e}")
            return None

    async def _is_logged_in(self, page: Page, email: str) -> bool:
        """Check if page shows logged-in state."""
        try:
            current_url = page.url
            if "accounts.google.com/signin" in current_url:
                return False
            if "myaccount.google.com" in current_url:
                return True

            avatar = await page.query_selector('img[data-profileimageid], a[aria-label*="Account"]')
            return avatar is not None
        except Exception:
            return False

    async def _is_flow_accessible(self, page: Page) -> bool:
        """Check if Flow app is accessible (not redirected to login)."""
        try:
            flow_element = await page.query_selector('text="Create", [data-testid], .mdc-text-field')
            return flow_element is not None
        except Exception:
            return False

    async def _update_session_info(self, account: Account, page: Page):
        """Update account session data in DB."""
        context = page.context
        cookies = await context.cookies()

        max_exp = 0
        for cookie in cookies:
            if "google" not in cookie.get("domain", ""):
                continue
            exp = cookie.get("expires", 0)
            if exp > max_exp:
                max_exp = exp

        if max_exp > 0:
            cookie_exp = datetime.fromtimestamp(max_exp)
        else:
            cookie_exp = datetime.now() + timedelta(days=30)
        account.cookie_exp = cookie_exp

        profile_dir = self._browser._profiles.get(account.id, "")
        if profile_dir:
            account.cookie_path = profile_dir

        try:
            import json

            cookies_file = Path(account.cookie_path) / "cookies_export.json"
            cookies_data = [
                {k: v for k, v in c.items() if k in ("name", "value", "domain", "path", "expires", "httpOnly", "secure", "sameSite")}
                for c in cookies
            ]
            with open(cookies_file, "w", encoding="utf-8") as f:
                json.dump(cookies_data, f)
            log.info(f"Exported {len(cookies_data)} cookies to {cookies_file}")
        except Exception as e:
            log.warning(f"Failed to export cookies: {e}")

        tier = await self.get_account_tier(account)
        if tier:
            account.tier = tier

        credits = await self.get_account_credits(account)
        if credits is not None:
            account.credit = credits

        self._db.update_account(account)
        log.info(
            f"Updated session for {account.email}: tier={account.tier}, "
            f"credit={account.credit}, exp={cookie_exp.strftime('%Y-%m-%d')}"
        )
