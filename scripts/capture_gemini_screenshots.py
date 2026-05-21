"""Screenshot the AI Studio key-creation flow using Playwright.

Outputs 3 PNGs into ``assets/screenshots/`` for the Settings -> Gemini key
guide dialog.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "assets" / "screenshots"
OUT_DIR.mkdir(parents=True, exist_ok=True)
PROFILE = ROOT / ".vidgen" / "browser_profiles" / "screenshot_capture"


def take_shots():
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(PROFILE),
            headless=False,
            viewport={"width": 1440, "height": 900},
            channel="chrome",
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        print("→ Navigating to AI Studio API keys page...")
        page.goto("https://aistudio.google.com/apikey", wait_until="domcontentloaded")
        time.sleep(3)

        dismiss = page.get_by_role("button", name="Dismiss")
        try:
            if dismiss.is_visible(timeout=2000):
                dismiss.click()
                print("  Dismissed ToS banner")
        except Exception:
            pass

        create_btn = page.get_by_role("button", name="Create API key")
        print(">> Đang đợi anh đăng nhập Google trong cửa sổ Chrome (max 3 phút)...")
        print("   Nếu đã login rồi sẽ auto-continue ngay.")

        max_wait = 180
        ready = False
        for poll in range(max_wait):
            try:
                if create_btn.is_visible(timeout=1500):
                    ready = True
                    break
            except Exception:
                pass
            if poll and poll % 30 == 0:
                print(f"   ... {poll}s elapsed, still waiting for login")
            time.sleep(1)

        if not ready:
            print("✗ Không thấy 'Create API key' sau 3 phút — dừng lại.")
            ctx.close()
            sys.exit(1)

        print("✓ Logged in, bắt đầu chụp...")

        print("→ Step 2: 'Create API key' button")
        box = create_btn.bounding_box()
        if not box:
            raise RuntimeError("Could not locate Create button")
        clip = {
            "x": max(0, box["x"] - 500),
            "y": max(0, box["y"] - 60),
            "width": min(1000, box["width"] + 600),
            "height": min(300, box["height"] + 160),
        }
        step2_path = OUT_DIR / "gemini_step2_create_key.png"
        page.screenshot(path=step2_path, clip=clip)
        print(f"  ✓ {step2_path} ({step2_path.stat().st_size // 1024}KB)")

        print("→ Step 3: Project selection modal")
        create_btn.click()
        time.sleep(2)
        step3_path = OUT_DIR / "gemini_step3_select_project.png"
        try:
            modal = page.locator("mat-dialog-container, [role='dialog']").first
            modal.wait_for(state="visible", timeout=5000)
            mbox = modal.bounding_box()
            if mbox:
                page.screenshot(
                    path=step3_path,
                    clip={
                        "x": max(0, mbox["x"] - 10),
                        "y": max(0, mbox["y"] - 20),
                        "width": min(1200, mbox["width"] + 20),
                        "height": min(850, mbox["height"] + 40),
                    },
                )
            else:
                page.screenshot(path=step3_path, full_page=True)
        except Exception as e:
            print(f"  (modal locator failed: {e}, using viewport)")
            page.screenshot(path=step3_path, full_page=True)
        print(f"  ✓ {step3_path} ({step3_path.stat().st_size // 1024}KB)")

        print("→ Step 4: existing key row with copy icon")
        page.keyboard.press("Escape")
        time.sleep(2)
        step4_path = OUT_DIR / "gemini_step4_copy_key.png"
        try:
            row = page.locator("table tbody tr, [role='row']").first
            rbox = row.bounding_box()
            if rbox:
                page.screenshot(
                    path=step4_path,
                    clip={
                        "x": max(0, rbox["x"] - 40),
                        "y": max(0, rbox["y"] - 40),
                        "width": min(1300, rbox["width"] + 80),
                        "height": min(500, rbox["height"] + 80),
                    },
                )
            else:
                page.screenshot(path=step4_path, full_page=True)
        except Exception as e:
            print(f"  (row locator failed: {e})")
            page.screenshot(path=step4_path, full_page=True)
        print(f"  ✓ {step4_path} ({step4_path.stat().st_size // 1024}KB)")

        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print("DONE — 3 screenshots ready in:")
        print(OUT_DIR)
        ctx.close()


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    take_shots()
