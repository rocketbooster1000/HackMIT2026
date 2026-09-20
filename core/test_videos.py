import json
from unittest.mock import patch

from django.test import TestCase, override_settings

from .models import Sandbox, Tag, Topic, VideoJob
from .services import remotion_renderer, script_writer, tts, video_pipeline


def _sandbox_with_topics():
    sandbox = Sandbox.objects.create(name="Calculus")
    tag = Tag.objects.create(name="Exam 1")
    first = Topic.objects.create(
        sandbox=sandbox, name="Limits", description="Function behavior near a point.", order=1)
    second = Topic.objects.create(
        sandbox=sandbox, name="Derivatives", description="Rates of change.", order=2)
    first.tags.add(tag)
    return sandbox, [first, second]


@patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
class ScriptWriterTests(TestCase):
    def _payload(self):
        return {
            "title": "Limits and Derivatives",
            "scenes": [
                {
                    "title": "Intro",
                    "narration": "Let's talk about limits.",
                    "on_screen_text": ["What is a limit?", "Why it matters"],
                    "visual": "A curve approaching a point on the x-axis",
                    "keywords": [{"term": "Limit", "icon": "Sigma"}],
                    "layout": "definition",
                    "assumption": None,
                    "duration_hint": 6.5,
                },
                {
                    "title": "",
                    "narration": "",
                    "on_screen_text": [],
                    "duration_hint": 3,
                },
            ],
        }

    @patch("core.services.script_writer._call")
    def test_validate_keeps_usable_scenes(self, call):
        call.return_value = self._payload()
        _, topics = _sandbox_with_topics()
        script = script_writer.write_script(topics)
        self.assertEqual(script["title"], "Limits and Derivatives")
        self.assertEqual(len(script["scenes"]), 1)
        self.assertEqual(script["scenes"][0]["duration_hint"], 6.5)

    @patch("core.services.script_writer._call")
    def test_validate_normalizes_rich_fields(self, call):
        payload = self._payload()
        scene = payload["scenes"][0]
        scene["keywords"] = [
            {"term": "Limit", "icon": "Sigma"},
            {"term": "limit", "icon": None},  # case-insensitive dup
            "epsilon",                         # bare string tolerated
            *[{"term": f"k{i}", "icon": None} for i in range(5)],
        ]
        scene["layout"] = "sideways"  # unknown -> default
        scene["assumption"] = ""      # empty -> None
        call.return_value = payload
        _, topics = _sandbox_with_topics()
        scene = script_writer.write_script(topics)["scenes"][0]
        self.assertEqual(scene["layout"], "definition")
        self.assertIsNone(scene["assumption"])
        self.assertEqual(
            [k["term"] for k in scene["keywords"]],
            ["Limit", "epsilon", "k0", "k1", "k2"],  # deduped, capped at 5
        )
        self.assertEqual(scene["keywords"][0]["icon"], "Sigma")
        self.assertIsNone(scene["keywords"][2]["icon"])

    @patch("core.services.script_writer._call")
    def test_validate_defaults_missing_rich_fields(self, call):
        payload = self._payload()
        payload["scenes"] = [{
            "narration": "Only narration.", "on_screen_text": [],
            "duration_hint": 4,
        }]
        call.return_value = payload
        _, topics = _sandbox_with_topics()
        scene = script_writer.write_script(topics)["scenes"][0]
        self.assertEqual(
            scene,
            {"title": "Scene 1", "narration": "Only narration.",
             "on_screen_text": [], "visual": "", "keywords": [],
             "layout": "definition", "assumption": None, "duration_hint": 4.0},
        )

    @patch("core.services.script_writer._call")
    def test_retries_once_on_invalid_output(self, call):
        call.side_effect = [
            {"scenes": [{"narration": "", "on_screen_text": [], "duration_hint": 1}]},
            self._payload(),
        ]
        _, topics = _sandbox_with_topics()
        script = script_writer.write_script(topics)
        self.assertEqual(call.call_count, 2)
        self.assertEqual(len(script["scenes"]), 1)

    @patch("core.services.script_writer._call")
    def test_raises_after_two_bad_responses(self, call):
        call.side_effect = RuntimeError("model returned non-JSON output: 'x'")
        _, topics = _sandbox_with_topics()
        with self.assertRaises(RuntimeError):
            script_writer.write_script(topics)
        self.assertEqual(call.call_count, 2)


class TtsTests(TestCase):
    @patch("core.services.tts._run")
    def test_synthesize_returns_boundary_duration(self, run):
        # _run is async, so patch gives an AsyncMock; return_value is the
        # awaited result, not a coroutine.
        run.return_value = 7.25
        out = self._tmpfile()
        out.write_bytes(b"x")
        self.assertEqual(tts.synthesize("hello", out), 7.25)

    def _tmpfile(self):
        import tempfile
        from pathlib import Path
        return Path(tempfile.mkdtemp()) / "scene-0.mp3"

    @patch("core.services.tts._run")
    def test_synthesize_retries_then_fails(self, run):
        run.side_effect = RuntimeError("boom")
        out = self._tmpfile()
        out.write_bytes(b"x")
        with self.assertRaises(tts.TTSError):
            tts.synthesize("hello", out)
        self.assertEqual(run.call_count, 2)

    def test_scene_duration_prefers_measured(self):
        self.assertEqual(tts.scene_duration(8.2, 50.0), 8.2)
        self.assertEqual(tts.scene_duration(0.0, 30.0), 20.0)
        self.assertEqual(tts.scene_duration(0.0, 1.0), 4.0)
        self.assertEqual(tts.scene_duration(0.0, 0.0), 4.0)


class RendererTests(TestCase):
    def test_render_video_requires_project(self):
        with override_settings(BASE_DIR=self._missing()):
            with patch.dict("os.environ", {"REMOTION_PROJECT_DIR": str(self._missing() / "nope")}):
                with self.assertRaises(remotion_renderer.RenderError):
                    remotion_renderer.render_video({"scenes": []}, 1)

    def _missing(self):
        import tempfile
        from pathlib import Path
        return Path(tempfile.mkdtemp())


class VideoApiTests(TestCase):
    def post_json(self, url, payload):
        return self.client.post(url, data=json.dumps(payload), content_type="application/json")

    @patch("core.views.threading.Thread")
    def test_generate_returns_202_and_job(self, thread_cls):
        sandbox, topics = _sandbox_with_topics()
        response = self.post_json("/api/videos/generate/", {
            "sandbox_id": sandbox.id,
            "topic_ids": [t.id for t in topics],
        })
        self.assertEqual(response.status_code, 202)
        job = VideoJob.objects.get(pk=response.json()["job_id"])
        self.assertEqual(job.status, "queued")
        self.assertEqual(sorted(job.topic_ids), sorted(t.id for t in topics))
        thread_cls.return_value.start.assert_called_once()

    def test_generate_rejects_empty_selection(self):
        sandbox, _ = _sandbox_with_topics()
        response = self.post_json("/api/videos/generate/", {"sandbox_id": sandbox.id, "topic_ids": []})
        self.assertEqual(response.status_code, 400)

    def test_generate_rejects_foreign_topics(self):
        sandbox, _ = _sandbox_with_topics()
        other = Sandbox.objects.create(name="Other")
        foreign = Topic.objects.create(sandbox=other, name="Nope")
        response = self.post_json("/api/videos/generate/", {
            "sandbox_id": sandbox.id, "topic_ids": [foreign.id]})
        self.assertEqual(response.status_code, 400)

    def test_status_endpoint(self):
        sandbox, topics = _sandbox_with_topics()
        job = VideoJob.objects.create(sandbox=sandbox, topic_ids=[topics[0].id])
        response = self.client.get(f"/api/videos/jobs/{job.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "queued")
        self.assertIsNone(response.json()["video_url"])


class PipelineIntegrationTests(TestCase):
    @patch("core.services.remotion_renderer.render_video")
    @patch("core.services.tts.synthesize")
    @patch("core.services.script_writer.write_script")
    def test_full_pipeline_marks_done(self, write_script, synthesize, render):
        sandbox, topics = _sandbox_with_topics()
        write_script.return_value = {
            "title": "Limits",
            "scenes": [{
                "title": "Intro", "narration": "Hi.",
                "on_screen_text": ["a"], "duration_hint": 5.0,
                "keywords": [{"term": "Limit", "icon": "Sigma"}],
                "layout": "process", "visual": "arrow", "assumption": None,
            }],
        }
        synthesize.return_value = 4.0

        def fake_render(props, job_id):
            import tempfile
            from pathlib import Path
            scene = props["scenes"][0]
            self.assertEqual(scene["durationInFrames"], 120)
            self.assertEqual(scene["layout"], "process")
            self.assertEqual(scene["keywords"], [{"term": "Limit", "icon": "Sigma"}])
            self.assertEqual(scene["visual"], "arrow")
            self.assertIsNone(scene["assumption"])
            out = Path(tempfile.mkdtemp()) / f"{job_id}.mp4"
            out.write_bytes(b"fake-mp4")
            return out
        render.side_effect = fake_render

        job = VideoJob.objects.create(sandbox=sandbox, topic_ids=[topics[0].id])
        video_pipeline.run_video_job(job.id)
        job.refresh_from_db()
        self.assertEqual(job.status, "done")
        self.assertTrue(job.video.name.endswith(".mp4"))
        self.assertEqual(job.error, "")

    @patch("core.services.script_writer.write_script", side_effect=RuntimeError("no api key"))
    def test_pipeline_failure_marks_failed(self, _):
        sandbox, topics = _sandbox_with_topics()
        job = VideoJob.objects.create(sandbox=sandbox, topic_ids=[topics[0].id])
        video_pipeline.run_video_job(job.id)
        job.refresh_from_db()
        self.assertEqual(job.status, "failed")
        self.assertIn("no api key", job.error)
