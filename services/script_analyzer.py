"""NAV TOOLS - Script/Idea -> Prompt analyzer."""

from __future__ import annotations

import json
import re
from typing import Callable, Optional

try:
    from services.gemini_with_fallback import agenerate_with_fallback
except Exception:
    async def agenerate_with_fallback(*args, **kwargs):
        raise RuntimeError("Gemini fallback service is unavailable")

from services.youtube_analyzer import VEO3_CAMERA_MOVES, VEO3_SHOT_TYPES, assemble_prompt, normalize_to_whitelist

try:
    from services.youtube_analyzer import VEO_CLIP_SECONDS
except Exception:
    try:
        from services.youtube_analyzer import VEO_VIDEO_LENGTH as VEO_CLIP_SECONDS
    except Exception:
        VEO_CLIP_SECONDS = 8


MAX_SCRIPT_SCENES = 40

_PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "global_context": {
            "type": "string",
            "description": "Short reusable context prefix (1-2 sentences, max 25 words) establishing era, setting, visual style, tone for ALL scenes.",
        },
        "scenes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "shot_type": {"type": "string"},
                    "camera_move": {"type": "string"},
                    "subject_desc": {
                        "type": "string",
                        "description": "What HAPPENS in the shot - characters, action, environment, lighting, mood. English. ~30-50 words.",
                    },
                    "vi_caption": {
                        "type": "string",
                        "description": "Short Vietnamese narration line for this scene (used for voiceover, max 25 words).",
                    },
                    "characters_in_scene": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Aliases that ACTUALLY appear in this specific shot.",
                    },
                },
                "required": ["shot_type", "camera_move", "subject_desc", "vi_caption", "characters_in_scene"],
            },
        },
    },
    "required": ["global_context", "scenes"],
}


def _build_planner_prompt(
    script_text,
    num_scenes,
    style_preset_desc,
    style_lock,
    global_context,
    character_aliases,
    voice_gender,
    auto_detect_scenes=False,
):
    """Single mega-prompt that asks Gemini to plan the whole shot list."""
    aliases_clause = ""
    if character_aliases:
        aliases_list = ", ".join("@" + alias.lstrip("@") for alias in character_aliases)
        aliases_clause = (
            f"\n\nCHARACTER ALIASES the user uploaded as reference images: {aliases_list}"
            "\n\nSTRICT character usage rules (CRITICAL - read carefully):"
            "\n  - Each alias represents a SPECIFIC character with reference image."
            "\n  - In `subject_desc`: use the alias token verbatim ONLY when that character is ACTUALLY ON SCREEN."
            "\n  - In `characters_in_scene`: list ONLY aliases visible in this shot."
            "\n  - DO NOT invent appearances."
        )

    voice_clause = ""
    if voice_gender in ("male", "female"):
        voice_clause = f"\n\nVoiceover gender: {voice_gender}. Keep vi_caption phrasing natural for a {voice_gender} narrator."

    ctx_clause = ""
    if global_context:
        ctx_clause = (
            '\n\nGlobal context the user already wrote - REUSE it verbatim in your `global_context` output:\n"'
            + global_context.strip()
            + '"'
        )

    if auto_detect_scenes:
        scene_count_rule = "1. Choose the OPTIMAL number of scenes (between 3 and 20) based on the natural beat structure of the script."
        opening = (
            f"You are a video director planning a Veo 3.1 video. First decide how many shots the script needs (3-20), "
            f"then plan the beat structure. Each shot renders as an independent ~{VEO_CLIP_SECONDS}-second clip concatenated in order."
        )
    else:
        scene_count_rule = f"1. Output EXACTLY {num_scenes} scenes - no more, no less."
        opening = (
            f"You are a video director planning a {num_scenes}-shot sequence for Google Veo 3.1. "
            f"Each shot renders as an independent ~{VEO_CLIP_SECONDS}-second clip concatenated in order."
        )

    return (
        opening
        + f'\n\nUSER SCRIPT / IDEA:\n"""{script_text.strip()}"""'
        + "\n\nVISUAL STYLE the user picked (you do NOT echo this in subject_desc - it goes into the Style: clause downstream):\n"
        + (style_preset_desc or "")
        + ("\n\n" + style_lock.strip() if style_lock else "")
        + aliases_clause
        + voice_clause
        + ctx_clause
        + "\n\nRules:\n"
        + scene_count_rule
        + "\n2. `shot_type` MUST come from this list:\n   "
        + ", ".join(VEO3_SHOT_TYPES)
        + "\n3. `camera_move` MUST come from this list:\n   "
        + ", ".join(VEO3_CAMERA_MOVES)
        + "\n4. `subject_desc` is ENGLISH, 30-50 words, present tense."
        + "\n5. `vi_caption` is the Vietnamese narration line under 25 words."
        + "\n6. `characters_in_scene` lists aliases visible in this exact shot."
        + "\n7. `global_context` is a SHORT reusable prefix."
        + "\n\nOutput ONLY the JSON object. No preamble, no markdown fence."
    )


def _strip_planning_rules_for_veo(text: str) -> str:
    text = re.sub(r"\b(?:shot_type|camera_move|characters_in_scene)\b\s*[:=].*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(?:Output|Rules?|JSON|schema)\b.*", "", text, flags=re.IGNORECASE)
    return text.strip()


def _strip_json_fence(text: str) -> str:
    s = (text or "").strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s
        if "```" in s:
            s = s.rsplit("```", 1)[0]
    if not s.startswith("{"):
        a, b = s.find("{"), s.rfind("}")
        if a >= 0 and b > a:
            s = s[a : b + 1]
    return s.strip()


def _load_genai():
    try:
        from google import genai
        from google.genai import types as genai_types
    except Exception as exc:
        raise RuntimeError("Google GenAI SDK is unavailable") from exc
    return genai, genai_types


class ScriptAnalyzer:
    def __init__(self):
        self._cancel_requested = False

    def cleanup(self):
        pass

    def request_cancel(self):
        self._cancel_requested = True

    def cancel(self):
        self.request_cancel()

    async def analyze(
        self,
        script_text: str,
        num_scenes: int,
        gemini_api_key: str,
        style_preset_desc: str = "",
        style_lock: str = "",
        global_context: str = "",
        character_aliases: Optional[list[str]] = None,
        voice_gender: str = "",
        narration_lang: str = "vi",
        auto_detect_scenes: bool = False,
        progress_cb: Optional[Callable] = None,
    ):
        """Plan a script into N Veo-ready scenes in a single Gemini call."""
        if not script_text.strip():
            raise ValueError("Kịch bản trống.")
        n = max(1, min(int(num_scenes or 1), MAX_SCRIPT_SCENES))
        aliases = ["@" + alias.lstrip("@") for alias in (character_aliases or [])]
        if progress_cb:
            progress_cb(0, 1, "User script")

        genai, genai_types = _load_genai()
        client = genai.Client(api_key=gemini_api_key)
        prompt = _build_planner_prompt(
            script_text,
            None if auto_detect_scenes else n,
            style_preset_desc,
            style_lock,
            global_context,
            aliases,
            voice_gender,
            auto_detect_scenes,
        )
        warnings = []
        response = await agenerate_with_fallback(
            client,
            contents=[prompt],
            config=genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_PLAN_SCHEMA,
            ),
        )
        raw_text = response.text or ""
        cleaned = _strip_json_fence(raw_text)
        data = json.loads(cleaned)
        ai_global_context = data.get("global_context", "")
        effective_context = global_context.strip() or ai_global_context
        ai_scenes = data.get("scenes", [])

        out_scenes = []
        for idx, raw in enumerate(ai_scenes, 1):
            shot_type = normalize_to_whitelist(raw.get("shot_type", ""), VEO3_SHOT_TYPES)
            camera_move = normalize_to_whitelist(raw.get("camera_move", ""), VEO3_CAMERA_MOVES)
            subject_desc = _strip_planning_rules_for_veo(raw.get("subject_desc", ""))
            vi_caption = raw.get("vi_caption", "") or raw.get("narration", "")
            allowed_aliases = set(aliases)
            scene_aliases = []
            for alias in raw.get("characters_in_scene", []) or []:
                clean = "@" + str(alias).lstrip("@")
                if clean in allowed_aliases:
                    scene_aliases.append(clean)
            final_prompt = assemble_prompt(
                global_context=effective_context,
                subject_desc=subject_desc,
                style_desc=style_preset_desc,
                shot_type=shot_type,
                camera_move=camera_move,
                character_aliases=scene_aliases,
            )
            out_scenes.append(
                {
                    "scene_num": idx,
                    "shot_type": shot_type,
                    "camera_move": camera_move,
                    "prompt": final_prompt,
                    "transcripts": vi_caption,
                    "narration": vi_caption,
                    "duration": VEO_CLIP_SECONDS,
                    "characters_in_scene": scene_aliases,
                    "subject_desc": subject_desc,
                }
            )

        return {
            "scenes": out_scenes,
            "warnings": warnings,
            "raw_scenes": [],
            "transcripts": {},
            "generated_global_context": ai_global_context,
            "title": "User script",
            "duration": len(out_scenes) * VEO_CLIP_SECONDS,
        }

    async def analyze_script(
        self,
        script_text: str,
        num_scenes: int,
        gemini_api_key: str,
        style_preset_desc: str = "",
        style_lock: str = "",
        global_context: str = "",
        character_aliases: Optional[list[str]] = None,
        voice_gender: str = "",
        narration_lang: str = "vi",
        auto_detect_scenes: bool = False,
        progress_cb: Optional[Callable] = None,
    ):
        return await self.analyze(
            script_text=script_text,
            num_scenes=num_scenes,
            gemini_api_key=gemini_api_key,
            style_preset_desc=style_preset_desc,
            style_lock=style_lock,
            global_context=global_context,
            character_aliases=character_aliases,
            voice_gender=voice_gender,
            narration_lang=narration_lang,
            auto_detect_scenes=auto_detect_scenes,
            progress_cb=progress_cb,
        )

    async def regenerate_scene(
        self,
        script_text: str,
        scene_idx: int,
        existing_scenes: list[dict],
        gemini_api_key: str,
        style_preset_desc: str = "",
        style_lock: str = "",
        global_context: str = "",
        character_aliases: Optional[list[str]] = None,
        voice_gender: str = "",
        narration_lang: str = "vi",
    ):
        """Re-analyze only one scene via Gemini."""
        aliases = ["@" + alias.lstrip("@") for alias in (character_aliases or [])]
        genai, genai_types = _load_genai()
        client = genai.Client(api_key=gemini_api_key)
        existing_summary_lines = []
        for i, scene in enumerate(existing_scenes, 1):
            tag = " <- regenerate this" if i == scene_idx else ""
            shot = scene.get("shot_type", "")
            cam = scene.get("camera_move", "")
            subj = scene.get("subject_desc") or scene.get("prompt", "")
            existing_summary_lines.append(f"{i}. {shot}/{cam}: {subj}{tag}")
        existing_summary = "\n".join(existing_summary_lines)
        prompt = (
            "Regenerate exactly ONE scene for a Veo 3.1 storyboard.\n"
            f"Scene index: {scene_idx}\nExisting scenes:\n{existing_summary}\n\n"
            f"Original script:\n{script_text}\n\n"
            "Return JSON object with shot_type, camera_move, subject_desc, vi_caption, characters_in_scene."
        )
        response = await agenerate_with_fallback(
            client,
            contents=[prompt],
            config=genai_types.GenerateContentConfig(response_mime_type="application/json"),
        )
        raw = response.text or ""
        data = json.loads(_strip_json_fence(raw))
        shot_type = normalize_to_whitelist(data.get("shot_type", ""), VEO3_SHOT_TYPES)
        camera_move = normalize_to_whitelist(data.get("camera_move", ""), VEO3_CAMERA_MOVES)
        subject_desc = _strip_planning_rules_for_veo(data.get("subject_desc", ""))
        vi_caption = data.get("vi_caption", "")
        allowed_aliases = set(aliases)
        scene_aliases = []
        for alias in data.get("characters_in_scene", []) or []:
            clean = "@" + str(alias).lstrip("@")
            if clean in allowed_aliases:
                scene_aliases.append(clean)
        final_prompt = assemble_prompt(
            global_context=global_context,
            subject_desc=subject_desc,
            style_desc=style_preset_desc,
            shot_type=shot_type,
            camera_move=camera_move,
            character_aliases=scene_aliases,
        )
        return {
            "scene_num": scene_idx,
            "shot_type": shot_type,
            "camera_move": camera_move,
            "prompt": final_prompt,
            "transcripts": vi_caption,
            "narration": vi_caption,
            "duration": VEO_CLIP_SECONDS,
            "characters_in_scene": scene_aliases,
            "subject_desc": subject_desc,
        }
