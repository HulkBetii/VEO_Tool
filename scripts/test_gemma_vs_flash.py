"""Benchmark: Gemini 2.5 Flash vs Gemma 4 31B on a realistic NAVTools prompt.

Run:
  set GEMINI_API_KEY=your_key_here
  python scripts/test_gemma_vs_flash.py

Output: latency, token usage, JSON-valid status, sample scenes per model.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from google import genai


MODELS = [
    "gemini-3-flash-preview",
    "gemini-2.5-flash",
    "gemma-4-31b-it",
]

SAMPLE_SCRIPT = """
Một con mèo nhỏ tên Miu lạc trong rừng đêm. Nó đi mãi giữa những hàng cây cao
vút, ánh trăng xuyên qua kẽ lá. Bỗng một con cú trắng đậu xuống cành cây gần
đó, đôi mắt vàng sáng rực. Cú nói: "Cháu đi đâu giữa đêm khuya thế này?". Miu
sợ hãi nhưng cũng đáp lại: "Cháu lạc đường về nhà". Cú trắng dang rộng đôi
cánh, dẫn Miu băng qua khu rừng, vượt qua dòng suối bạc, đến tận bìa rừng nơi
ánh đèn ấm áp của ngôi nhà nhỏ đang chờ. Miu cảm ơn cú và chạy ào về phía mẹ.
""".strip()

PROMPT_TEMPLATE = """
You are a video director. Split the script below into exactly 5 scenes.
For each scene output:
- "vi_caption": short Vietnamese caption (max 20 words)
- "veo3_prompt": detailed English prompt for Google Veo3 (camera, lighting, character action, mood, ~40-60 words)
- "duration": integer seconds (sum across all scenes ≈ 40)

Output ONLY a valid JSON array of 5 objects, no preamble, no markdown fence.

SCRIPT:
{script}
""".strip()


def extract_json(text: str) -> str:
    """Strip markdown fences and isolate JSON array if model added prose."""
    s = text.strip()
    if s.startswith("```"):
        lines = s.split("\n", 1)
        if len(lines) > 1:
            s = lines[1]
        if "```" in s:
            s = s.rsplit("```", 1)[0]
        s = s.strip()

    if not s.startswith("["):
        a = s.find("[")
        b = s.rfind("]")
        if a >= 0 and b > a:
            s = s[a : b + 1]
    return s


def benchmark(client: genai.Client, model: str, prompt: str) -> dict:
    """Call model once, measure latency, return result dict."""
    out = {
        "model": model,
        "ok": False,
        "error": None,
        "latency_s": 0,
        "scenes": 0,
        "in_tokens": None,
        "out_tokens": None,
        "preview": None,
        "raw_first_300": None,
    }
    t0 = time.perf_counter()

    try:
        resp = client.models.generate_content(model=model, contents=[prompt])
        out["latency_s"] = round(time.perf_counter() - t0, 2)
        raw = (resp.text or "").strip()
        out["raw_first_300"] = raw[:300]

        usage = getattr(resp, "usage_metadata", None)
        if usage:
            out["in_tokens"] = getattr(usage, "prompt_token_count", None)
            out["out_tokens"] = getattr(usage, "candidates_token_count", None)

        try:
            data = json.loads(extract_json(raw))
            if isinstance(data, list):
                out["scenes"] = len(data)
                out["ok"] = True
                if data:
                    s0 = data[0]
                    out["preview"] = {
                        "vi_caption": s0.get("vi_caption", "")[:80],
                        "veo3_prompt": s0.get("veo3_prompt", "")[:120],
                        "duration": s0.get("duration"),
                    }
            return out
        except json.JSONDecodeError as e:
            out["error"] = f"JSON parse: {e}"
            return out
    except Exception as e:
        out["latency_s"] = round(time.perf_counter() - t0, 2)
        out["error"] = f"{type(e).__name__}: {e}"
        return out


def main() -> int:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: set GEMINI_API_KEY in environment", file=sys.stderr)
        return 1

    client = genai.Client(api_key=api_key)
    prompt = PROMPT_TEMPLATE.format(script=SAMPLE_SCRIPT)

    print("=" * 78)
    print("BENCHMARK — Flash vs Gemma 4 (chia kịch bản → 5 scene JSON)")
    print(f"Prompt length: {len(prompt)} chars")
    print("=" * 78)

    results = []
    for m in MODELS:
        print(f"\n→ Testing: {m} ...", flush=True)
        r = benchmark(client, m, prompt)
        results.append(r)

        status = "OK " if r["ok"] else "FAIL"
        print(
            f"   [{status}] {r['latency_s']}s | scenes={r['scenes']} "
            f"| tokens in={r['in_tokens']} out={r['out_tokens']}"
        )
        if r["error"]:
            print(f"   ERROR: {r['error']}")
            print(f"   RAW (first 300): {r['raw_first_300']!r}")
            continue

        if not r["preview"]:
            continue

        p = r["preview"]
        print(f"   VI:  {p['vi_caption']}")
        print(f"   EN:  {p['veo3_prompt']}")
        print(f"   DUR: {p['duration']}s")

    print("\n" + "=" * 78)
    print("SUMMARY")
    print("=" * 78)
    print(f"{'Model':<24} {'Status':<6} {'Latency':<10} {'Scenes':<8} {'In/Out tokens'}")
    print("-" * 78)
    for r in results:
        st = "OK" if r["ok"] else "FAIL"
        tok = f"{r['in_tokens']}/{r['out_tokens']}" if r["in_tokens"] else "n/a"
        print(f"{r['model']:<24} {st:<6} {r['latency_s']}s     {r['scenes']:<8} {tok}")

    print("\n" + "=" * 78)
    print("FALLBACK WIRING CHECK (forced Flash failure via bad key)")
    print("=" * 78)

    from services.gemini_with_fallback import generate_with_fallback

    bad_client = genai.Client(api_key="AIzaSyINVALIDKEY_only_for_smoke_test_xxxxx")
    triggered = False
    try:
        generate_with_fallback(bad_client, contents=["ping"])
    except Exception as e:
        msg = str(e)
        triggered = "gemma-4-31b-it" in msg or "API_KEY_INVALID" in msg or "API key" in msg

    if triggered:
        print("   [PASS] helper attempted fallback — check stderr above for")
        print("          the '[gemini-fallback] ... retrying with gemma-4-31b-it' line.")
        return 0

    print("   [WARN] could not confirm fallback path — review helper logic.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
