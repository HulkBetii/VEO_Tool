"""Gemini model fallback chain: 3 Flash Preview → 2.5 Flash → Gemma 4 31B."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from google import genai
from google.genai import types as genai_types


log = logging.getLogger("navtools.gemini_fallback")

MODEL_CHAIN: list[str] = [
    "gemini-3-flash-preview",
    "gemini-2.5-flash",
    "gemma-4-31b-it",
]

_NEEDS_SCHEMA_STRIP: set[str] = {"gemma-4-31b-it", "gemma-3-27b-it"}
_FALLBACK_TRIGGERS = (
    "RESOURCE_EXHAUSTED",
    "quota",
    "API key expired",
    "API_KEY_INVALID",
    "PERMISSION_DENIED",
    "NOT_FOUND",
)


def _should_advance_chain(err: Exception) -> bool:
    """True if `err` means we should try the NEXT model in the chain."""
    msg = str(err)
    return any(trigger in msg for trigger in _FALLBACK_TRIGGERS)


def _strip_schema_for_open_models(kwargs: dict) -> dict:
    """Drop config fields open-weights models on AI Studio don't accept."""
    cfg = kwargs.get("config")
    if cfg is None:
        return kwargs

    new_cfg = genai_types.GenerateContentConfig(
        response_mime_type=getattr(cfg, "response_mime_type", None),
        temperature=getattr(cfg, "temperature", None),
        max_output_tokens=getattr(cfg, "max_output_tokens", None),
    )
    return {**kwargs, "config": new_cfg}


def generate_with_fallback(client: genai.Client, **kwargs: Any) -> Any:
    """Sync: try each model in MODEL_CHAIN in order on quota/key errors."""
    if "model" in kwargs:
        log.warning(
            f"[gemini-fallback] caller passed model={kwargs['model']!r}; ignoring — helper owns model selection"
        )
        kwargs = {k: v for k, v in kwargs.items() if k != "model"}

    last_err = None
    for idx, model in enumerate(MODEL_CHAIN):
        call_kwargs = _strip_schema_for_open_models(kwargs) if model in _NEEDS_SCHEMA_STRIP else kwargs
        try:
            resp = client.models.generate_content(model=model, **call_kwargs)
            try:
                setattr(resp, "_model_used", model)
            except Exception:
                pass
            return resp
        except Exception as e:
            last_err = e
            stripped = False
            msg = str(e)
            if (
                model in _NEEDS_SCHEMA_STRIP
                and "response_schema" in msg.lower()
                and "config" in kwargs
            ):
                try:
                    stripped_kwargs = _strip_schema_for_open_models(kwargs)
                    log.warning(
                        f"[gemini-fallback] {model} rejected response_schema ({msg[:80]}) — retrying same model without schema"
                    )
                    resp = client.models.generate_content(model=model, **stripped_kwargs)
                    try:
                        setattr(resp, "_model_used", model)
                    except Exception:
                        pass
                    return resp
                except Exception as e2:
                    last_err = e2
                    stripped = True
                    e = e2

            is_last = idx == len(MODEL_CHAIN) - 1
            if is_last:
                log.error(f"[gemini-fallback] all {len(MODEL_CHAIN)} models exhausted, last error from {model}: {str(e)[:120]}")
                raise
            if not _should_advance_chain(e):
                raise

            next_model = MODEL_CHAIN[idx + 1]
            log.warning(
                f"[gemini-fallback] {model} unavailable ({type(e).__name__}: {str(e)[:120]}) — advancing to {next_model}"
            )
            _emit_fallback_metric(model, next_model, _classify_error(e))

    raise RuntimeError("MODEL_CHAIN is empty") from last_err


def _classify_error(err: Exception) -> str:
    """Map exception → short tag for metrics aggregation."""
    msg = str(err)
    for tag in ("RESOURCE_EXHAUSTED", "API_KEY_INVALID", "PERMISSION_DENIED", "NOT_FOUND", "API key expired"):
        if tag in msg:
            return tag.replace(" ", "_")
    if "quota" in msg.lower():
        return "QUOTA"
    return "UNKNOWN"


def _emit_fallback_metric(from_model: str, to_model: str, error_type: str) -> None:
    """Best-effort metric emit."""
    try:
        from services.metrics_logger import emit_gemini_fallback

        emit_gemini_fallback(from_model=from_model, to_model=to_model, error_type=error_type)
    except Exception:
        return None


async def agenerate_with_fallback(client_or_prompt: "genai.Client | str", api_key: str | None = None, **kwargs: Any) -> Any:
    """Async: try each model in MODEL_CHAIN.

    Supports two calling conventions:

    **New** (preferred)::

        client = genai.Client(api_key="...")
        resp = await agenerate_with_fallback(client, contents="...", config=...)
        text = resp.text

    **Legacy** (used by ``youtube_analyzer.py``)::

        text = await agenerate_with_fallback(prompt_str, api_key="KEY")
        # Returns a plain string so callers can do  str(raw).strip()
    """
    if isinstance(client_or_prompt, str):
        # ── Legacy path ──────────────────────────────────────────────────────
        # First arg is the prompt text; api_key is passed as a keyword arg.
        if not api_key:
            raise ValueError(
                "agenerate_with_fallback: api_key is required when the first "
                "argument is a prompt string, not a genai.Client instance."
            )
        _client = genai.Client(api_key=api_key)
        resp = await asyncio.to_thread(
            generate_with_fallback, _client, contents=client_or_prompt, **kwargs
        )
        # Legacy callers use  str(raw).strip()  or  json.loads(raw) — return text.
        return resp.text if hasattr(resp, "text") else str(resp)

    # ── New path ──────────────────────────────────────────────────────────────
    # First arg is already a genai.Client instance.
    return await asyncio.to_thread(generate_with_fallback, client_or_prompt, **kwargs)
