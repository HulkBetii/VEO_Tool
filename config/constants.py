"""VidGen AI — Constants and configuration."""

import os
import sys
from pathlib import Path

APP_NAME = "NAV TOOLS"
APP_VERSION = "2.0.0"
APP_AUTHOR = "eKids"

if getattr(sys, "frozen", False):
    if hasattr(sys, "_MEIPASS"):
        ASSETS_DIR = Path(sys._MEIPASS)
        BASE_DIR = Path(sys.executable).parent
    else:
        ASSETS_DIR = Path(os.path.dirname(sys.executable))
        BASE_DIR = ASSETS_DIR
else:
    BASE_DIR = Path(os.path.dirname(os.path.abspath(__file__))).parent
    ASSETS_DIR = BASE_DIR

DATA_DIR = BASE_DIR / ".vidgen"
DB_PATH = DATA_DIR / "vidgen.db"
LOG_DIR = DATA_DIR / "logs"
BROWSER_PROFILE_DIR = DATA_DIR / "browser_profiles"
CONFIG_FILE = DATA_DIR / "app.json"

from utils.platform import find_ffmpeg as _find_ffmpeg

FFMPEG_PATH = _find_ffmpeg(BASE_DIR)
DEFAULT_IMAGE_OUTPUT = BASE_DIR / "image_output"
DEFAULT_VIDEO_OUTPUT = BASE_DIR / "video_output"


class TaskMode:
    IMAGE = "image"
    CHAR_IMAGE = "char_image"
    CHAR_VIDEO = "char_video"
    VIDEO_PLAIN = "video_plain"
    VIDEO_REF = "video_ref"
    FRAME_VIDEO = "frame_video"


MODE_LABELS = {
    TaskMode.IMAGE: "Tạo Ảnh",
    TaskMode.CHAR_IMAGE: "Ảnh đồng nhất",
    TaskMode.CHAR_VIDEO: "Video đồng nhất",
    TaskMode.VIDEO_PLAIN: "Video Flow",
    TaskMode.VIDEO_REF: "Video từ ảnh",
    TaskMode.FRAME_VIDEO: "Nối khung hình",
}


class TaskStatus:
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"
    CANCELLED = "CANCELLED"


class ItemStatus:
    PENDING = "PENDING"
    UPLOADING = "UPLOADING"
    GENERATING = "GENERATING"
    DOWNLOADING = "DOWNLOADING"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"


POLL_INTERVAL_SECONDS = 5
MAX_RETRY_COUNT = 3
MAX_CONCURRENT_TASKS = 20
DEFAULT_CONCURRENT_PROMPTS = 1

QUALITY_OPTIONS = [
    "Veo 3.1 - Fast",
    "Veo 3.1 - Quality",
    "Veo 3.1 - Lite",
    "Veo 3.1 - Lite [Lower Priority]",
    "Veo 3.1 - Fast [Lower Priority]",
]

CREDITS_PER_MODEL = {
    "Veo 3.1 - Quality": 100,
    "Veo 3.1 - Fast": 10,
    "Veo 3.1 - Lite": 5,
    "Veo 3.1 - Lite [Lower Priority]": 0,
    "Veo 3.1 - Fast [Lower Priority]": 0,
}


def estimate_credits(quality: str, n_videos: int = 1) -> int:
    """Total credits the user is about to spend.

    Mirrors the "Generating will use X credits" indicator on Flow.
    Returns 0 for any 'Lower Priority' queue model (free / quota).
    """
    per = CREDITS_PER_MODEL.get(quality, 10)
    return per * max(0, int(n_videos))


def cost_for_model_key(model_key: str) -> int:
    """Map Flow `model_key` → credit cost per video. Race-free alternative
    to delta tracking when multiple parallel clients share an account.

    Pricing rules (verified Flow web capture, see commits 4399c10, afcd2e0,
    e833d49, c1e07a7):

    | suffix in model_key                     | tier        | credits |
    |-----------------------------------------|-------------|---------|
    | `_low_priority`                         | Lite [LP]   | 0       |
    | `_relaxed` (Fast LP, ends `_ultra_relaxed`) | Fast [LP] | 0       |
    | `_extension_lite` / `_extension_fast`   | Extend [LP] | 0       |
    | `_lite` (no `_low_priority`)            | Lite paid   | 5       |
    | `_fast` (no `_relaxed`)                 | Fast paid   | 10      |
    | none of the above                       | Quality     | 100     |

    Quality detection: Flow's Quality model_keys do NOT contain `_quality`
    substring — they're identified by the ABSENCE of `_fast`/`_lite`. Examples:
    `veo_3_1_t2v_landscape`, `veo_3_1_i2v_s_portrait`, `veo_3_1_extend_landscape`,
    `veo_3_1_i2v_s_landscape_fl`. Hence Quality is the default fallback (NOT 10).

    Empty `model_key` → 10 (Fast) as the safer fallback when generation hasn't
    set `_last_model_key` yet (rare race; logs a debug warning at call site).

    Note: upsampler keys (`veo_3_1_upsampler_1080p` / `_4k`) currently fall
    into the Quality bucket (100). Real upsampler pricing unverified — TODO.
    """
    if not model_key:
        return 10
    k = model_key.lower()
    if "_low_priority" in k or "_relaxed" in k or "_extension_" in k:
        return 0
    if "_lite" in k:
        return 5
    if "_fast" in k:
        return 10
    return 100


ASPECT_RATIO_OPTIONS = [
    ("16:9 Ngang", "16:9"),
    ("9:16 Dọc", "9:16"),
    ("1:1 Vuông", "1:1"),
]

IMAGE_MODEL_OPTIONS = ["Nano Banana Pro", "Nano Banana 2", "Imagen 4"]
SERVICE_OPTIONS = ["Flow"]
SAVE_MODE_OPTIONS = ["1 Thư mục mỗi Task", "1 Thư mục chung"]


class AccountTier:
    FREE = "FREE"
    PAYGATE_TIER_TWO = "PAYGATE_TIER_TWO"


class DarkColors:
    BG = "#0b1326"
    SURFACE = "#0b1326"
    SURFACE_CONTAINER_LOW = "#131b2e"
    SURFACE_CONTAINER = "#171f33"
    SURFACE_CONTAINER_HIGH = "#222a3d"
    SURFACE_CONTAINER_HIGHEST = "#2d3449"
    SURFACE_BRIGHT = "#31394d"
    PRIMARY = "#adc6ff"
    PRIMARY_CONTAINER = "#4d8eff"
    ON_PRIMARY = "#002e6a"
    SECONDARY = "#bcc7de"
    SECONDARY_CONTAINER = "#3e495d"
    TERTIARY = "#ffb786"
    TERTIARY_CONTAINER = "#df7412"
    ON_SURFACE = "#dae2fd"
    ON_SURFACE_VARIANT = "#c2c6d6"
    ERROR = "#ffb4ab"
    ERROR_CONTAINER = "#93000a"
    SUCCESS = "#4EC9B0"
    WARNING = "#F7C325"
    OUTLINE = "#8c909f"
    OUTLINE_VARIANT = "#424754"
    TEXT_PRIMARY = "#dae2fd"
    TEXT_SECONDARY = "#c2c6d6"
    TEXT_MUTED = "#8c909f"
    ACCENT_BLUE = "#3b82f6"
    ACCENT_ORANGE = "#f97316"
    ACCENT_GREEN = "#22c55e"
    ACCENT_RED = "#ef4444"


class LightColors:
    BG = "#f8fafc"
    SURFACE = "#ffffff"
    SURFACE_CONTAINER_LOW = "#f1f5f9"
    SURFACE_CONTAINER = "#e2e8f0"
    SURFACE_CONTAINER_HIGH = "#cbd5e1"
    SURFACE_CONTAINER_HIGHEST = "#94a3b8"
    SURFACE_BRIGHT = "#ffffff"
    PRIMARY = "#1e40af"
    PRIMARY_CONTAINER = "#3b82f6"
    ON_PRIMARY = "#ffffff"
    SECONDARY = "#475569"
    SECONDARY_CONTAINER = "#e2e8f0"
    TERTIARY = "#c2410c"
    TERTIARY_CONTAINER = "#f97316"
    ON_SURFACE = "#0f172a"
    ON_SURFACE_VARIANT = "#475569"
    ERROR = "#dc2626"
    ERROR_CONTAINER = "#fecaca"
    SUCCESS = "#16a34a"
    WARNING = "#ca8a04"
    OUTLINE = "#94a3b8"
    OUTLINE_VARIANT = "#cbd5e1"
    TEXT_PRIMARY = "#0f172a"
    TEXT_SECONDARY = "#475569"
    TEXT_MUTED = "#94a3b8"
    ACCENT_BLUE = "#3b82f6"
    ACCENT_ORANGE = "#f97316"
    ACCENT_GREEN = "#22c55e"
    ACCENT_RED = "#ef4444"


FONT_HEADLINE = "Manrope"
FONT_BODY = "Inter"
FONT_LABEL = "Inter"
FONT_MONO = "JetBrains Mono"

FONT_SIZE_H1 = 20
FONT_SIZE_H2 = 16
FONT_SIZE_BODY = 13
FONT_SIZE_LABEL = 12
FONT_SIZE_SMALL = 11

SIDEBAR_WIDTH = 120
CONFIG_PANEL_WIDTH = 480
SIDEBAR_ICON_SIZE = 20
MAX_CHARACTER_IMAGES = 100

API_BASE_URL = os.environ.get("NAVTOOLS_API_BASE_URL", "https://workspace.navtools.vn")
CLIENT_API_KEY = os.environ.get("NAVTOOLS_CLIENT_API_KEY", "0erOa6TaylTHz8WNAM-LeZfM-YXAqNBvQ4iiN8N7cnc")

GSHEET_CREDENTIALS_PATH = DATA_DIR / "service_account.json"
GSHEET_SHEET_ID = "1VyZFh5bhkM-ZV1wHmRxGBY2sSr62CCsQHIeF536tsHw"
GSHEET_WORKSHEET_NAME = "users"

DEFAULT_ACCOUNT_EXPIRY_DAYS = 30
DEFAULT_ACCOUNT_EXPIRY_HOURS: int | None = 1
