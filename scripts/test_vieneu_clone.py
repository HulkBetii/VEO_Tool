"""Test VieNeu-TTS voice cloning — pass ANY audio/video, get quality samples.

Usage:
    python scripts/test_vieneu_clone.py <path_to_audio_or_video>

    # Examples:
    python scripts/test_vieneu_clone.py "C:/Downloads/podcast.mp3"
    python scripts/test_vieneu_clone.py "D:/videos/rome.mp4"
    python scripts/test_vieneu_clone.py scripts/tts_samples/ZZ_turbo_medium.wav

What it does:
    1. Extract an 8-second clean clip from the source (skips first 1s
       to avoid intro silence).
    2. Encode it as a VieNeu reference voice.
    3. Synthesize 3 Vietnamese test sentences using that voice.
    4. Save outputs alongside the script so anh can compare turbo
       preset vs voice-cloned quality.

Tips for a GOOD reference:
    - Single speaker, no music, no background noise.
    - Clear pronunciation, neutral tone.
    - At least 10s of source audio (we only take 8s but need buffer).
    - Vietnamese preferred (English also works for cloning timbre).
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
    """Use ffmpeg to cut a mono 24kHz WAV clip from the source.

    VieNeu likes 16-24kHz mono WAV. We use 24kHz to match the codec.
    """
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


def synth_with_ref(tts, text: str, ref_encoded, label: str) -> None:
    out = OUT_DIR / f"{label}.wav"
    t0 = time.time()
    try:
        audio = tts.infer(text=text, voice=ref_encoded)
        tts.save(audio, str(out))
        size_kb = out.stat().st_size // 1024
        print(f"  ✓ {out.name} ({size_kb}KB, {time.time() - t0:.1f}s)")
    except Exception as e:
        print(f"  ✗ {label}: {type(e).__name__}: {e}")


def synth_with_preset(tts, text: str, voice: str, label: str) -> None:
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

    if len(sys.argv) < 2:
        print(__doc__)
        print("\n❌ Missing argument: path to source audio/video.\n")
        sys.exit(1)

    src = Path(sys.argv[1]).expanduser().resolve()
    if not src.exists():
        print(f"❌ File not found: {src}")
        sys.exit(1)

    print("━" * 70)
    print("🎙️  VieNeu-TTS Voice Cloning Test")
    print("━" * 70)
    print(f"Source:   {src}")
    print(f"Size:     {src.stat().st_size / 1024:.0f}KB")
    print()

    print("Step 1 — Extract 8s reference clip")
    ref_wav = OUT_DIR / "_ref_clip.wav"
    if not extract_reference_clip(src, ref_wav, start=1, duration=8):
        print("  Trying without skip...")
        if not extract_reference_clip(src, ref_wav, start=0, duration=8):
            print("❌ Could not extract reference. Is ffmpeg installed?")
            sys.exit(1)

    print(f"  ✓ {ref_wav.name} ({ref_wav.stat().st_size // 1024}KB)")

    print("\nStep 2 — Load VieNeu-TTS (turbo) and encode reference")
    from vieneu import Vieneu

    t0 = time.time()
    tts = Vieneu(mode="turbo", device="cpu")
    print(f"  ✓ Loaded in {time.time() - t0:.1f}s")

    t0 = time.time()
    try:
        ref = tts.encode_reference(str(ref_wav))
        print(f"  ✓ Encoded reference in {time.time() - t0:.1f}s")
    except Exception as e:
        print(f"  ✗ Failed to encode reference: {type(e).__name__}: {e}")
        print("\n  Common causes:")
        print("    - Audio too short (<5s needed)")
        print("    - Multiple speakers in the clip")
        print("    - Background music / noise")
        print("    - Unsupported format")
        sys.exit(1)

    short = "Xin chào, đây là giọng đọc cho video của bạn."
    medium = "Cyrus Đại Đế sáng lập đế chế Ba Tư vào năm 550 trước Công nguyên."
    long = (
        "Năm 550 trước Công nguyên, Cyrus Đại Đế sáng lập đế chế Ba Tư. "
        "Đây là đế chế hùng mạnh nhất thế giới cổ đại."
    )

    src_tag = src.stem[:20].replace(" ", "_")

    print(f"\nStep 3 — Synthesize with CLONED voice (tag: {src_tag})")
    synth_with_ref(tts, short, ref, f"CLONE_{src_tag}_short")
    synth_with_ref(tts, medium, ref, f"CLONE_{src_tag}_medium")
    synth_with_ref(tts, long, ref, f"CLONE_{src_tag}_long")

    print("\nStep 4 — Synthesize with PRESET Bích Ngọc (for A/B)")
    preset = "Bích Ngọc (Nữ - Miền Bắc)"
    synth_with_preset(tts, short, preset, "PRESET_BN_short")
    synth_with_preset(tts, medium, preset, "PRESET_BN_medium")
    synth_with_preset(tts, long, preset, "PRESET_BN_long")

    del tts
    gc.collect()

    print()
    print("━" * 70)
    print("✅ Done! Files to compare:")
    print("━" * 70)
    for f in sorted(OUT_DIR.glob("CLONE_*.wav")):
        print(f"  🎯 {f}")
    for f in sorted(OUT_DIR.glob("PRESET_BN_*.wav")):
        print(f"  📦 {f}")

    print()
    print("Mở file cùng label (short/medium/long) để so sánh:")
    print("  CLONE_*_short.wav  vs  PRESET_BN_short.wav")
    print()
    print("Nếu CLONE hay hơn → voice cloning work! Chọn file reference")
    print("khác nếu chưa hài lòng. Nếu PRESET vẫn hay hơn → reference")
    print("không đủ sạch (có noise/nhiều speaker).")


if __name__ == "__main__":
    main()
