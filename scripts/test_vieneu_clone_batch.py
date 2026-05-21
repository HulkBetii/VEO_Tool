"""Batch voice cloning test — clone from ngochuyen + minhquan in ONE model load.

Loads VieNeu-TTS once, then synthesizes the SAME 3 Vietnamese test sentences
with:
    1. Voice clone từ ngochuyen.mp3 (nữ)
    2. Voice clone từ minhquan.mp3 (nam)
    3. Preset Bích Ngọc (female reference)
    4. Preset Phạm Tuyên (male reference)

Files saved with clear prefixes so anh can A/B easily:
    CLONE_ngochuyen_short.wav   vs   PRESET_BichNgoc_short.wav
    CLONE_minhquan_long.wav     vs   PRESET_PhamTuyen_long.wav

Saves ~55s per reload by reusing the Vieneu instance across all 4 voices.
"""

from __future__ import annotations

import gc
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "scripts" / "tts_samples"
OUT_DIR.mkdir(parents=True, exist_ok=True)

REFS = [
    ("ngochuyen", OUT_DIR / "ngochuyen.mp3"),
    ("minhquan", OUT_DIR / "minhquan.mp3"),
]

PRESETS = [
    ("BichNgoc", "Bích Ngọc (Nữ - Miền Bắc)"),
    ("PhamTuyen", "Phạm Tuyên (Nam - Miền Bắc)"),
]

SENTENCES = {
    "short": "Xin chào, đây là giọng đọc cho video của bạn.",
    "medium": "Cyrus Đại Đế sáng lập đế chế Ba Tư vào năm 550 trước Công nguyên.",
    "long": (
        "Năm 550 trước Công nguyên, Cyrus Đại Đế sáng lập đế chế Ba Tư. "
        "Đây là đế chế hùng mạnh nhất thế giới cổ đại."
    ),
}


def _ffmpeg_bin() -> str:
    try:
        sys.path.insert(0, str(ROOT))
        from config.constants import FFMPEG_PATH

        if Path(FFMPEG_PATH).exists():
            return str(FFMPEG_PATH)
    except Exception:
        return "ffmpeg"
    return "ffmpeg"


def extract_reference_clip(src: Path, out_wav: Path, start: float = 1, duration: float = 8) -> bool:
    """Cut mono 24kHz 16-bit PCM WAV from any audio/video source."""
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
            print(f"  ✗ ffmpeg failed: {r.stderr[-300:]}")
            return False
        return out_wav.exists() and out_wav.stat().st_size > 0
    except Exception as e:
        print(f"  ✗ ffmpeg exception: {e}")
        return False


def synth_one(tts, text: str, voice, label: str) -> None:
    out = OUT_DIR / f"{label}.wav"
    t0 = time.time()
    try:
        audio = tts.infer(text=text, voice=voice)
        tts.save(audio, str(out))
        size_kb = out.stat().st_size // 1024
        print(f"  ✓ {out.name} ({size_kb}KB, {time.time() - t0:.1f}s)")
    except Exception as e:
        print(f"  ✗ {label}: {type(e).__name__}: {e}")


def main():
    sys.stdout.reconfigure(encoding="utf-8")

    print("━" * 72)
    print("🎙️  VieNeu-TTS — Batch Voice Clone + Preset A/B Test")
    print("━" * 72)

    for tag, path in REFS:
        if not path.exists():
            print(f"❌ Missing reference: {path}")
            sys.exit(1)
        print(f"✓ {tag} ({path.name}, {path.stat().st_size / 1024:.0f}KB)")

    print()
    print("Step 1 — Extract 8s clean clips (mono 24kHz)")
    extracted_refs = {}
    for tag, src in REFS:
        clip_path = OUT_DIR / f"_ref_{tag}.wav"
        ok = extract_reference_clip(src, clip_path, start=1, duration=8)
        if not ok:
            ok = extract_reference_clip(src, clip_path, start=0, duration=8)
        if not ok:
            print(f"❌ Could not extract clip for {tag}")
            sys.exit(1)
        print(f"  ✓ {clip_path.name} ({clip_path.stat().st_size // 1024}KB)")
        extracted_refs[tag] = clip_path

    print()
    print("Step 2 — Load VieNeu-TTS (turbo, CPU)")
    from vieneu import Vieneu

    t0 = time.time()
    tts = Vieneu(mode="turbo", device="cpu")
    print(f"  ✓ Loaded in {time.time() - t0:.1f}s")

    print()
    print("Step 3 — Encode references as voice embeddings")
    encoded_refs = {}
    for tag, clip_path in extracted_refs.items():
        t0 = time.time()
        try:
            ref = tts.encode_reference(str(clip_path))
            encoded_refs[tag] = ref
            print(f"  ✓ {tag}: encoded in {time.time() - t0:.1f}s")
        except Exception as e:
            print(f"  ✗ {tag}: {type(e).__name__}: {e}")

    print()
    if not encoded_refs:
        print("❌ No references encoded successfully, aborting.")
        sys.exit(1)

    print("Step 4 — Synthesize (4 voices × 3 sentences = 12 files)")
    print()

    for tag, ref in encoded_refs.items():
        print(f"  ── CLONE: {tag} ──")
        for length, text in SENTENCES.items():
            synth_one(tts, text, ref, f"CLONE_{tag}_{length}")

    print()

    for tag, voice_name in PRESETS:
        print(f"  ── PRESET: {tag} ──")
        for length, text in SENTENCES.items():
            synth_one(tts, text, voice_name, f"PRESET_{tag}_{length}")

    del tts
    gc.collect()

    print()
    print("━" * 72)
    print("✅ Done! Comparison matrix:")
    print("━" * 72)
    print()
    print("  🟢 FEMALE voice comparison (cùng 3 câu):")
    for length in SENTENCES:
        print(f"     CLONE_ngochuyen_{length}.wav  ⇄  PRESET_BichNgoc_{length}.wav")

    print()
    print("  🔵 MALE voice comparison (cùng 3 câu):")
    for length in SENTENCES:
        print(f"     CLONE_minhquan_{length}.wav   ⇄  PRESET_PhamTuyen_{length}.wav")

    print()
    print(f"  📁 Tất cả files ở: {OUT_DIR}")
    print()
    print("  Cách nghe:")
    print("  1. Mở Explorer đến folder trên")
    print("  2. Click đôi từng file, nghe theo cặp")
    print("  3. Đánh giá: CLONE giữ được đặc trưng của ngochuyen/minhquan không?")
    print("  4. Nếu CLONE hay hơn PRESET → voice cloning là hướng đi đúng")


if __name__ == "__main__":
    main()
