"""NAV TOOLS - YouTube to Prompt analyzer."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable, Optional
from difflib import get_close_matches

try:
    from config.constants import DATA_DIR, FFMPEG_PATH
except Exception:
    DATA_DIR = Path("data")
    FFMPEG_PATH = "ffmpeg"

try:
    from utils.logger import log
except Exception:
    import logging

    log = logging.getLogger(__name__)

try:
    from utils.platform import get_subprocess_flags
except Exception:
    def get_subprocess_flags() -> int:
        return 0

try:
    from services.gemini_with_fallback import agenerate_with_fallback
except Exception:
    async def agenerate_with_fallback(*args, **kwargs):
        raise RuntimeError("Gemini fallback service is unavailable")


MAX_DURATION = 1800
VERY_LONG_VIDEO_CONFIRM = 1200
LONG_VIDEO_WARNING_THRESHOLD = 600
VEO_VIDEO_LENGTH = 8
MAX_SCENES = 40
MIN_SCENE_DURATION_SEC = 2
HARD_DROP_DURATION_SEC = 0.8
WHISPER_MODEL_DEFAULT = "small"
WHISPER_LANGUAGE = None
CONFIDENCE_WARNING_THRESHOLD = 0.55
FFMPEG_AUDIO_EXTRACT_TIMEOUT = 600
FFMPEG_SCENE_DETECT_TIMEOUT = 600

STYLE_PRESETS = {
    "cinematic": "cinematic documentary realism, natural light, detailed production design",
    "anime": "high quality anime illustration, expressive staging, clean linework",
    "3d": "stylized 3D animation, polished lighting, cinematic composition",
    "watercolor": "soft watercolor illustration, hand painted texture, gentle atmosphere",
    "comic": "graphic novel panel, bold inking, dramatic framing",
    "stick_figure": "minimal stick figure animation, clean white background, simple readable action",
}
DEFAULT_STYLE_PRESET = "cinematic"

VEO3_SHOT_TYPES = [
    "extreme wide shot",
    "wide establishing shot",
    "wide shot",
    "medium wide shot",
    "medium shot",
    "medium close-up",
    "close-up",
    "extreme close-up",
    "over-the-shoulder shot",
    "POV shot",
    "bird's-eye view",
    "worm's-eye view",
    "dutch angle shot",
    "low angle shot",
    "high angle shot",
    "aerial shot",
    "profile shot",
    "two-shot",
    "group shot",
]

VEO3_CAMERA_MOVES = [
    "static tripod shot",
    "slow dolly-in",
    "slow dolly-out",
    "smooth tracking shot left-to-right",
    "smooth tracking shot right-to-left",
    "crane shot rising",
    "crane shot descending",
    "handheld shaky cam",
    "FPV drone dive",
    "orbit shot circling subject",
    "pull-back reveal",
    "whip pan",
    "tilt up slowly",
    "tilt down slowly",
    "zoom in gradually",
    "zoom out gradually",
]

VALID_SCENE_CLASSES = ("CHARACTER", "LANDMARK", "DOCUMENT", "OBJECT", "ATMOSPHERE", "MAP_OVERVIEW")

SHOT_SCHEMA = {
    "type": "object",
    "properties": {
        "shot_type": {"type": "string", "enum": VEO3_SHOT_TYPES},
        "camera_move": {"type": "string", "enum": VEO3_CAMERA_MOVES},
        "scene_class": {"type": "string", "enum": list(VALID_SCENE_CLASSES)},
        "subject_desc": {"type": "string"},
        "visible_characters": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number"},
        "narration_summary": {"type": "string"},
    },
    "required": ["shot_type", "camera_move", "subject_desc"],
}


def _safe_imwrite(path, frame, params=None):
    ext = os.path.splitext(path)[1] or ".jpg"
    try:
        import cv2 as _cv2
        ok, buf = _cv2.imencode(ext, frame, params or [])
        if not ok:
            log.warning(f"[safe_imwrite] cv2.imencode({ext}) returned False")
            return False
        with open(path, "wb") as f:
            f.write(buf.tobytes())
        return True
    except ImportError:
        try:
            from PIL import Image as _Image
            import numpy as _np
            img = _Image.fromarray(frame[..., ::-1] if frame.ndim == 3 else frame)
            img.save(path)
            return True
        except Exception as e:
            log.warning(f"[safe_imwrite] PIL fallback failed: {e}")
            return False
    except Exception as e:
        log.warning(f"[safe_imwrite] write to {path} failed: {e}")
        return False


def normalize_to_whitelist(value, whitelist, default):
    text = str(value or "").strip().lower()
    options = list(whitelist or [])
    if not text:
        return default
    by_lower = {str(item).lower(): item for item in options}
    if text in by_lower:
        return by_lower[text]
    for key, original in by_lower.items():
        if text in key or key in text:
            return original
    match = get_close_matches(text, list(by_lower), n=1, cutoff=0.4)
    return by_lower[match[0]] if match else default


_PROMINENT_PERSON_REPLACEMENTS = {
    "celebrity": "public figure",
    "president": "political leader",
    "prime minister": "political leader",
    "youtuber": "online narrator",
}
_TEXT_RENDERING_REPLACEMENTS = {
    "subtitle": "visual caption area",
    "logo": "simple emblem",
    "watermark": "faint overlay mark",
    "text on screen": "graphic panel",
}
_VIOLENT_WORD_REPLACEMENTS = {
    "blood": "dark stains",
    "gore": "aftermath",
    "kill": "defeat",
    "murder": "violent incident",
}
_CONTEXTUAL_PERSON_TRIGGERS = ("face", "portrait", "celebrity", "president", "politician", "youtuber")


def _apply_contextual_sanitize(text: str) -> tuple[str, list[str]]:
    result = str(text or "")
    replacements = []
    for mapping, label in (
        (_PROMINENT_PERSON_REPLACEMENTS, "name->role"),
        (_VIOLENT_WORD_REPLACEMENTS, "violent->soft"),
        (_TEXT_RENDERING_REPLACEMENTS, "text-overlay->stripped"),
    ):
        for old, new in mapping.items():
            pattern = re.compile(re.escape(old), re.IGNORECASE)
            if pattern.search(result):
                result = pattern.sub(new, result)
                replacements.append(label)
    return result, replacements


def _sanitize_subject_desc(text: str) -> tuple[str, list[str]]:
    desc = re.sub(r"\s+", " ", str(text or "")).strip()
    desc, replacements = _apply_contextual_sanitize(desc)
    desc = re.sub(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3}\b", "a named person", desc)
    desc = desc.strip(" ,;:")
    if len(desc) > 240:
        cut = desc[:240]
        for sep in (". ", "! ", "? ", ".", "!", "?"):
            idx = cut.rfind(sep)
            if idx >= 30:
                cut = cut[: idx + 1]
                break
        desc = cut.rstrip(" ,;:") + ("" if cut.endswith((".", "!", "?")) else ".")
    return desc or "main subject in scene", replacements


def validate_shot_payload(payload):
    if not isinstance(payload, dict):
        payload = {}
    shot_type = normalize_to_whitelist(payload.get("shot_type", ""), VEO3_SHOT_TYPES, "medium shot")
    camera_move = normalize_to_whitelist(payload.get("camera_move", ""), VEO3_CAMERA_MOVES, "static tripod shot")
    scene_class = str(payload.get("scene_class") or "").strip().upper()
    if scene_class not in VALID_SCENE_CLASSES:
        scene_class = "CHARACTER"
    subject_desc, replacements = _sanitize_subject_desc(payload.get("subject_desc", ""))

    visible = payload.get("visible_characters") or []
    if isinstance(visible, str):
        visible = [p.strip() for p in visible.split(",") if p.strip()]
    visible = [str(v).strip() for v in visible if str(v).strip()]

    try:
        confidence = float(payload.get("confidence", 0) or 0)
    except Exception:
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    narration_summary = re.sub(r"\s+", " ", str(payload.get("narration_summary", "") or "")).strip()
    if len(narration_summary) > 240:
        narration_summary = narration_summary[:240].rsplit(" ", 1)[0]

    if replacements:
        log.info(f"Sanitized subject_desc: {', '.join(replacements)} replacements")
    return {
        "shot_type": shot_type,
        "camera_move": camera_move,
        "subject_desc": subject_desc,
        "visible_characters": visible,
        "confidence": confidence,
        "narration_summary": narration_summary,
        "scene_class": scene_class,
    }


def parse_shot_fallback_text(text):
    data = {
        "shot_type": "medium shot",
        "camera_move": "static tripod shot",
        "subject_desc": "main subject in scene",
        "visible_characters": [],
        "confidence": 0,
    }
    for line in str(text or "").splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower().replace(" ", "_")
        if key in data:
            data[key] = value.strip()
    return validate_shot_payload(data)


VISION_PROMPT_TEMPLATE = """Analyze this keyframe for Veo prompt generation.
Return JSON only with shot_type, camera_move, scene_class, subject_desc, visible_characters, confidence and narration_summary.
Transcript: {transcript}
Global context: {global_context}
Previous context: {previous_context}
Character aliases: {character_aliases}
Allowed shot types: {shot_types}
Allowed camera moves: {camera_moves}
"""

CUTAWAY_TEMPLATES = {
    "MAP_OVERVIEW": ["animated map route with highlighted regions", "wide atlas-style map showing geographic context"],
    "CHARACTER": ["generic historical figure performing the key action", "anonymous narrator-like character in the scene"],
    "LANDMARK": ["recognizable landmark or building establishing the location", "monumental architecture tied to the narration"],
    "DOCUMENT": ["aged document, map, newspaper, or archival page", "close-up of records and handwritten notes"],
    "OBJECT": ["symbolic object central to the story", "detailed prop on a table under cinematic light"],
    "ATMOSPHERE": ["moody environmental scene expressing the narration", "wide scenic background with dramatic weather"],
}


def _compute_required_class(scene_num):
    classes = list(VALID_SCENE_CLASSES)
    try:
        idx = int(scene_num) - 1
    except Exception:
        return ""
    return classes[idx % len(classes)] if idx >= 0 else ""


def _format_previous_context(previous_context):
    if not previous_context:
        return "(none - this is scene 1. Choose any appropriate class.)"
    rows = []
    for item in list(previous_context)[-5:]:
        if isinstance(item, dict):
            num = item.get("scene_num", "?")
            cls = item.get("class", item.get("scene_class", "?"))
            desc = str(item.get("subject_desc", ""))[:80]
            rows.append(f"  Scene {num}: [{cls}] {desc}")
    return "\n".join(rows) or "(none)"


def build_vision_prompt(transcript, global_context, previous_context, character_aliases):
    previous = _format_previous_context(previous_context)
    aliases = ", ".join(character_aliases or []) or "(none)"
    return VISION_PROMPT_TEMPLATE.format(
        transcript=(transcript or "(no audio)")[:300],
        global_context=(global_context or "(none)")[:200],
        previous_context=previous,
        character_aliases=aliases,
        shot_types="\n".join(f"- {s}" for s in VEO3_SHOT_TYPES),
        camera_moves="\n".join(f"- {m}" for m in VEO3_CAMERA_MOVES),
    )


def build_batch_vision_prompt(transcripts, global_context, previous_context, character_aliases):
    scene_lines = []
    for i, text in enumerate(transcripts or [], 1):
        scene_lines.append(f'SCENE_{i}: "{(text or "(no audio)")[:300]}"')
    base = build_vision_prompt("(see SCENE transcripts below)", global_context, previous_context, character_aliases)
    return (
        f"BATCH MODE - ANALYZE {len(scene_lines)} SCENES IN ONE RESPONSE.\n"
        + "\n".join(scene_lines)
        + "\nReturn one JSON object: {\"shots\": [shot_obj_1, ...]}.\n\n"
        + base
    )


def assemble_prompt(
    scene_num=1,
    shot_type="medium shot",
    camera_move="static tripod shot",
    subject_desc="main subject in scene",
    style_desc="",
    global_context="",
    narration="",
    visible_characters=None,
    character_aliases=None,
    voice_gender="",
):
    visible_characters = visible_characters or []
    character_aliases = character_aliases or []
    style = style_desc or STYLE_PRESETS.get(DEFAULT_STYLE_PRESET, "")
    subject = _sanitize_subject_desc(subject_desc)[0]
    context = f" in {global_context.strip()}" if global_context else ""
    people = f" featuring {', '.join(visible_characters)}" if visible_characters else ""
    prompt = f"SCENE_{int(scene_num):03d}. Shot: {shot_type}, {camera_move}, {subject}{context}{people}. Style: {style}."

    words = str(narration or "").strip().replace('"', "'").replace("“", "'").replace("”", "'")
    if words:
        if voice_gender == "male":
            voice = "the same male documentary narrator throughout - a mature warm baritone in his early 40s, deep chest resonance, measured confident pace around 130 words per minute, clear articulation, calm authoritative delivery like a seasoned BBC documentary presenter"
        elif voice_gender == "female":
            voice = "the same female documentary narrator throughout - a mature warm alto in her mid-30s, rich mid-range timbre with subtle chest resonance, measured confident pace around 130 words per minute, clear articulation, calm authoritative delivery like a seasoned documentary presenter"
        else:
            voice = "a consistent documentary narrator"
        prompt += f' Audio: voiceover by {voice}, saying exactly: "{words}". Purely cinematic visual composition - the narration is delivered only through the audio channel.'
    return re.sub(r"\s+", " ", prompt).strip()


def enforce_scene_cap(scenes, max_scenes=MAX_SCENES):
    scenes = list(scenes or [])
    if len(scenes) <= max_scenes:
        return scenes
    if max_scenes <= 0:
        return []
    step = len(scenes) / max_scenes
    kept = []
    for i in range(max_scenes):
        kept.append(scenes[min(int(round(i * step)), len(scenes) - 1)])
    return kept


def _max_scenes_for_duration(duration):
    try:
        duration = float(duration or 0)
    except Exception:
        duration = 0.0
    if duration <= 0:
        return MAX_SCENES
    return max(1, min(MAX_SCENES, int(duration // VEO_VIDEO_LENGTH) or 1))


def _url_cache_key(url):
    return hashlib.sha256(str(url).encode("utf-8")).hexdigest()[:16]


def _get_cache_dir(url):
    d = Path(DATA_DIR) / "youtube_cache" / _url_cache_key(url)
    d.mkdir(parents=True, exist_ok=True)
    return d


_MASTER_SCRIPT_PROMPT = """You are a professional documentary scriptwriter.
Rewrite the transcript into exactly <<BEAT_COUNT>> short narration beats.
Output only JSON with overall_story, language and beats."""


class YouTubeAnalyzer:
    """Download and analyze YouTube videos into Veo prompts."""

    _whisper_model_cache: dict = {}

    def __init__(self, use_cache=True):
        self._temp_dir = None
        self._cache_dir = None
        self._use_cache = use_cache
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    @property
    def temp_dir(self):
        if self._temp_dir is None:
            self._temp_dir = tempfile.mkdtemp(prefix="navtools_yt_")
        return self._temp_dir

    def _setup_cache_for(self, url):
        self._cache_dir = _get_cache_dir(url) if self._use_cache else None
        if self._cache_dir:
            log.info(f"[cache] dir: {self._cache_dir}")
        return self._cache_dir

    def cleanup(self):
        if self._temp_dir:
            shutil.rmtree(self._temp_dir, ignore_errors=True)
            self._temp_dir = None

    def _yt_dlp_cmd(self):
        """Return a runnable yt-dlp command prefix.

        GUI apps on macOS often launch without Homebrew paths in PATH, so
        shutil.which("yt-dlp") may fail even when /opt/homebrew/bin/yt-dlp exists.
        """
        candidates = []
        env_path = os.environ.get("NAVTOOLS_YT_DLP")
        if env_path:
            candidates.append(Path(env_path))
        found = shutil.which("yt-dlp")
        if found:
            candidates.append(Path(found))
        base_dir = Path(__file__).resolve().parents[1]
        candidates.extend(
            [
                base_dir / "yt-dlp",
                base_dir / "yt-dlp.exe",
                base_dir / "bin" / "yt-dlp",
                base_dir / "bin" / "yt-dlp.exe",
                Path("/opt/homebrew/bin/yt-dlp"),
                Path("/usr/local/bin/yt-dlp"),
            ]
        )
        for candidate in candidates:
            if candidate and candidate.exists():
                return [str(candidate)]
        try:
            import importlib.util

            if importlib.util.find_spec("yt_dlp") is not None:
                return [sys.executable, "-m", "yt_dlp"]
        except Exception:
            pass
        raise RuntimeError(
            "Không tìm thấy yt-dlp. Cài bằng: brew install yt-dlp hoặc pip install yt-dlp. "
            "Nếu đã cài, đặt biến NAVTOOLS_YT_DLP trỏ tới file yt-dlp."
        )

    async def download(self, url, progress_cb=None):
        self._setup_cache_for(url)
        cached = self._cache_dir / "video.mp4" if self._cache_dir else None
        meta_file = self._cache_dir / "metadata.json" if self._cache_dir else None
        if cached and cached.exists():
            meta = {}
            if meta_file and meta_file.exists():
                try:
                    meta = json.loads(meta_file.read_text(encoding="utf-8"))
                except Exception:
                    meta = {}
            return str(cached), meta.get("title", ""), float(meta.get("duration", 0) or 0)

        output = str(Path(self.temp_dir) / "video.%(ext)s")
        yt_dlp = self._yt_dlp_cmd()
        common_args = [
            "--merge-output-format", "mp4",
            "--no-playlist",
            "--no-update",
            "-o", output,
            "--print-json",
        ]
        # Download strategies ordered by reliability.
        # YouTube SABR may block separate-stream formats for some clients,
        # so we try multiple client/format combos and stop at the first success.
        strategies = [
            {"format": "bv*[height<=720]+ba/b[height<=720]/best", "extra": []},
            {"format": "b[height<=720]/best", "extra": ["--extractor-args", "youtube:player_client=android"]},
            {"format": "18/b/best", "extra": ["--extractor-args", "youtube:player_client=android"]},
        ]
        if progress_cb:
            progress_cb("Downloading video...")
        proc = None
        for strategy in strategies:
            cmd = yt_dlp + strategy["extra"] + common_args + ["-f", strategy["format"], url]
            proc = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                creationflags=get_subprocess_flags(),
            )
            if proc.returncode == 0:
                break
            log.warning(f"yt-dlp strategy {strategy!r} failed (rc={proc.returncode}), trying next...")
        if proc is None or proc.returncode != 0:
            stderr = (proc.stderr.strip() if proc else "") or "yt-dlp download failed"
            raise RuntimeError(stderr)

        info = {}
        for line in proc.stdout.splitlines()[::-1]:
            try:
                info = json.loads(line)
                break
            except Exception:
                continue
        title = info.get("title", "")
        duration = float(info.get("duration", 0) or 0)
        files = [p for p in Path(self.temp_dir).iterdir() if p.suffix.lower() in (".mp4", ".webm", ".mkv")]
        if not files:
            raise RuntimeError("Downloaded video file was not found")
        video_path = files[0]
        if cached:
            shutil.copy2(video_path, cached)
            meta_file.write_text(json.dumps({"title": title, "duration": duration, "url": url}, ensure_ascii=False), encoding="utf-8")
            video_path = cached
        return str(video_path), title, duration

    async def detect_scenes(self, video_path, duration=None, progress_cb=None):
        if progress_cb:
            progress_cb("Detecting scenes...")
        cache_file = self._cache_dir / "scenes.json" if self._cache_dir else None
        if cache_file and cache_file.exists():
            try:
                return json.loads(cache_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        scenes = await asyncio.to_thread(self._detect_scenes_ffmpeg, video_path, duration, progress_cb)
        scenes = enforce_scene_cap(scenes, _max_scenes_for_duration(duration))
        if cache_file:
            cache_file.write_text(json.dumps(scenes, ensure_ascii=False, indent=2), encoding="utf-8")
        return scenes

    def _pad_with_fixed_frames(self, video_path, scenes, duration, target_count, progress_cb=None):
        scenes = list(scenes or [])
        if not duration or len(scenes) >= target_count:
            return scenes
        step = max(float(duration) / max(target_count, 1), MIN_SCENE_DURATION_SEC)
        existing = {(round(s.get("start", 0)), round(s.get("end", 0))) for s in scenes if isinstance(s, dict)}
        for i in range(target_count):
            start = i * step
            end = min(float(duration), start + step)
            key = (round(start), round(end))
            if key not in existing:
                scenes.append({"scene_num": len(scenes) + 1, "start": start, "end": end, "keyframe": ""})
        scenes.sort(key=lambda s: s.get("start", 0))
        for i, scene in enumerate(scenes, 1):
            scene["scene_num"] = i
        return scenes[:target_count]

    def _detect_scenes_ffmpeg(self, video_path, duration=None, progress_cb=None):
        total = float(duration or 0)
        count = _max_scenes_for_duration(total)
        scenes = []
        frames_dir = Path(self.temp_dir) / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)

        try:
            import cv2
            _have_cv2 = True
        except ImportError:
            _have_cv2 = False
            log.info("cv2 not available — using ffmpeg for keyframe extraction")

        if _have_cv2:
            cap = cv2.VideoCapture(str(video_path))
            if not cap.isOpened():
                raise RuntimeError("Cannot open video for scene extraction")
            fps = cap.get(cv2.CAP_PROP_FPS) or 25
            frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
            if not total:
                total = frame_count / fps if fps else 0
            count = _max_scenes_for_duration(total)
            for i in range(count):
                start = i * VEO_VIDEO_LENGTH
                end = min(total or start + VEO_VIDEO_LENGTH, start + VEO_VIDEO_LENGTH)
                mid = (start + end) / 2
                cap.set(cv2.CAP_PROP_POS_MSEC, mid * 1000)
                ok, frame = cap.read()
                keyframe = frames_dir / f"scene_{i + 1:03d}.jpg"
                if ok:
                    _safe_imwrite(str(keyframe), frame)
                scenes.append({"scene_num": i + 1, "start": start, "end": end, "keyframe": str(keyframe)})
            cap.release()
        else:
            ffmpeg = str(FFMPEG_PATH) if FFMPEG_PATH else "ffmpeg"
            for i in range(count):
                start = i * VEO_VIDEO_LENGTH
                end = min(total or start + VEO_VIDEO_LENGTH, start + VEO_VIDEO_LENGTH)
                mid = (start + end) / 2
                keyframe = frames_dir / f"scene_{i + 1:03d}.jpg"
                cmd = [
                    ffmpeg, "-y", "-ss", str(mid), "-i", str(video_path),
                    "-vframes", "1", "-q:v", "2", str(keyframe),
                ]
                try:
                    subprocess.run(
                        cmd,
                        capture_output=True,
                        timeout=30,
                        creationflags=get_subprocess_flags(),
                    )
                except Exception as e:
                    log.warning(f"ffmpeg keyframe {i+1} failed: {e}")
                scenes.append({"scene_num": i + 1, "start": start, "end": end, "keyframe": str(keyframe)})
        return scenes

    @classmethod
    def _get_whisper_model(cls, model_name=WHISPER_MODEL_DEFAULT):
        if model_name not in cls._whisper_model_cache:
            import whisper

            cls._whisper_model_cache[model_name] = whisper.load_model(model_name)
        return cls._whisper_model_cache[model_name]

    @staticmethod
    def _load_wav_as_numpy(path):
        import numpy as np
        import wave

        with wave.open(str(path), "rb") as wav:
            raw = wav.readframes(wav.getnframes())
            arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        return arr

    async def extract_transcript(self, video_path, progress_cb=None):
        cache_file = self._cache_dir / "transcript.json" if self._cache_dir else None
        if cache_file and cache_file.exists():
            try:
                return json.loads(cache_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        if progress_cb:
            progress_cb("Extracting transcript...")
        audio_path = Path(self.temp_dir) / "audio.wav"
        cmd = [str(FFMPEG_PATH), "-y", "-i", str(video_path), "-vn", "-ac", "1", "-ar", "16000", str(audio_path)]
        await asyncio.to_thread(
            subprocess.run,
            cmd,
            capture_output=True,
            text=True,
            timeout=FFMPEG_AUDIO_EXTRACT_TIMEOUT,
            creationflags=get_subprocess_flags(),
        )
        model = await asyncio.to_thread(self._get_whisper_model, WHISPER_MODEL_DEFAULT)
        result = await asyncio.to_thread(model.transcribe, str(audio_path), language=WHISPER_LANGUAGE, fp16=False)
        segments = result.get("segments", []) if isinstance(result, dict) else []
        self._last_segments = segments
        if cache_file:
            cache_file.write_text(json.dumps(segments, ensure_ascii=False, indent=2), encoding="utf-8")
        return segments

    def _probe_audio_duration(self, audio_path):
        cmd = [str(FFMPEG_PATH).replace("ffmpeg", "ffprobe"), "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(audio_path)]
        proc = subprocess.run(cmd, capture_output=True, text=True, creationflags=get_subprocess_flags())
        try:
            return float(proc.stdout.strip())
        except Exception:
            return 0.0

    def _whisper_chunked(self, model, audio_path, progress_cb=None):
        return model.transcribe(str(audio_path), language=WHISPER_LANGUAGE, fp16=False).get("segments", [])

    def align_transcript_to_scenes(self, scenes, segments):
        aligned = []
        for scene in scenes or []:
            start = float(scene.get("start", 0))
            end = float(scene.get("end", start))
            parts = []
            for seg in segments or []:
                if float(seg.get("end", 0)) >= start and float(seg.get("start", 0)) <= end:
                    parts.append(str(seg.get("text", "")).strip())
            item = dict(scene)
            item["transcript"] = " ".join(p for p in parts if p).strip()
            aligned.append(item)
        return aligned

    async def suggest_global_context(self, title, transcript, gemini_api_key, progress_cb=None):
        if not transcript:
            return title or ""
        prompt = "Summarize this video in one concise production context paragraph:\n" + str(transcript)[:4000]
        try:
            return (await agenerate_with_fallback(prompt, api_key=gemini_api_key)).strip()
        except Exception as e:
            log.warning(f"Global context suggestion failed: {e}")
            return title or ""

    async def generate_master_script(self, segments, duration, beat_count, language_hint, character_note, gemini_api_key, progress_cb=None):
        full = "\n".join(f"[{s.get('start', 0):.1f}-{s.get('end', 0):.1f}] {s.get('text', '')}" for s in segments or [])
        prompt = (
            _MASTER_SCRIPT_PROMPT.replace("<<BEAT_COUNT>>", str(beat_count))
            .replace("<<LANGUAGE_HINT>>", language_hint or "English")
            .replace("<<FULL_TRANSCRIPT>>", full)
            .replace("<<TOTAL_DURATION>>", str(duration))
            .replace("<<CHARACTER_NOTE>>", character_note or "(none)")
        )
        try:
            raw = await agenerate_with_fallback(prompt, api_key=gemini_api_key)
            return json.loads(str(raw).strip().strip("`"))
        except Exception as e:
            log.warning(f"Master script generation failed: {e}")
            beats = []
            for i in range(int(beat_count or 0)):
                beats.append({
                    "beat_id": i + 1,
                    "start_time": i * VEO_VIDEO_LENGTH,
                    "end_time": (i + 1) * VEO_VIDEO_LENGTH,
                    "narration": "",
                    "visual_intent": VALID_SCENE_CLASSES[i % len(VALID_SCENE_CLASSES)],
                    "key_entities": [],
                })
            return {"overall_story": "", "language": language_hint or "en", "beats": beats}

    async def translate_segments_to_vi(self, segments, gemini_api_key, progress_cb=None):
        texts = [str(s.get("text", "")).strip() for s in segments or []]
        if not texts:
            return []
        prompt = "Translate each transcript segment to Vietnamese, return JSON array of strings:\n" + json.dumps(texts, ensure_ascii=False)
        try:
            raw = await agenerate_with_fallback(prompt, api_key=gemini_api_key)
            translated = json.loads(str(raw).strip().strip("`"))
            out = []
            for seg, text in zip(segments, translated):
                item = dict(seg)
                item["text_vi"] = text
                out.append(item)
            return out
        except Exception as e:
            log.warning(f"Vietnamese translation failed: {e}")
            return [dict(s, text_vi=s.get("text", "")) for s in segments or []]

    def align_transcript_to_scenes_vi(self, scenes, segments):
        aligned = self.align_transcript_to_scenes(scenes, segments)
        for scene in aligned:
            start = float(scene.get("start", 0))
            end = float(scene.get("end", start))
            parts = []
            for seg in segments or []:
                if float(seg.get("end", 0)) >= start and float(seg.get("start", 0)) <= end:
                    parts.append(str(seg.get("text_vi", seg.get("text", ""))).strip())
            scene["transcript_vi"] = " ".join(p for p in parts if p).strip()
        return aligned

    async def extract_style_from_reference_images(self, image_paths, gemini_api_key, progress_cb=None):
        if not image_paths:
            return ""
        prompt = "Describe the shared visual style of these reference images in one compact Veo-ready style phrase."
        try:
            return (await self._genai_vision_json(image_paths[0], prompt, gemini_api_key, None)).get("style", "")
        except Exception as e:
            log.warning(f"Reference style extraction failed: {e}")
            return ""

    def _init_genai(self):
        import google.generativeai as genai

        return genai

    async def _genai_vision_json(self, image_path, prompt, gemini_api_key, schema=None):
        data = Path(image_path).read_bytes()
        encoded = base64.b64encode(data).decode("ascii")
        full_prompt = f"{prompt}\nImage base64 JPEG:\n{encoded[:120000]}"
        raw = await agenerate_with_fallback(full_prompt, api_key=gemini_api_key)
        text = str(raw).strip()
        match = re.search(r"\{.*\}", text, re.S)
        return json.loads(match.group(0) if match else text)

    async def _genai_vision_batch_json(self, image_paths, prompt, gemini_api_key, schema=None):
        chunks = [prompt]
        for i, image_path in enumerate(image_paths or [], 1):
            data = Path(image_path).read_bytes()
            chunks.append(f"\nSCENE_{i} IMAGE BASE64:\n{base64.b64encode(data).decode('ascii')[:80000]}")
        raw = await agenerate_with_fallback("\n".join(chunks), api_key=gemini_api_key)
        text = str(raw).strip()
        match = re.search(r"\{.*\}", text, re.S)
        return json.loads(match.group(0) if match else text)

    async def _genai_vision_with_retry(self, image_path, prompt, gemini_api_key, schema=None, retries=2):
        last_error = None
        for _ in range(max(1, retries + 1)):
            try:
                return await self._genai_vision_json(image_path, prompt, gemini_api_key, schema)
            except Exception as e:
                last_error = e
                await asyncio.sleep(1)
        raise last_error

    async def generate_captions(
        self,
        scenes,
        gemini_api_key,
        style_lock=None,
        global_context="",
        character_aliases=None,
        progress_cb=None,
        quick_mode=False,
        voice_gender="",
        use_batch=True,
        style_desc="",
        previous_context=None,
        master_beats=None,
    ):
        captions = []
        previous_context = list(previous_context or [])
        character_aliases = character_aliases or []
        for i, scene in enumerate(scenes or [], 1):
            if self._cancelled:
                raise RuntimeError("Analysis cancelled")
            if progress_cb:
                progress_cb(f"Analyzing scene {i}/{len(scenes)}")
            transcript = scene.get("transcript_vi") or scene.get("transcript") or ""
            payload = {}
            if not quick_mode and scene.get("keyframe") and Path(scene["keyframe"]).exists():
                prompt = build_vision_prompt(transcript, global_context, previous_context, character_aliases)
                try:
                    payload = await self._genai_vision_with_retry(scene["keyframe"], prompt, gemini_api_key, SHOT_SCHEMA)
                except Exception as e:
                    log.warning(f"Vision analysis failed for scene {i}: {e}")
            shot = validate_shot_payload(payload)
            beat = master_beats[i - 1] if master_beats and i - 1 < len(master_beats) else {}
            narration = beat.get("narration") or shot.get("narration_summary") or transcript
            prompt_text = assemble_prompt(
                scene_num=i,
                shot_type=shot["shot_type"],
                camera_move=shot["camera_move"],
                subject_desc=shot["subject_desc"],
                style_desc=style_desc or STYLE_PRESETS.get(style_lock or DEFAULT_STYLE_PRESET, ""),
                global_context=global_context,
                narration=narration,
                visible_characters=shot.get("visible_characters"),
                character_aliases=character_aliases,
                voice_gender=voice_gender,
            )
            item = dict(scene)
            item.update(shot)
            item["prompt"] = prompt_text
            item["caption"] = prompt_text
            captions.append(item)
            previous_context.append({"scene_num": i, "class": shot["scene_class"], "subject_desc": shot["subject_desc"]})
        return captions

    async def reanalyze_scene(
        self,
        scene,
        gemini_api_key,
        style_lock=None,
        global_context="",
        character_aliases=None,
        previous_context=None,
        voice_gender="",
        style_desc="",
    ):
        captions = await self.generate_captions(
            [scene],
            gemini_api_key,
            style_lock=style_lock,
            global_context=global_context,
            character_aliases=character_aliases,
            previous_context=previous_context,
            voice_gender=voice_gender,
            style_desc=style_desc,
        )
        return captions[0] if captions else {}

    async def analyze(
        self,
        url,
        gemini_api_key,
        style_lock=DEFAULT_STYLE_PRESET,
        global_context="",
        character_aliases=None,
        use_whisper=True,
        quick_mode=False,
        translate_to_vi=False,
        auto_suggest_context=False,
        voice_gender="",
        progress_cb=None,
    ):
        warnings = []
        video_path, title, duration = await self.download(url, progress_cb)
        if duration > LONG_VIDEO_WARNING_THRESHOLD:
            warnings.append(f"Video is long ({duration:.0f}s); analysis may take longer.")
        if auto_suggest_context and not global_context:
            try:
                global_context = await self.suggest_global_context(title, "", gemini_api_key, progress_cb)
            except Exception as e:
                log.warning(f"Context auto-suggest failed: {e}")
        scenes = await self.detect_scenes(video_path, duration, progress_cb)
        segments = []
        if use_whisper:
            try:
                segments = await self.extract_transcript(video_path, progress_cb)
                scenes = self.align_transcript_to_scenes(scenes, segments)
                if translate_to_vi:
                    vi_segments = await self.translate_segments_to_vi(segments, gemini_api_key, progress_cb)
                    scenes = self.align_transcript_to_scenes_vi(scenes, vi_segments)
            except Exception as e:
                warnings.append(f"Transcript unavailable: {e}")
        scenes = enforce_scene_cap(scenes, _max_scenes_for_duration(duration))
        master = await self.generate_master_script(
            segments,
            duration,
            len(scenes),
            "vi" if translate_to_vi else "English",
            ", ".join(character_aliases or []),
            gemini_api_key,
            progress_cb,
        ) if segments else {"beats": []}
        captions = await self.generate_captions(
            scenes,
            gemini_api_key,
            style_lock=style_lock,
            global_context=global_context,
            character_aliases=character_aliases,
            progress_cb=progress_cb,
            quick_mode=quick_mode,
            voice_gender=voice_gender,
            master_beats=master.get("beats", []),
        )
        return {
            "title": title,
            "duration": duration,
            "video_path": video_path,
            "global_context": global_context,
            "warnings": warnings,
            "scenes": captions,
            "captions": captions,
            "segments": segments,
            "master_script": master,
        }


__all__ = [
    "STYLE_PRESETS",
    "DEFAULT_STYLE_PRESET",
    "VEO3_SHOT_TYPES",
    "VEO3_CAMERA_MOVES",
    "CONFIDENCE_WARNING_THRESHOLD",
    "SHOT_SCHEMA",
    "MAX_SCENES",
    "VEO_VIDEO_LENGTH",
    "assemble_prompt",
    "normalize_to_whitelist",
    "_max_scenes_for_duration",
    "LONG_VIDEO_WARNING_THRESHOLD",
    "VERY_LONG_VIDEO_CONFIRM",
    "YouTubeAnalyzer",
]
