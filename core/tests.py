import json
import os
import tempfile
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from .models import Document, Prerequisite, Topic


class WorkspaceApiTests(TestCase):
    def post_json(self, url, payload):
        return self.client.post(url, data=json.dumps(payload), content_type="application/json")

    def test_graph_crud_and_tags(self):
        sandbox = self.post_json("/api/sandboxes/", {"name": "Calculus"}).json()["sandbox"]
        tag = self.post_json("/api/tags/", {"name": "Exam 1"}).json()["tag"]
        first = self.post_json(f"/api/sandboxes/{sandbox['id']}/topics/", {"name": "Limits", "description": "Foundations", "tag_ids": [tag["id"]]}).json()["topic"]
        second = self.post_json(f"/api/sandboxes/{sandbox['id']}/topics/", {"name": "Derivatives", "tag_ids": []}).json()["topic"]
        moved = self.client.patch(f"/api/topics/{second['id']}/", data=json.dumps({"x": 450, "y": 280}), content_type="application/json")
        self.assertEqual(moved.status_code, 200)
        self.assertEqual((moved.json()["topic"]["x"], moved.json()["topic"]["y"]), (450.0, 280.0))
        edge = self.post_json(f"/api/sandboxes/{sandbox['id']}/prerequisites/", {"prerequisite": first["id"], "topic": second["id"]})
        self.assertEqual(edge.status_code, 201)
        self.assertEqual(self.client.post(f"/api/sandboxes/{sandbox['id']}/tags/", data=json.dumps({"tag_id": tag["id"], "topic_ids": [second["id"]]}), content_type="application/json").status_code, 200)
        graph = self.client.get(f"/api/sandboxes/{sandbox['id']}/graph/").json()
        self.assertEqual(len(graph["nodes"]), 2)
        self.assertEqual(len(graph["edges"]), 1)
        self.assertIn("Exam 1", next(node for node in graph["nodes"] if node["id"] == second["id"])["tags"])
        self.assertEqual(self.client.delete(f"/api/topics/{first['id']}/").status_code, 200)
        self.assertFalse(Prerequisite.objects.exists())

    def test_tags_can_be_loaded_assigned_to_multiple_topics_and_removed(self):
        sandbox = self.post_json("/api/sandboxes/", {"name": "Physics"}).json()["sandbox"]
        tag_response = self.post_json("/api/tags/", {"name": "Exam 1"})
        self.assertEqual(tag_response.status_code, 201)
        tag = tag_response.json()["tag"]
        self.assertIn(tag, self.client.get("/api/tags/").json()["tags"])
        duplicate = self.post_json("/api/tags/", {"name": "exam 1"})
        self.assertEqual(duplicate.status_code, 400)

        topics = [
            self.post_json(f"/api/sandboxes/{sandbox['id']}/topics/", {"name": name}).json()["topic"]
            for name in ("Motion", "Forces", "Energy")
        ]
        assignment = self.post_json(
            f"/api/sandboxes/{sandbox['id']}/tags/",
            {"tag_id": tag["id"], "topic_ids": [topic["id"] for topic in topics]},
        )
        self.assertEqual(assignment.status_code, 200)

        graph = self.client.get(f"/api/sandboxes/{sandbox['id']}/graph/").json()
        for node in graph["nodes"]:
            self.assertIn(tag["id"], node["tag_ids"])
            self.assertIn(tag["name"], node["tags"])

        removal = self.client.delete(f"/api/topics/{topics[0]['id']}/tags/{tag['id']}/")
        self.assertEqual(removal.status_code, 200)
        refreshed = self.client.get(f"/api/sandboxes/{sandbox['id']}/graph/").json()
        removed_node = next(node for node in refreshed["nodes"] if node["id"] == topics[0]["id"])
        self.assertNotIn(tag["id"], removed_node["tag_ids"])
        self.assertNotIn(tag["name"], removed_node["tags"])
        self.assertTrue(all(tag["id"] in node["tag_ids"] for node in refreshed["nodes"] if node["id"] != topics[0]["id"]))

    def test_document_upload_is_saved_and_associated(self):
        with tempfile.TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            sandbox = self.post_json("/api/sandboxes/", {"name": "Physics"}).json()["sandbox"]
            topic = self.post_json(f"/api/sandboxes/{sandbox['id']}/topics/", {"name": "Motion", "tag_ids": []}).json()["topic"]
            upload = SimpleUploadedFile("notes.pdf", b"%PDF-1.4 test", content_type="application/pdf")
            response = self.client.post(f"/api/sandboxes/{sandbox['id']}/documents/", {"file": upload, "topic_ids": json.dumps([topic["id"]])})
            self.assertEqual(response.status_code, 201)
            self.assertEqual(Document.objects.count(), 1)
            self.assertEqual(Topic.objects.get(pk=topic["id"]).documents.count(), 1)
            url = response.json()["document"]["url"]
            self.assertTrue(url.startswith("/media/documents/"))
            self.assertTrue(url.endswith(".pdf"))
            graph = self.client.get(f"/api/sandboxes/{sandbox['id']}/graph/").json()
            self.assertEqual(graph["nodes"][0]["documents"][0]["url"], url)

    def test_slide_deck_upload_is_accepted(self):
        sandbox = self.post_json("/api/sandboxes/", {"name": "Physics"}).json()["sandbox"]
        topic = self.post_json(f"/api/sandboxes/{sandbox['id']}/topics/", {"name": "Motion"}).json()["topic"]
        upload = SimpleUploadedFile("lecture.pptx", b"PK fake", content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation")
        response = self.client.post(f"/api/sandboxes/{sandbox['id']}/documents/", {"file": upload, "topic_ids": json.dumps([topic["id"]])})
        self.assertEqual(response.status_code, 201)

    def test_document_can_be_assigned_after_upload(self):
        sandbox = self.post_json("/api/sandboxes/", {"name": "Physics"}).json()["sandbox"]
        other = self.post_json("/api/sandboxes/", {"name": "Other"}).json()["sandbox"]
        topic = self.post_json(f"/api/sandboxes/{sandbox['id']}/topics/", {"name": "Motion"}).json()["topic"]
        foreign = self.post_json(f"/api/sandboxes/{other['id']}/topics/", {"name": "Nope"}).json()["topic"]
        upload = SimpleUploadedFile("notes.pdf", b"%PDF-1.4 test", content_type="application/pdf")
        doc = self.client.post(f"/api/sandboxes/{sandbox['id']}/documents/", {"file": upload, "topic_ids": "[]"}).json()["document"]
        self.assertEqual(doc["topic_ids"], [])
        response = self.client.patch(f"/api/documents/{doc['id']}/", data=json.dumps({"topic_ids": [topic["id"]]}), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["document"]["topic_ids"], [topic["id"]])
        bad = self.client.patch(f"/api/documents/{doc['id']}/", data=json.dumps({"topic_ids": [foreign["id"]]}), content_type="application/json")
        self.assertEqual(bad.status_code, 400)
        graph = self.client.get(f"/api/sandboxes/{sandbox['id']}/graph/").json()
        self.assertEqual(len(graph["documents"]), 1)

    @patch("core.services.graph_builder.match_topics")
    @patch("core.services.syllabus_parser.extract_document_text")
    def test_document_auto_assigns_to_matching_topics(self, extract, match):
        extract.return_value = "Newton's laws: force equals mass times acceleration."
        match.return_value = [1]
        sandbox = self.post_json("/api/sandboxes/", {"name": "Physics"}).json()["sandbox"]
        topics = [
            self.post_json(f"/api/sandboxes/{sandbox['id']}/topics/", {"name": name}).json()["topic"]
            for name in ("Motion", "Forces")
        ]
        upload = SimpleUploadedFile("lecture.pdf", b"%PDF-1.4 test", content_type="application/pdf")
        response = self.client.post(f"/api/sandboxes/{sandbox['id']}/documents/", {"file": upload, "topic_ids": "[]"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["document"]["topic_ids"], [topics[1]["id"]])
        self.assertEqual(Topic.objects.get(pk=topics[1]["id"]).documents.count(), 1)
        self.assertEqual(Topic.objects.get(pk=topics[0]["id"]).documents.count(), 0)

    @patch("core.services.syllabus_parser.extract_document_text", side_effect=ValueError("unsupported"))
    def test_document_upload_succeeds_when_autoassign_fails(self, extract):
        sandbox = self.post_json("/api/sandboxes/", {"name": "Physics"}).json()["sandbox"]
        self.post_json(f"/api/sandboxes/{sandbox['id']}/topics/", {"name": "Motion"})
        upload = SimpleUploadedFile("deck.ppt", b"binary", content_type="application/vnd.ms-powerpoint")
        response = self.client.post(f"/api/sandboxes/{sandbox['id']}/documents/", {"file": upload, "topic_ids": "[]"})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["document"]["topic_ids"], [])

    def test_document_delete_removes_row_and_file(self):
        with tempfile.TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            sandbox = self.post_json("/api/sandboxes/", {"name": "Physics"}).json()["sandbox"]
            topic = self.post_json(f"/api/sandboxes/{sandbox['id']}/topics/", {"name": "Motion"}).json()["topic"]
            upload = SimpleUploadedFile("notes.pdf", b"%PDF-1.4 test", content_type="application/pdf")
            doc_id = self.client.post(f"/api/sandboxes/{sandbox['id']}/documents/", {"file": upload, "topic_ids": json.dumps([topic["id"]])}).json()["document"]["id"]
            path = Document.objects.get(pk=doc_id).file.path
            self.assertTrue(os.path.exists(path))
            self.assertEqual(self.client.delete(f"/api/documents/{doc_id}/").status_code, 200)
            self.assertFalse(Document.objects.exists())
            self.assertFalse(os.path.exists(path))
            self.assertEqual(Topic.objects.get(pk=topic["id"]).documents.count(), 0)

    @patch("core.services.graph_builder.build_graph")
    @patch("core.services.syllabus_parser.parse_syllabus_pdf")
    def test_syllabus_multipart_post_reaches_syllabus_view(self, parse_pdf, build_graph):
        parse_pdf.return_value = "Limits and derivatives"
        build_graph.return_value = {
            "nodes": [{"id": "t1", "title": "Limits", "summary": "Function behavior.", "order": 1}],
            "edges": [],
        }
        sandbox = self.post_json("/api/sandboxes/", {"name": "Analysis"}).json()["sandbox"]
        upload = SimpleUploadedFile("syllabus.pdf", b"%PDF-1.4 test", content_type="application/pdf")
        response = self.client.post(f"/api/sandboxes/{sandbox['id']}/syllabus/", {"file": upload})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["nodes"][0]["name"], "Limits")
