import json
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

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
        sandbox = self.post_json("/api/sandboxes/", {"name": "Physics"}).json()["sandbox"]
        topic = self.post_json(f"/api/sandboxes/{sandbox['id']}/topics/", {"name": "Motion", "tag_ids": []}).json()["topic"]
        upload = SimpleUploadedFile("notes.pdf", b"%PDF-1.4 test", content_type="application/pdf")
        response = self.client.post(f"/api/sandboxes/{sandbox['id']}/documents/", {"file": upload, "topic_ids": json.dumps([topic["id"]])})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Document.objects.count(), 1)
        self.assertEqual(Topic.objects.get(pk=topic["id"]).documents.count(), 1)

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
