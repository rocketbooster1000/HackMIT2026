"""End-to-end video job orchestration.

`run_video_job(job_id)` is invoked on a background thread by the
``generate_video`` view. It moves the VideoJob through
generating_script -> generating_audio -> rendering -> done/failed,
writing per-scene TTS audio to a temp working dir and the finished mp4
into ``MEDIA_ROOT/videos/``.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path

from django.db import close_old_connections

logger = logging.getLogger(__name__)


def _set_status(job, status, **fields):
    job.status = status
    for key, value in fields.items():
        setattr(job, key, value)
    job.save(update_fields=["status", *fields.keys(), "updated_at"])


def _prerequisite_names(sandbox, topics) -> dict:
    from ..models import Prerequisite
    names = {}
    edges = Prerequisite.objects.filter(
        sandbox=sandbox, topic_id__in=[t.id for t in topics]
    ).select_related("prerequisite")
    for edge in edges:
        names.setdefault(edge.topic_id, []).append(edge.prerequisite.name)
    return names


def run_video_job(job_id: int) -> None:
    """Run the full pipeline for a VideoJob; never raises."""
    close_old_connections()
    from ..models import VideoJob  # deferred so threads get fresh state
    workdir = Path(tempfile.mkdtemp(prefix=f"video-job-{job_id}-"))
    job = None
    try:
        job = VideoJob.objects.select_related("sandbox").get(pk=job_id)
        topics = list(
            job.sandbox.topics.filter(pk__in=job.topic_ids)
            .prefetch_related("tags")
        )
        if not topics:
            raise RuntimeError("selected topics no longer exist")

        _set_status(job, VideoJob.Status.GENERATING_SCRIPT)
        from . import script_writer
        script = script_writer.write_script(
            topics, _prerequisite_names(job.sandbox, topics))

        _set_status(job, VideoJob.Status.GENERATING_AUDIO)
        from . import tts
        scenes = []
        for i, scene in enumerate(script["scenes"]):
            audio_path = workdir / f"scene-{i}.mp3"
            measured = tts.synthesize(scene["narration"], audio_path)
            seconds = tts.scene_duration(measured, scene.get("duration_hint"))
            scenes.append({
                "title": scene["title"],
                "bullets": scene["on_screen_text"],
                "audio": audio_path,
                "durationInFrames": int(seconds * 30 + 0.999),
            })

        _set_status(job, VideoJob.Status.RENDERING)
        from . import remotion_renderer
        out_path = remotion_renderer.render_video({"scenes": scenes}, job.id)

        _set_status(
            job, VideoJob.Status.DONE,
            video=f"videos/{out_path.name}", error="",
        )
    except Exception as exc:  # noqa: BLE001 — surfaced to the client
        logger.exception("video job %s failed", job_id)
        try:
            if job is not None:
                _set_status(job, VideoJob.Status.FAILED, error=str(exc)[:2000])
        except Exception:
            logger.exception("could not mark video job %s failed", job_id)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
        close_old_connections()
