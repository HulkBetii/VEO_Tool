"""Compare VieNeu-TTS modes and quality knobs.

Dimensions tested:
    - mode:   turbo (GGUF Q4 CPU) vs standard (PyTorch full) vs fast (GPU)
    - length: short 1-chunk vs long 2-chunk sentence
    - voice:  Bích Ngọc (best candidate from previous test)

Saves each sample with a self-describing filename so anh can A/B them.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "scripts" / "tts_samples"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def synth_sample(tts, text: str, voice: str, label: str):
    out = OUT_DIR / f"{label}.wav"
    t0 = time.time()
    try:
        audio = tts.infer(text=text, voice=voice)
        tts.save(audio, str(out))
        size_kb = out.stat().st_size // 1024
        print(f"  ✓ {out.name} ({size_kb}KB, {time.time() - t0:.1f}s)")
    except Exception as e:
        print(f"  ✗ {label}: {e}")


def main():
    sys.stdout.reconfigure(encoding="utf-8")

    print("━" * 70)
    print("🔬 VieNeu-TTS Quality Comparison — turbo vs standard mode")
    print("━" * 70)

    from vieneu import Vieneu

    short = "Xin chào, đây là giọng đọc cho video của bạn."
    medium = "Cyrus Đại Đế sáng lập đế chế Ba Tư vào năm 550 trước Công nguyên."
    long = (
        "Năm 550 trước Công nguyên, Cyrus Đại Đế sáng lập đế chế Ba Tư. "
        "Đây là đế chế hùng mạnh nhất thế giới cổ đại."
    )
    voice = "Bích Ngọc (Nữ - Miền Bắc)"

    print("\n━━ Mode: TURBO (GGUF Q4 CPU) ━━")
    t0 = time.time()
    tts_turbo = Vieneu(mode="turbo", device="cpu")
    print(f"(init {time.time() - t0:.1f}s)")
    synth_sample(tts_turbo, short, voice, "ZZ_turbo_short")
    synth_sample(tts_turbo, medium, voice, "ZZ_turbo_medium")
    synth_sample(tts_turbo, long, voice, "ZZ_turbo_long")
    del tts_turbo

    import gc

    gc.collect()

    print("\n━━ Mode: STANDARD (PyTorch full precision) ━━")
    t0 = time.time()
    try:
        tts_std = Vieneu(mode="standard")
        print(f"(init {time.time() - t0:.1f}s)")
        synth_sample(tts_std, short, voice, "ZZ_standard_short")
        synth_sample(tts_std, medium, voice, "ZZ_standard_medium")
        synth_sample(tts_std, long, voice, "ZZ_standard_long")
    except Exception as e:
        print(f"  ✗ standard mode failed: {type(e).__name__}: {e}")

    print()
    print("━" * 70)
    print(f"Files in {OUT_DIR}:")
    for f in sorted(OUT_DIR.glob("ZZ_*.wav")):
        print(f"  {f.name}")

    print()
    print("So sánh turbo vs standard, cùng text → anh sẽ thấy rõ")
    print("standard có hay hơn hay không.")


if __name__ == "__main__":
    main()
