"""Smoke test VieNeu-TTS.

First run downloads ~1-2GB of models from HuggingFace Hub to
~/.cache/huggingface/hub/. Subsequent runs are instant.

Tests Vietnamese synthesis quality with a sample that includes:
- Historical names (Khomeini, Cyrus) — verify no content filter
- Numbers and dates (1979, 550 TCN)
- Code-switching (English words in Vietnamese)
"""

from __future__ import annotations

import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "scripts" / "tts_samples"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8")

    print("=" * 70)
    print("🔊 VieNeu-TTS Smoke Test")
    print("=" * 70)

    samples = [
        (
            "historical_vn",
            "Cyrus Đại Đế sáng lập đế chế Ba Tư cổ đại vào năm 550 trước Công nguyên.",
        ),
        (
            "modern_vn",
            "Năm 1979, Ayatollah Khomeini trở về Iran và sáng lập Cộng hòa Hồi giáo.",
        ),
        (
            "codeswitch",
            "Hệ thống này dùng AI inpainting để xóa watermark Veo 3 khỏi video.",
        ),
    ]

    print("\nLoading VieNeu (mode=turbo)... first run will download ~1-2GB")
    t0 = time.time()
    from vieneu import Vieneu

    tts = Vieneu(mode="turbo", device="cpu")
    print(f"✓ Loaded in {time.time() - t0:.1f}s")

    voices = getattr(tts, "voices", None) or getattr(tts, "list_voices", lambda: None)()
    if voices:
        print("\nBuilt-in voices:")
        if isinstance(voices, dict):
            for k in list(voices.keys())[:10]:
                print(f"  - {k}")
        elif isinstance(voices, (list, tuple)):
            for v in voices[:10]:
                print(f"  - {v}")

    for name, text in samples:
        print(f"\n── {name} ──")
        print(f"Text: {text}")
        t0 = time.time()
        try:
            audio = tts.infer(text=text)
            elapsed = time.time() - t0
            out_path = OUT_DIR / f"{name}.wav"
            tts.save(audio, str(out_path))
            size_kb = out_path.stat().st_size // 1024
            print(f"✓ Synthesized in {elapsed:.2f}s → {out_path.name} ({size_kb} KB)")
        except Exception as e:
            print(f"✗ Failed: {type(e).__name__}: {e}")

    print()
    print("=" * 70)
    print(f"Samples saved in: {OUT_DIR}")
    print("Anh mở file WAV để nghe quality:")
    for name, _ in samples:
        print(f"  {OUT_DIR / (name + '.wav')}")


if __name__ == "__main__":
    main()
