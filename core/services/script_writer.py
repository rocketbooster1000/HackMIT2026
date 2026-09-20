"""Generate a scene-by-scene narration script for a video via the OpenAI API.

`write_script(topics)` takes the selected Topic rows (plus their
prerequisite names for context) and returns a validated script:

    {
        "title": "...",
        "scenes": [{"title": ..., "narration": ...,
                     "on_screen_text": ["bullet", ...],
                     "markup": "self-contained HTML/SVG for the scene",
                     "assumption": "..." | null,
                     "duration_hint": seconds}, ...],
    }

`duration_hint` is advisory only — real scene timing comes from the TTS
audio length in the pipeline. `markup` is rendered verbatim in the
Remotion composition: the model invents each scene's visual itself.

Follows the same strict-JSON-schema approach as `graph_builder.py`.

Usage:
    python -m core.services.script_writer <topic_id> [topic_id ...]
"""

from __future__ import annotations

import json
import re
import sys
from typing import Optional

import openai

from .graph_builder import _env

_MAX_SCENES = 8
_MAX_TITLE = 120
_MAX_NARRATION = 1200
_MAX_BULLETS = 5
_MAX_BULLET_LEN = 90
_MAX_MARKUP = 12000
_MAX_ASSUMPTION = 200
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
                        "markup": {
                            "type": "string",
                            "description": "self-contained HTML or inline SVG "
                                           "filling the entire 1920x1080 "
                                           "frame; the model owns all "
                                           "on-screen content. No external "
                                           "resources, no <script>",
                        },
                        "assumption": {
                            "type": ["string", "null"],
                            "description": "one short sentence flagging a "
                                           "simplification or uncertain claim, "
                                           "else null",
                        },
                        "duration_hint": {
                            "type": "number",
                            "description": "estimated narration seconds",
                        },
                    },
                    "required": ["title", "narration", "on_screen_text",
                                 "markup", "assumption", "duration_hint"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["title", "scenes"],
        "additionalProperties": False,
    },
}

_SYSTEM_PROMPT = """\
You are a script generator for an automated educational video pipeline.
You write scripts for short educational videos that explain course
topics to a student reviewing their knowledge map.

You are given the selected topics (name, description, tags) plus their
prerequisite topics for context. Produce a single coherent video.

Scene rules:
- 3-6 scenes, never more than 8. If the source material is thin, use
  fewer scenes rather than padding. Keep total narration under ~90
  seconds.
- Order scenes so ideas build sensibly (prerequisites first): introduce
  the concept, explain the mechanism, close with significance. Scene 1
  states what the video covers; the last scene recaps the key takeaway.
- If two selected topics overlap in scope, merge the shared material
  into one scene — never repeat content.

Per scene:
- title: short scene heading.
- narration: 1-3 sentences spoken aloud verbatim by TTS. One idea per
  sentence, conversational, no markdown, no headers, no scene labels,
  no visual directions.
- markup: self-contained HTML or inline SVG that fills the ENTIRE
  1920x1080 frame — you own the whole canvas. Nothing is drawn for you:
  include the scene's heading, labels, diagrams, equations, callouts,
  whatever the idea needs, positioned and styled however you want.
  You may embed <style> blocks — CSS animations and transitions do play
  during rendering, so animate entrances, highlights, flows. Hard
  rules: self-contained only — no external images, fonts, scripts,
  iframes, or links; no <script> or on* event handlers; no markdown.
  Design light-on-dark (background #16161a, text #f5f1ea, muted
  #8a8378, accent hues of your choice), font sizes >= 28px,
  system-ui / sans-serif. Prefer inline SVG with a viewBox and
  width/height of 100%, or absolutely-positioned divs on a full-size
  root element, so your layout fills the frame at any render size.
- on_screen_text: 1-4 bullets reinforcing (not repeating verbatim) the
  narration, max 10 words each. These are a fallback — they render only
  if markup is empty — so still write them, but design markup to carry
  the scene on its own.
- assumption: one short sentence flagging any simplification or
  uncertain claim; null when nothing needs flagging.
- duration_hint: estimated narration seconds, based on ~150 words/min
  plus one beat per visual transition.

When a topic builds on a listed prerequisite topic, the narration may
reference it by name for continuity (e.g. "as shown in
Transcription...").

Teach at the depth the course descriptions imply; use standard subject
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


def _markup(raw) -> str:
    """Return the scene's HTML/SVG, stripped of scripts and handlers."""
    markup = str(raw or "").strip()[:_MAX_MARKUP]
    markup = re.sub(r"<script[^>]*>.*?</script\s*>", "", markup,
                    flags=re.IGNORECASE | re.DOTALL)
    markup = re.sub(r"<script[^>]*/?>", "", markup, flags=re.IGNORECASE)
    markup = re.sub(r"\son[a-z]+\s*=", " data-removed=", markup,
                    flags=re.IGNORECASE)
    return markup


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
        assumption = str(raw.get("assumption") or "").strip()[:_MAX_ASSUMPTION]
        try:
            hint = float(raw.get("duration_hint") or 0)
        except (TypeError, ValueError):
            hint = 0
        scenes.append({
            "title": str(raw.get("title") or "").strip()[:_MAX_TITLE] or f"Scene {len(scenes) + 1}",
            "narration": narration[:_MAX_NARRATION],
            "on_screen_text": bullets,
            "markup": _markup(raw.get("markup")),
            "assumption": assumption or None,
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
