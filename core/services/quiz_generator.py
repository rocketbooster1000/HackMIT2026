"""Generate a short, structured study quiz for a knowledge-map topic."""

from __future__ import annotations

from .graph_builder import _call, _client, _env


_DEFAULT_MODEL = "gpt-4.1-mini"

_QUIZ_SCHEMA = {
    "name": "topic_quiz",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "questions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "question": {"type": "string"},
                        "type": {"type": "string", "enum": ["multiple_choice"]},
                        "options": {"type": "array", "items": {"type": "string"}},
                        "correct_answer": {"type": "integer"},
                        "explanation": {"type": "string"},
                    },
                    "required": ["question", "type", "options", "correct_answer", "explanation"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["questions"],
        "additionalProperties": False,
    },
}

_SYSTEM_PROMPT = """You create concise, accurate study quizzes for students.

Create exactly five multiple-choice questions for the selected topic. Each
question must have four plausible options, one unambiguous correct answer, and
a short explanation that teaches the concept. Use the topic context as the
primary source. Prerequisites are supporting context only, not separate quiz
subjects. Match difficulty to the student's confidence: lower confidence means
more foundational questions; higher confidence permits more application and
reasoning questions. Do not mention the source documents or this instruction."""


def _validated_questions(payload):
    questions = payload.get("questions") if isinstance(payload, dict) else None
    if not isinstance(questions, list) or len(questions) != 5:
        raise ValueError("The quiz did not contain exactly five questions.")

    normalized = []
    for item in questions:
        if not isinstance(item, dict):
            raise ValueError("The quiz included an invalid question.")
        question = str(item.get("question") or "").strip()
        explanation = str(item.get("explanation") or "").strip()
        options = item.get("options")
        answer = item.get("correct_answer")
        if (
            item.get("type") != "multiple_choice" or not question or not explanation
            or not isinstance(options, list) or len(options) != 4
            or not all(isinstance(option, str) and option.strip() for option in options)
            or isinstance(answer, bool) or not isinstance(answer, int) or not 0 <= answer <= 3
        ):
            raise ValueError("The quiz included malformed question data.")
        normalized.append({"question": question, "type": "multiple_choice", "options": [option.strip() for option in options], "correct_answer": answer, "explanation": explanation})
    return normalized


def generate_quiz(*, topic, prerequisites, documents, model=None):
    """Return five validated question dictionaries for ``topic``."""
    context = {
        "topic": {"id": topic.id, "name": topic.name, "description": topic.description, "confidence": topic.confidence},
        "prerequisites": prerequisites,
        "documents": documents,
    }
    payload = _call(
        _client(), model or _env("OPENAI_QUIZ_MODEL", _DEFAULT_MODEL), _SYSTEM_PROMPT,
        f"Create the quiz from this course context:\n{context!r}", _QUIZ_SCHEMA,
    )
    return {"questions": _validated_questions(payload)}
