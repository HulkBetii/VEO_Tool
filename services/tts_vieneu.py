"""NAV TOOLS — VieNeu-TTS service (offline Vietnamese, voice cloning only)."""

from __future__ import annotations

import asyncio
import subprocess
import threading
from pathlib import Path
from typing import Optional

from config.constants import ASSETS_DIR, BASE_DIR, FFMPEG_PATH
from utils.logger import log


VOICES = {
    "female": {"label": "Nữ (Ngọc Huyền)", "source_file": "ngochuyen.mp3", "gender": "female"},
    "male": {"label": "Nam (Minh Quân)", "source_file": "minhquan.mp3", "gender": "male"},
}
DEFAULT_VOICE = "female"

_VOICE_REFS_DIR = Path(ASSETS_DIR) / "assets" / "voice_refs"
_VOICE_CACHE_DIR = Path(BASE_DIR) / ".vidgen" / "voice_cache"
_tts_instance = None
_tts_lock = threading.Lock()
_tts_op_lock = threading.Lock()
_encoded_voice_cache = {}
_encode_lock = threading.Lock()


def list_voices():
    """Return the voice catalog for UI dropdowns / radio selectors."""
    return [{"id": vid, "label": meta["label"], "gender": meta["gender"]} for vid, meta in VOICES.items()]


def get_preview_path(voice_id):
    if voice_id not in VOICES:
        return None
    preview_dir = Path(ASSETS_DIR) / "assets" / "voice_refs"
    candidate = preview_dir / f"preview_{voice_id}.wav"
    if candidate.exists() and candidate.stat().st_size > 0:
        return candidate
    return None


def _ensure_cache_dir():
    _VOICE_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def get_tts():
    global _tts_instance
    if _tts_instance is not None:
        return _tts_instance
    with _tts_lock:
        if _tts_instance is not None:
            return _tts_instance
        try:
            from vieneu import Vieneu
        except ImportError:
            raise RuntimeError(
                "vieneu package not installed. Run: pip install vieneu --extra-index-url https://pnnbao97.github.io/llama-cpp-python-v0.3.16/cpu/"
            )
        log.info("[vieneu] Loading TTS (mode=turbo, device=cpu)")
        _tts_instance = Vieneu(mode="turbo", device="cpu")
        log.info("[vieneu] TTS ready")
        return _tts_instance


def _ffmpeg_bin():
    if Path(FFMPEG_PATH).exists():
        return str(FFMPEG_PATH)
    return "ffmpeg"


def _extract_reference_clip(src: Path, out_wav: Path, start: float = 1, duration: float = 8):
    """Cut a clean mono 24kHz 16-bit PCM WAV clip from any audio/video source."""
    ffmpeg = _ffmpeg_bin()
    cmd = [
        ffmpeg,
        "-y",
        "-ss",
        str(start),
        "-i",
        str(src),
        "-t",
        str(duration),
        "-ac",
        "1",
        "-ar",
        "24000",
        "-c:a",
        "pcm_s16le",
        "-vn",
        str(out_wav),
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            log.warning(f"[vieneu] ffmpeg ref extract failed: {r.stderr[-300:]}")
            return False
        return out_wav.exists() and out_wav.stat().st_size > 0
    except Exception as e:
        log.warning(f"[vieneu] ffmpeg ref extract exception: {e}")
        return False


def _get_encoded_voice(voice_id):
    """Return a VieNeu encoded reference for the given voice id."""
    if voice_id in _encoded_voice_cache:
        return _encoded_voice_cache[voice_id]
    if voice_id not in VOICES:
        raise ValueError(f"Unknown voice_id '{voice_id}'. Valid: {list(VOICES.keys())}")

    meta = VOICES[voice_id]
    src = _VOICE_REFS_DIR / meta["source_file"]
    if not src.exists():
        raise RuntimeError(f"Missing bundled voice reference: {src}. Reinstall the app to restore assets/voice_refs/.")

    _ensure_cache_dir()
    clip_path = _VOICE_CACHE_DIR / f"{voice_id}_clip.wav"
    if not (clip_path.exists() and clip_path.stat().st_size > 0):
        log.info(f"[vieneu] Extracting reference clip: {src.name}")
        ok = _extract_reference_clip(src, clip_path, start=1, duration=8)
        if not ok:
            ok = _extract_reference_clip(src, clip_path, start=0, duration=8)
        if not ok:
            raise RuntimeError(f"Could not extract reference clip from {src}")

    with _encode_lock:
        if voice_id in _encoded_voice_cache:
            return _encoded_voice_cache[voice_id]
        tts = get_tts()
        log.info(f"[vieneu] Encoding reference voice '{voice_id}'...")
        encoded = tts.encode_reference(str(clip_path))
        _encoded_voice_cache[voice_id] = encoded
        log.info(f"[vieneu] ✓ Voice '{voice_id}' ready")
        return encoded


def synth_to_file(text, output_path, voice=DEFAULT_VOICE):
    """Synthesize a Vietnamese sentence to a WAV file using a cloned voice."""
    if not text or not text.strip():
        log.warning("[vieneu] synth: empty text")
        return False
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        tts = get_tts()
    except Exception as e:
        log.error(f"[vieneu] TTS load failed: {e}")
        return False

    try:
        encoded = _get_encoded_voice(voice)
    except Exception as e:
        log.error(f"[vieneu] Voice '{voice}' load failed: {e}")
        return False

    try:
        with _tts_op_lock:
            audio = tts.infer(text=text, voice=encoded)
            tts.save(audio, str(output_path))
        if not output_path.exists() or output_path.stat().st_size == 0:
            log.error(f"[vieneu] output missing: {output_path}")
            return False
        size_kb = output_path.stat().st_size // 1024
        log.info(f"[vieneu] synth OK: {output_path.name} ({size_kb}KB, voice={voice})")
        return True
    except Exception as e:
        log.error(f"[vieneu] synth failed: {e}")
        return False


async def synth_to_file_async(text, output_path, voice=DEFAULT_VOICE):
    return await asyncio.to_thread(synth_to_file, text, output_path, voice)


def preload_voice(voice=DEFAULT_VOICE):
    _get_encoded_voice(voice)
    return True


def probe_duration(audio_path):
    """Return audio duration in seconds."""
    try:
        import soundfile as sf

        info = sf.info(str(audio_path))
        return float(info.frames) / float(info.samplerate)
    except Exception as e:
        log.debug(f"[vieneu] duration probe failed: {e}")
        return 0


def merge_audio_video(video_path, audio_path, output_path, ffmpeg_path=None):
    """Overlay a WAV audio track onto a silent MP4 video."""
    video_path = Path(video_path)
    audio_path = Path(audio_path)
    output_path = Path(output_path)
    if not video_path.exists():
        log.error(f"[merge] video not found: {video_path}")
        return False
    if not audio_path.exists():
        log.error(f"[merge] audio not found: {audio_path}")
        return False
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg_path = ffmpeg_path or _ffmpeg_bin()
    cmd = [
        str(ffmpeg_path),
        "-y",
        "-i",
        str(video_path),
        "-i",
        str(audio_path),
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-shortest",
        str(output_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            log.error(f"[merge] ffmpeg failed: {result.stderr[-500:]}")
            return False
        if not output_path.exists() or output_path.stat().st_size == 0:
            log.error(f"[merge] output empty: {output_path}")
            return False
        log.info(f"[merge] OK: {output_path.name}")
        return True
    except subprocess.TimeoutExpired:
        log.error("[merge] ffmpeg timeout")
        return False
    except Exception as e:
        log.error(f"[merge] ffmpeg exception: {e}")
        return False
