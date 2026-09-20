"""Generate a scene-by-scene narration script for a video via the OpenAI API.

`write_script(topics)` takes the selected Topic rows (plus their
prerequisite names for context) and returns a validated script:

    {
        "title": "...",
        "scenes": [{"title": ..., "narration": ...,
                     "on_screen_text": ["bullet", ...],
                     "duration_hint": seconds}, ...],
    }

`duration_hint` is advisory only — real scene timing comes from the TTS
audio length in the pipeline.

Follows the same strict-JSON-schema approach as `graph_builder.py`.

Usage:
    python -m core.services.script_writer <topic_id> [topic_id ...]
"""

from __future__ import annotations

import json
import sys
from typing import Optional

import openai

from .graph_builder import _env

_MAX_SCENES = 8
_MAX_TITLE = 120
_MAX_NARRATION = 1200
_MAX_BULLETS = 5
_MAX_BULLET_LEN = 90
_DEFAULT_MODEL = "gpt-4o-mini"

_SCHEMA = {
    "name": "video_script",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "short video title covering the selected topics",
            },
            "scenes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "narration": {
                            "type": "string",
                            "description": "spoken narration for this scene, "
                                           "1-3 conversational sentences",
                        },
                        "on_screen_text": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "short bullets shown on screen, "
                                           "max 10 words each",
                        },
                        "duration_hint": {
                            "type": "number",
                            "description": "estimated narration seconds",
                        },
                    },
                    "required": ["title", "narration", "on_screen_text", "duration_hint"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["title", "scenes"],
        "additionalProperties": False,
    },
}

_SYSTEM_PROMPT = """\
You write scripts for short educational videos that explain course topics
to a student reviewing their knowledge map.

You are given the selected topics (name, description, tags) plus their
prerequisite topics for context. Produce a single coherent video.

Rules:
- 3-6 scenes. If the source material is thin, use fewer scenes rather than
  padding. Never exceed 8 scenes.
- Keep the whole video under ~90 seconds of narration.
- Scene 1 introduces what the video covers; the last scene recaps the key
  takeaway. Middle scenes teach one idea each, in a sensible learning
  order (prerequisites first).
- narration: spoken aloud verbatim — conversational, no markdown, no
  headers, no "scene" labels, no visual directions.
- on_screen_text: 1-4 bullets per scene reinforcing (not repeating
  verbatim) the narration. Max 10 words per bullet.
- duration_hint: your estimate of how long the narration takes to speak.
- Teach at the depth the course descriptions imply; use standard subject
  knowledge to flesh out terse descriptions, but stay on-topic."""


# --------------------------------------------------------------------------
# Prompt construction / validation
# --------------------------------------------------------------------------

def _topics_text(topics, prerequisites_of) -> str:
    lines = ["SELECTED TOPICS (in curriculum order):"]
    for i, topic in enumerate(topics):
        lines.append(f"[{i}] {topic.name}")
        if topic.description:
            lines.append(f"    description: {topic.description}")
        tags = [tag.name for tag in topic.tags.all()]
        if tags:
            lines.append(f"    tags: {', '.join(tags)}")
        prereqs = prerequisites_of.get(topic.id) or []
        if prereqs:
            lines.append(f"    prerequisites: {', '.join(prereqs)}")
    return "\n".join(lines)


def _validate(payload: dict) -> dict:
    scenes = []
    for raw in payload.get("scenes") or []:
        narration = str(raw.get("narration") or "").strip()
        if not narration or len(scenes) >= _MAX_SCENES:
            continue
        bullets = [
            str(b).strip()[:_MAX_BULLET_LEN]
            for b in raw.get("on_screen_text") or []
            if str(b).strip()
        ][: _MAX_BULLETS]
        try:
            hint = float(raw.get("duration_hint") or 0)
        except (TypeError, ValueError):
            hint = 0
        scenes.append({
            "title": str(raw.get("title") or "").strip()[:_MAX_TITLE] or f"Scene {len(scenes) + 1}",
            "narration": narration[:_MAX_NARRATION],
            "on_screen_text": bullets,
            "duration_hint": max(0.0, hint),
        })
    if not scenes:
        raise ValueError("model returned no usable scenes")
    return {
        "title": str(payload.get("title") or "").strip()[:_MAX_TITLE] or topics_fallback_title(scenes),
        "scenes": scenes,
    }


def topics_fallback_title(scenes) -> str:
    return scenes[0]["title"] if scenes else "Video"


# --------------------------------------------------------------------------
# OpenAI call
# --------------------------------------------------------------------------

def _client() -> openai.OpenAI:
    key = _env("OPENAI_API_KEY")
    if not key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set — add it to .env or the environment.")
    return openai.OpenAI(api_key=key)


def _call(client, model: str, user: str, *, stricter: bool = False) -> dict:
    system = _SYSTEM_PROMPT
    if stricter:
        system += (
            "\n\nRespond with ONLY valid JSON matching the schema — no prose,"
            " no code fences."
        )
    resp = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_schema", "json_schema": _SCHEMA},
    )
    content = resp.choices[0].message.content or ""
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"model returned non-JSON output: {content[:200]!r}") from exc


def write_script(topics, prerequisites_of: Optional[dict] = None, *,
                 model: Optional[str] = None) -> dict:
    """Return a {"title", "scenes"} script for the selected Topic rows.

    ``prerequisites_of`` maps topic id -> list of prerequisite topic names.
    Malformed model output is retried once with a stricter prompt before
    raising.
    """
    client, mdl = _client(), model or _env("OPENAI_SCRIPT_MODEL", _DEFAULT_MODEL)
    user = _topics_text(topics, prerequisites_of or {})
    transient = (openai.RateLimitError, openai.APIConnectionError)
    for attempt in range(2):
        try:
            return _validate(_call(client, mdl, user, stricter=attempt > 0))
        except (RuntimeError, ValueError, *transient):
            if attempt == 1:
                raise
    raise RuntimeError("unreachable")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: python -m core.services.script_writer <topic_id> [...]")
    import django
    import os
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mysite.settings")
    django.setup()
    from core.models import Topic
    selected = list(Topic.objects.filter(pk__in=[int(a) for a in sys.argv[1:]]))
    sys.stdout.reconfigure(errors="replace")
    print(json.dumps(write_script(selected), indent=2, ensure_ascii=False))
