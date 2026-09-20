import json
import math
from pathlib import Path

from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_http_methods

from .models import Document, Prerequisite, Sandbox, Tag, Topic


MAX_UPLOAD_BYTES = 20 * 1024 * 1024
ALLOWED_UPLOAD_SUFFIXES = {".pdf", ".docx"}


def _body(request):
    try:
        return json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return {}


def _error(message, status=400):
    return JsonResponse({"error": message}, status=status)


def _topic_data(topic):
    return {
        "id": topic.id,
        "name": topic.name,
        "description": topic.description,
        "tags": list(topic.tags.values_list("name", flat=True)),
        "tag_ids": list(topic.tags.values_list("id", flat=True)),
        "documents": [{"id": doc.id, "name": doc.name} for doc in topic.documents.all()],
        "order": topic.order,
        "x": topic.x,
        "y": topic.y,
        "confidence": topic.confidence,
    }


def _prerequisite_context(topic):
    """Return prerequisite ancestors once, nearest topics first."""
    result, seen, pending = [], {topic.id}, [topic]
    while pending:
        current = pending.pop(0)
        for edge in current.requires.select_related("prerequisite").all():
            prerequisite = edge.prerequisite
            if prerequisite.id in seen:
                continue
            seen.add(prerequisite.id)
            result.append({"id": prerequisite.id, "name": prerequisite.name, "description": prerequisite.description})
            pending.append(prerequisite)
    return result


def _document_context(topic):
    """Use associated document text when it can be safely extracted."""
    from .services.syllabus_parser import parse_syllabus_docx, parse_syllabus_pdf

    documents, remaining = [], 8000
    for document in topic.documents.all():
        item = {"id": document.id, "name": document.name}
        suffix = Path(document.name).suffix.lower()
        if remaining and suffix in ALLOWED_UPLOAD_SUFFIXES:
            try:
                document.file.open("rb")
                parser = parse_syllabus_pdf if suffix == ".pdf" else parse_syllabus_docx
                text = parser(document.file).strip()
                document.file.close()
                if text:
                    item["text"] = text[:remaining]
                    remaining -= len(item["text"])
            except Exception:
                try:
                    document.file.close()
                except Exception:
                    pass
        documents.append(item)
    return documents


def _default_position(order):
    index = max(order - 1, 0)
    return {
        "x": 230 + (index % 3) * 270,
        "y": 105 + (index // 3) * 145,
    }


def _coordinates(data, fallback):
    x, y = data.get("x", fallback["x"]), data.get("y", fallback["y"])
    try:
        x, y = float(x), float(y)
    except (TypeError, ValueError):
        return None
    return (x, y) if math.isfinite(x) and math.isfinite(y) else None


def _sandbox_data(sandbox):
    return {"id": sandbox.id, "name": sandbox.name}


def _validate_upload(upload):
    if not upload:
        return "Choose a file to upload."
    if Path(upload.name).suffix.lower() not in ALLOWED_UPLOAD_SUFFIXES:
        return "Only PDF and DOCX files are supported."
    if upload.size > MAX_UPLOAD_BYTES:
        return "Files must be 20 MB or smaller."
    return None


def _sandbox_topics(sandbox, ids):
    try:
        ids = [int(value) for value in ids]
    except (TypeError, ValueError):
        return None
    topics = list(sandbox.topics.filter(id__in=ids))
    return topics if len(topics) == len(set(ids)) else None


@require_http_methods(["GET", "POST"])
def sandboxes(request):
    if request.method == "GET":
        return JsonResponse({"sandboxes": [_sandbox_data(item) for item in Sandbox.objects.all()]})
    data = _body(request)
    name = str(data.get("name") or "New Sandbox").strip()[:120] or "New Sandbox"
    sandbox = Sandbox.objects.create(name=name)
    return JsonResponse({"sandbox": _sandbox_data(sandbox)}, status=201)


@require_http_methods(["GET", "PATCH", "DELETE"])
def sandbox_detail(request, sandbox_id):
    sandbox = get_object_or_404(Sandbox, pk=sandbox_id)
    if request.method == "GET":
        return JsonResponse({"sandbox": _sandbox_data(sandbox)})
    if request.method == "DELETE":
        sandbox.delete()
        return JsonResponse({"ok": True})
    name = str(_body(request).get("name") or "").strip()
    if not name:
        return _error("A sandbox name is required.")
    sandbox.name = name[:120]
    sandbox.save(update_fields=["name", "updated_at"])
    return JsonResponse({"sandbox": _sandbox_data(sandbox)})


def _graph_response(sandbox):
    topics = list(sandbox.topics.prefetch_related("tags", "documents"))
    return JsonResponse({
        "sandbox": _sandbox_data(sandbox),
        "nodes": [_topic_data(topic) for topic in topics],
        "edges": [
            {"id": edge.id, "prerequisite": edge.prerequisite_id, "topic": edge.topic_id}
            for edge in sandbox.prerequisites.all()
        ],
    })


@require_http_methods(["GET"])
def sandbox_graph(request, sandbox_id):
    return _graph_response(get_object_or_404(Sandbox, pk=sandbox_id))


@require_http_methods(["POST"])
def sandbox_topics(request, sandbox_id):
    sandbox = get_object_or_404(Sandbox, pk=sandbox_id)
    data = _body(request)
    name = str(data.get("name") or "").strip()
    if not name:
        return _error("A topic name is required.")
    tag_ids = data.get("tag_ids", [])
    tags = list(Tag.objects.filter(id__in=tag_ids))
    if len(tags) != len(set(tag_ids)):
        return _error("One or more tags do not exist.")
    order = sandbox.topics.count() + 1
    coordinates = _coordinates(data, _default_position(order))
    if coordinates is None:
        return _error("Node coordinates must be valid numbers.")
    topic = Topic.objects.create(
        sandbox=sandbox,
        name=name[:120],
        description=str(data.get("description") or "")[:2000],
        order=order,
        x=coordinates[0],
        y=coordinates[1],
    )
    topic.tags.set(tags)
    return JsonResponse({"topic": _topic_data(topic)}, status=201)


@require_http_methods(["PATCH", "DELETE"])
def topic_detail(request, topic_id):
    topic = get_object_or_404(Topic.objects.prefetch_related("tags", "documents"), pk=topic_id)
    if request.method == "DELETE":
        topic.delete()
        return JsonResponse({"ok": True})
    data = _body(request)
    update_fields = []
    if "name" in data:
        name = str(data.get("name") or "").strip()
        if not name:
            return _error("A topic name is required.")
        topic.name = name[:120]
        topic.description = str(data.get("description") or "")[:2000]
        update_fields.extend(["name", "description"])
    if "x" in data or "y" in data:
        fallback = {"x": topic.x, "y": topic.y}
        if fallback["x"] is None or fallback["y"] is None:
            fallback = _default_position(topic.order)
        coordinates = _coordinates(data, fallback)
        if coordinates is None:
            return _error("Node coordinates must be valid numbers.")
        topic.x, topic.y = coordinates
        update_fields.extend(["x", "y"])
    if "confidence" in data:
        confidence = data["confidence"]
        if isinstance(confidence, bool) or not isinstance(confidence, int) or not 0 <= confidence <= 5:
            return _error("Confidence must be an integer from 0 to 5.")
        topic.confidence = confidence
        update_fields.append("confidence")
    if update_fields:
        topic.save(update_fields=update_fields)
    if "tag_ids" in data:
        tag_ids = data["tag_ids"]
        tags = list(Tag.objects.filter(id__in=tag_ids))
        if len(tags) != len(set(tag_ids)):
            return _error("One or more tags do not exist.")
        topic.tags.set(tags)
    return JsonResponse({"topic": _topic_data(topic)})


@require_http_methods(["POST"])
def topic_quiz(request, topic_id):
    topic = get_object_or_404(Topic.objects.prefetch_related("documents"), pk=topic_id)
    try:
        from .services.quiz_generator import generate_quiz
        quiz = generate_quiz(topic=topic, prerequisites=_prerequisite_context(topic), documents=_document_context(topic))
    except Exception:
        return _error("Unable to generate quiz. Please try again.", status=422)
    return JsonResponse({"quiz": {"topic": {"id": topic.id, "name": topic.name}, "questions": quiz["questions"]}})


@require_http_methods(["GET", "POST"])
def tags(request):
    if request.method == "GET":
        return JsonResponse({"tags": [{"id": tag.id, "name": tag.name} for tag in Tag.objects.all()]})
    name = str(_body(request).get("name") or "").strip()
    if not name:
        return _error("A tag name is required.")
    if Tag.objects.filter(name__iexact=name).exists():
        return _error("A tag with that name already exists.")
    tag = Tag.objects.create(name=name[:80])
    return JsonResponse({"tag": {"id": tag.id, "name": tag.name}}, status=201)


@require_http_methods(["POST"])
def apply_tag(request, sandbox_id):
    sandbox = get_object_or_404(Sandbox, pk=sandbox_id)
    data = _body(request)
    tag = get_object_or_404(Tag, pk=data.get("tag_id"))
    topics = _sandbox_topics(sandbox, data.get("topic_ids", []))
    if not topics:
        return _error("Select at least one topic from this sandbox.")
    for topic in topics:
        topic.tags.add(tag)
    return JsonResponse({"ok": True})


@require_http_methods(["DELETE"])
def remove_tag(request, topic_id, tag_id):
    topic = get_object_or_404(Topic, pk=topic_id)
    topic.tags.remove(get_object_or_404(Tag, pk=tag_id))
    return JsonResponse({"ok": True})


@require_http_methods(["POST"])
def prerequisites(request, sandbox_id):
    sandbox = get_object_or_404(Sandbox, pk=sandbox_id)
    data = _body(request)
    source = sandbox.topics.filter(pk=data.get("prerequisite")).first()
    target = sandbox.topics.filter(pk=data.get("topic")).first()
    if not source or not target or source.id == target.id:
        return _error("Choose two different topics from this sandbox.")
    edge, _ = Prerequisite.objects.get_or_create(sandbox=sandbox, prerequisite=source, topic=target)
    return JsonResponse({"edge": {"id": edge.id, "prerequisite": edge.prerequisite_id, "topic": edge.topic_id}}, status=201)


@require_http_methods(["POST"])
def documents(request, sandbox_id):
    sandbox = get_object_or_404(Sandbox, pk=sandbox_id)
    upload = request.FILES.get("file")
    if error := _validate_upload(upload):
        return _error(error)
    try:
        topic_ids = json.loads(request.POST.get("topic_ids", "[]"))
    except json.JSONDecodeError:
        return _error("Invalid topic selection.")
    topics = _sandbox_topics(sandbox, topic_ids)
    if topics is None:
        return _error("One or more selected topics do not exist in this sandbox.")
    document = Document.objects.create(sandbox=sandbox, file=upload, name=upload.name)
    document.topics.set(topics)
    return JsonResponse({"document": {"id": document.id, "name": document.name, "topic_ids": [topic.id for topic in topics]}}, status=201)


@require_http_methods(["POST"])
def syllabus(request, sandbox_id):
    sandbox = get_object_or_404(Sandbox, pk=sandbox_id)
    upload = request.FILES.get("file")
    if error := _validate_upload(upload):
        return _error(error)
    try:
        from .services.graph_builder import build_graph
        from .services.syllabus_parser import parse_syllabus_docx, parse_syllabus_pdf
        parser = parse_syllabus_pdf if Path(upload.name).suffix.lower() == ".pdf" else parse_syllabus_docx
        graph = build_graph(parser(upload))
        upload.seek(0)
    except Exception as exc:
        return _error(f"Syllabus processing failed: {exc}", status=422)

    with transaction.atomic():
        sandbox.syllabus = upload
        sandbox.save(update_fields=["syllabus", "updated_at"])
        sandbox.topics.all().delete()
        topics = []
        for index, item in enumerate(graph["nodes"], start=1):
            position = _default_position(item.get("order") or index)
            topics.append(Topic.objects.create(
                sandbox=sandbox, name=item["title"], description=item.get("summary") or "", order=item.get("order") or 0, x=position["x"], y=position["y"],
            ))
        by_graph_id = {item["id"]: topic for item, topic in zip(graph["nodes"], topics)}
        Prerequisite.objects.bulk_create([
            Prerequisite(sandbox=sandbox, prerequisite=by_graph_id[edge["source"]], topic=by_graph_id[edge["target"]])
            for edge in graph["edges"] if edge["source"] in by_graph_id and edge["target"] in by_graph_id
        ])
    return _graph_response(sandbox)
