"""Build a directed topic graph from parsed syllabus text via the OpenAI API.

`build_graph(text)` sends the parser's output to a chat model constrained
by a JSON schema, then validates and normalizes the result:

    {
        "course": "HIST 103-1 ..." | None,
        "nodes":  [{"id": "t1", "title": ..., "date": "YYYY-MM-DD"|None,
                    "order": 1, "summary": ...}, ...],
        "edges":  [{"source": "t1", "target": "t2",
                    "type": "prerequisite"}, ...],
    }

All edges are prerequisite relationships inferred by the model: source
must be understood before target. Node `date`/`order` fields describe
when a topic is taught but never drive edge creation.

Usage:
    python -m core.services.graph_builder path/to/syllabus.pdf
    python -m core.services.graph_builder path/to/parsed.txt
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

import openai

_MAX_NODES = 150
_MAX_TITLE = 120
_MAX_SUMMARY = 200
_DEFAULT_MODEL = "gpt-4o-mini"

# Strict structured-outputs schema — the model must fill every field.
_SCHEMA = {
    "name": "course_graph",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "course": {
                "type": ["string", "null"],
                "description": "course code/name if identifiable, else null",
            },
            "topics": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "date": {"type": ["string", "null"]},
                        "order": {"type": "integer"},
                        "summary": {"type": "string"},
                    },
                    "required": ["title", "date", "order", "summary"],
                    "additionalProperties": False,
                },
            },
            "prerequisites": {
                "type": "array",
                "description": "pairs of indices into topics[]",
                "items": {
                    "type": "object",
                    "properties": {
                        "source": {"type": "integer"},
                        "target": {"type": "integer"},
                    },
                    "required": ["source", "target"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["course", "topics", "prerequisites"],
        "additionalProperties": False,
    },
}

_SYSTEM_PROMPT = """\
You convert course syllabi and study materials into a directed knowledge
graph of curriculum topics.

Rules:
- One node per distinct curriculum topic, in the order the course covers
  them. Merge duplicate mentions; split entries that cover several clearly
  distinct topics.
- Skip non-instructional content: holidays, "no class" days, admin notes,
  grading/policy sections, contact info.
- Assessments (exams, quizzes, project deadlines) count as topics when they
  mark curriculum milestones.
- title: short (10 words max) and specific.
- summary: one sentence on what the topic covers (200 chars max).
- date: the session's ISO date (YYYY-MM-DD) if one appears in the text —
  the material annotates dates as [YYYY-MM-DD] — otherwise null.
- order: 1-based position in the curriculum. Metadata only — it does
  not create edges.
- prerequisites: pairs of topic indices (source -> target). Add edge
  A -> B only if a student who skipped A could not properly understand
  B — a true conceptual dependency, NOT chronological order. There are
  no sequence edges: do not connect topics merely because they are
  adjacent in the schedule. When judging dependencies you may use
  standard curriculum knowledge of the subject.
- Nodes must come ONLY from the text — do not add topics the material
  does not cover, and keep titles and summaries at the depth the course
  actually teaches."""

# Pass 2: per-node dependency enumeration. Forward-only indices keep the
# graph acyclic.
_DEPS_SCHEMA = {
    "name": "topic_dependencies",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "dependencies": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "topic": {"type": "integer"},
                        "requires": {
                            "type": "array",
                            "items": {"type": "integer"},
                        },
                    },
                    "required": ["topic", "requires"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["dependencies"],
        "additionalProperties": False,
    },
}

_DEPS_PROMPT = """\
You are given the topic list of a course, in curriculum order. For each
topic, list the indices of the EARLIER topics it depends on.

Rules:
- requires[] may only contain indices lower than the topic's own index
  (a prerequisite must be taught before the topic).
- Add a dependency only if a student who skipped the source could not
  properly understand the target — a real conceptual prerequisite, not
  schedule adjacency.
- Use standard curriculum knowledge of the subject.
- Most topics need few or no prerequisites. Omit topics with none."""


# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------

def _env(name: str, default: str = "") -> str:
    try:
        from django.conf import settings
        value = getattr(settings, name, "")
        if value:
            return value
    except Exception:
        pass
    return os.environ.get(name, default)


def _client() -> openai.OpenAI:
    key = _env("OPENAI_API_KEY")
    if not key:
        try:
            from dotenv import load_dotenv
            load_dotenv(Path.cwd() / ".env")
            key = os.environ.get("OPENAI_API_KEY", "")
        except Exception:
            pass
    if not key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set — add it to .env or the environment.")
    return openai.OpenAI(api_key=key)


# --------------------------------------------------------------------------
# Validation / normalization
# --------------------------------------------------------------------------

def _validate(payload: dict) -> dict:
    raw_topics = payload.get("topics") or []
    nodes, id_of_raw, seen = [], {}, set()
    for i, t in enumerate(raw_topics):
        title = str(t.get("title") or "").strip()
        key = title.lower()
        if not title or key in seen or len(nodes) >= _MAX_NODES:
            continue
        seen.add(key)
        node = {
            "id": f"t{len(nodes) + 1}",
            "title": title[:_MAX_TITLE],
            "date": t.get("date") or None,
            "order": t.get("order") or len(nodes) + 1,
            "summary": str(t.get("summary") or "")[:_MAX_SUMMARY],
        }
        id_of_raw[i] = node["id"]
        nodes.append(node)

    edges, seen_edges = [], set()

    def add_edge(source, target, kind):
        pair = (source, target)
        if source != target and pair not in seen_edges:
            seen_edges.add(pair)
            edges.append({"source": source, "target": target, "type": kind})

    # Forward-only indices (source taught before target) => acyclic graph.
    for p in payload.get("prerequisites") or []:
        s, t = p.get("source"), p.get("target")
        if isinstance(s, int) and isinstance(t, int) and s < t \
                and s in id_of_raw and t in id_of_raw:
            add_edge(id_of_raw[s], id_of_raw[t], "prerequisite")

    for d in payload.get("dependencies") or []:
        t = d.get("topic")
        if not isinstance(t, int) or t not in id_of_raw:
            continue
        for s in d.get("requires") or []:
            if isinstance(s, int) and s < t and s in id_of_raw:
                add_edge(id_of_raw[s], id_of_raw[t], "prerequisite")

    return {"course": payload.get("course"), "nodes": nodes, "edges": edges}


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def _call(client, model: str, system: str, user: str, schema: dict) -> dict:
    resp = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_schema", "json_schema": schema},
    )
    content = resp.choices[0].message.content or ""
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"model returned non-JSON output: {content[:200]!r}") from exc


def _topics_text(course, topics) -> str:
    lines = [f"COURSE: {course or 'unknown'}", "TOPICS:"]
    for i, t in enumerate(topics):
        lines.append(
            f"[{i}] {t.get('date') or 'undated'} "
            f"{str(t.get('title') or '').strip()} -- "
            f"{str(t.get('summary') or '').strip()}")
    return "\n".join(lines)


def build_graph(text: str, *, model: Optional[str] = None) -> dict:
    """Return a {"course", "nodes", "edges"} graph for the given text.

    Pass 1 extracts topics; pass 2 enumerates per-topic prerequisites
    over the extracted list (forward-only indices => acyclic edges).
    """
    client, mdl = _client(), model or _env("OPENAI_GRAPH_MODEL", _DEFAULT_MODEL)
    payload = _call(client, mdl, _SYSTEM_PROMPT, text, _SCHEMA)
    if payload.get("topics"):
        deps = _call(client, mdl, _DEPS_PROMPT,
                     _topics_text(payload.get("course"), payload["topics"]),
                     _DEPS_SCHEMA)
        payload["dependencies"] = deps.get("dependencies")
    return _validate(payload)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python -m core.services.graph_builder <file.pdf|file.txt>")
    src = Path(sys.argv[1])
    if src.suffix.lower() == ".pdf":
        from core.services.syllabus_parser import parse_syllabus_pdf
        text = parse_syllabus_pdf(src)
    else:
        text = src.read_text(encoding="utf-8", errors="replace")
    sys.stdout.reconfigure(errors="replace")
    print(json.dumps(build_graph(text), indent=2, ensure_ascii=False))
