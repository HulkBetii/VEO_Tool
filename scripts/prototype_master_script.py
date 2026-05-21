"""Prototype: 2-Pass Story Planner — Pass 1 (Master Script Generator).

Standalone script to validate the story-first approach BEFORE touching
production code. Takes a cached transcript from a previous YouTube
analyze run and asks Gemini to generate a coherent master narration
script split into N beats.

Goal: Prove that feeding the full transcript to a story planner
produces narration with plot arc + continuity, vs the current
per-scene fragmented approach.

Usage:
    python scripts/prototype_master_script.py
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TRANSCRIPT_PATH = ROOT / ".vidgen" / "youtube_cache" / "1ca2aacbc016f8b6" / "transcript.json"
TARGET_BEAT_COUNT = 7

MASTER_SCRIPT_PROMPT = """You are a professional documentary scriptwriter.

You will be given the FULL transcript of a short documentary video,
along with its total duration and the number of beats (scenes) we
need to produce. Your task is to REWRITE the transcript into a
coherent master narration broken into exactly N beats.

Each beat will be voiced over an 8-second video clip. The beats
together must form ONE continuous story with clear plot arc:
intro → development → climax → resolution.

CRITICAL RULES:
1. CONTINUITY — Each beat must flow from the previous one. Do NOT
   re-introduce the same entity twice. If Beat 1 says "Trajan the
   emperor", Beat 2 should just say "he" or "the emperor", not
   "Trajan the emperor" again.
2. PLOT ARC — Open with a hook or establishing fact, build the
   narrative, deliver the payoff at the end. Don't make every beat
   a generic fact.
3. LENGTH — Each beat narration max 18 words (~ 7 seconds at natural
   Vietnamese or English speaking pace).
4. NO FILLER — Skip "Hôm nay chúng ta sẽ tìm hiểu...", "Chào mừng
   bạn đến với video này...". Start the story immediately.
5. LANGUAGE — Output in the SAME LANGUAGE as the transcript.
6. NAMES — Preserve real historical names (Trajan, Diocletian, etc.)
   This is narration, not visual — Veo safety filter only scans
   visual description.
7. VISUAL INTENT — For each beat, tell me what KIND of visual would
   work best: MAP_OVERVIEW / CHARACTER / LANDMARK / DOCUMENT /
   OBJECT / ATMOSPHERE. Vary across beats for visual rhythm.

You MUST output ONLY valid JSON matching this schema:
{
  "overall_story": "<2-3 sentence summary of the full narrative arc>",
  "language": "<en or vi>",
  "beats": [
    {
      "beat_id": 1,
      "start_time": <float seconds>,
      "end_time": <float seconds>,
      "narration": "<≤18 word sentence, continues from beat before>",
      "visual_intent": "<MAP_OVERVIEW|CHARACTER|LANDMARK|DOCUMENT|OBJECT|ATMOSPHERE>",
      "key_entities": ["<name1>", "<name2>"]
    }
  ]
}

========================================================================
INPUT

Video total duration: <<TOTAL_DURATION>> seconds
Number of beats needed: <<BEAT_COUNT>>

Full transcript with timestamps:
<<FULL_TRANSCRIPT>>

========================================================================
OUTPUT (JSON only, no markdown, no preamble):"""


def load_transcript(path: Path) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def format_transcript_for_prompt(segments: list[dict]) -> str:
    """Build a timestamped transcript block for the prompt."""
    lines = []
    for s in segments:
        start = s.get("start", 0)
        end = s.get("end", start)
        text = (s.get("text") or "").strip()
        if not text:
            continue
        lines.append(f"[{start:5.1f}s-{end:5.1f}s] {text}")
    return "\n".join(lines)


def get_gemini_api_key() -> str:
    """Read Gemini API key from the project's SQLite settings."""
    db_path = ROOT / ".vidgen" / "vidgen.db"
    if not db_path.exists():
        raise RuntimeError(f"DB not found: {db_path}")

    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute("SELECT value FROM settings WHERE key=?", ("gemini_api_key",)).fetchone()
        if not row:
            raise RuntimeError("gemini_api_key not in settings table")

        val = row[0]
        if isinstance(val, str) and val.startswith('"'):
            val = json.loads(val)
        return val
    finally:
        conn.close()


async def generate_master_script(
    transcript_segments: list[dict],
    beat_count: int,
    api_key: str,
) -> dict:
    from google import genai

    total_dur = max((s.get("end", 0) for s in transcript_segments), default=0)
    prompt = (
        MASTER_SCRIPT_PROMPT.replace("<<TOTAL_DURATION>>", f"{total_dur:.1f}")
        .replace("<<BEAT_COUNT>>", str(beat_count))
        .replace("<<FULL_TRANSCRIPT>>", format_transcript_for_prompt(transcript_segments))
    )

    print("\n" + "=" * 80)
    print("SENDING TO GEMINI")
    print("=" * 80)
    print(f"Total duration: {total_dur:.1f}s")
    print(f"Beat count: {beat_count}")
    print(f"Transcript segments: {len(transcript_segments)}")
    print(f"Prompt size: {len(prompt):,} chars")

    client = genai.Client(api_key=api_key)
    from services.gemini_with_fallback import agenerate_with_fallback

    response = await agenerate_with_fallback(client, contents=[prompt])
    raw_text = (response.text or "").strip()

    cleaned = raw_text
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
        cleaned = cleaned.rsplit("```", 1)[0].strip()

    if not cleaned.startswith("{"):
        first = cleaned.find("{")
        last = cleaned.rfind("}")
        if first >= 0 and last > first:
            cleaned = cleaned[first : last + 1]

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        print("❌ JSON decode failed")
        print("Raw first 500 chars:", repr(raw_text[:500]))
        print("Cleaned first 500 chars:", repr(cleaned[:500]))
        raise


async def main():
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    print("\n" + "=" * 80)
    print("PROTOTYPE MASTER SCRIPT GENERATOR")
    print("=" * 80)

    if not TRANSCRIPT_PATH.exists():
        print(f"❌ Transcript not found: {TRANSCRIPT_PATH}")
        return

    segments = load_transcript(TRANSCRIPT_PATH)
    print(f"Loaded {len(segments)} transcript segments from:")
    print(f"  {TRANSCRIPT_PATH}")

    print("\n" + "=" * 80)
    print("ORIGINAL TRANSCRIPT")
    print("=" * 80)
    print(format_transcript_for_prompt(segments))

    try:
        api_key = get_gemini_api_key()
    except Exception as e:
        print(f"❌ {e}")
        return

    try:
        data = await generate_master_script(
            transcript_segments=segments,
            beat_count=TARGET_BEAT_COUNT,
            api_key=api_key,
        )
    except Exception as e:
        print(f"❌ Gemini call failed: {e}")
        return

    print("\n" + "=" * 80)
    print("MASTER SCRIPT RESULT")
    print("=" * 80)
    print(f"\nOverall story:\n{data.get('overall_story', '(missing)')}")
    print(f"\nLanguage: {data.get('language', '?')}")
    print("\nBeats:")

    for b in data.get("beats", []):
        word_count = len((b.get("narration") or "").split())
        print(
            f"  Beat {b.get('beat_id', '?'):>2}: "
            f"{b.get('start_time', 0):>5.1f}s - {b.get('end_time', 0):>5.1f}s | "
            f"{b.get('visual_intent', '?'):<13} | {word_count:>2} words"
        )
        print(f"    → {b.get('narration', '')}")
        entities = b.get("key_entities", [])
        if entities:
            print(f"    📌 Entities: {', '.join(entities)}")
        print()

    out_path = ROOT / "scripts" / "prototype_master_script_output.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"💾 Saved to: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
