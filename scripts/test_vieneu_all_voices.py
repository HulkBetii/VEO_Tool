"""Generate 1 sample per preset voice for A/B comparison."""

from __future__ import annotations

import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "scripts" / "tts_samples"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8")

    print("━" * 70)
    print("🎤 VieNeu-TTS — All Voices Comparison")
    print("━" * 70)

    from vieneu import Vieneu

    tts = Vieneu(mode="turbo", device="cpu")
    voices = tts.list_preset_voices()

    sample_text = (
        "Năm 550 trước Công nguyên, Cyrus Đại Đế sáng lập đế chế Ba Tư. "
        "Đây là đế chế hùng mạnh nhất thế giới cổ đại."
    )
    print(f"\nSample text: {sample_text}")
    print()

    for voice_tuple in voices:
        if isinstance(voice_tuple, (list, tuple)):
            voice_id = voice_tuple[0]
        else:
            voice_id = voice_tuple

        safe_name = (
            voice_id.replace(" ", "_")
            .replace("(", "")
            .replace(")", "")
            .replace("-", "_")
            .replace(",", "")
        )
        out_path = OUT_DIR / f"voice_{safe_name}.wav"

        print(f"🎤 {voice_id}")
        t0 = time.time()
        try:
            audio = tts.infer(text=sample_text, voice=voice_id)
            tts.save(audio, str(out_path))
            elapsed = time.time() - t0
            size_kb = out_path.stat().st_size // 1024
            print(f"   ✓ {out_path.name} ({size_kb}KB, {elapsed:.1f}s)")
        except Exception as e:
            print(f"   ✗ Failed: {e}")
        print()

    print("━" * 70)
    print(f"All samples saved in: {OUT_DIR}")
    print()
    print("Anh mở lần lượt từng file để so sánh, chọn giọng hay nhất:")
    for v in voices:
        if isinstance(v, (list, tuple)):
            vid = v[0]
        else:
            vid = v

        safe = vid.replace(" ", "_").replace("(", "").replace(")", "").replace("-", "_").replace(",", "")
        print(f"  {OUT_DIR / ('voice_' + safe + '.wav')}")


if __name__ == "__main__":
    main()
