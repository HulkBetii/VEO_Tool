"""Platform helpers."""

from __future__ import annotations

import os
import platform as _platform
import shutil
import subprocess
from pathlib import Path


def find_chrome():
    system = _platform.system().lower()
    if "windows" in system:
        return _find_chrome_windows()
    if "darwin" in system:
        return _find_chrome_macos()
    return _find_chrome_linux()


def _find_chrome_windows():
    for env in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        root = os.environ.get(env)
        if not root:
            continue
        for rel in ("Google/Chrome/Application/chrome.exe", "Chromium/Application/chrome.exe"):
            path = Path(root) / rel
            if path.exists():
                return str(path)
    return shutil.which("chrome") or shutil.which("chrome.exe")


def _find_chrome_macos():
    path = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    return str(path) if path.exists() else shutil.which("google-chrome")


def _find_chrome_linux():
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        path = shutil.which(name)
        if path:
            return path
    return None


def _macos_homebrew_candidates(name: str) -> list:
    """Return likely Homebrew / system paths for `name` on macOS.

    GUI .app bundles on macOS launch without /opt/homebrew/bin in PATH, so
    shutil.which() misses Homebrew-installed tools even when they exist.
    """
    return [
        Path("/opt/homebrew/bin") / name,   # Apple-Silicon Homebrew
        Path("/usr/local/bin") / name,       # Intel Homebrew / manual install
        Path("/usr/bin") / name,             # system install
    ]


def find_binary(name: str, base_dir=None, env_var: str = "") -> str:
    """Locate a binary by name, checking bundled path, env-var override,
    shutil.which, and macOS Homebrew locations.  Returns the full path or
    falls back to bare *name* (lets the OS try at runtime).
    """
    candidates: list[Path] = []

    # 1. Environment-variable override (highest priority).
    if env_var:
        override = os.environ.get(env_var, "")
        if override:
            candidates.append(Path(override))

    # 2. Bundled binary next to the project root.
    if base_dir:
        base = Path(base_dir)
        for rel in (name, f"{name}.exe", f"bin/{name}", f"bin/{name}.exe",
                    f"tools/{name}", f"tools/{name}/bin/{name}"):
            candidates.append(base / rel)

    # 3. PATH lookup.
    found = shutil.which(name) or shutil.which(f"{name}.exe")
    if found:
        candidates.append(Path(found))

    # 4. macOS Homebrew / system paths (needed when launched as .app bundle).
    if _platform.system() == "Darwin":
        candidates.extend(_macos_homebrew_candidates(name))

    for p in candidates:
        if p and p.is_file():       # is_file() skips directories (e.g. bundled "ffmpeg/" dir)
            return str(p)

    return name  # fall back to bare name; subprocess will try $PATH at launch time


def find_ffmpeg(base_dir=None):
    return find_binary("ffmpeg", base_dir=base_dir, env_var="NAVTOOLS_FFMPEG")


def get_subprocess_flags():
    return subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


def kill_process_tree(pid):
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
        else:
            os.kill(int(pid), 9)
        return True
    except Exception:
        return False


def kill_process_on_port(port):
    return False


def hide_window(*args, **kwargs):
    return None


def enum_callback(*args, **kwargs):
    return True


def hide_chromium_taskbar_icons(*args, **kwargs):
    return None


def _is_playwright_process(proc):
    return "playwright" in str(proc).lower()


class _ITaskbarList:
    def __init__(self):
        pass

    def DeleteTab(self, hwnd):
        return None

    def __del__(self):
        pass


def _get_taskbar_list():
    return _ITaskbarList()


def _GUID(value):
    return value


def open_folder(path):
    path = str(path)
    if os.name == "nt":
        os.startfile(path)
    elif _platform.system() == "Darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def get_playwright_browsers_path():
    return os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
