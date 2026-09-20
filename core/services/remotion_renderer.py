"""Render a video through the Remotion project in ``video-service/``.

`render_video(props, job_id)` stages the props JSON and scene audio inside
the Remotion project, then invokes ``node render.mjs`` as a subprocess.
The Node script bundles the composition and writes the finished mp4 to
``MEDIA_ROOT/videos/<job_id>.mp4``.

Kept deliberately narrow — swapping this for an HTTP render service later
only requires reimplementing ``render_video``.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Union

from .graph_builder import _env

FPS = 30


class RenderError(RuntimeError):
    pass


def _project_dir() -> Path:
    try:
        from django.conf import settings
        base = Path(settings.BASE_DIR)
    except Exception:
        base = Path.cwd()
    return Path(_env("REMOTION_PROJECT_DIR", str(base / "video-service")))


def _media_root() -> Path:
    try:
        from django.conf import settings
        return Path(settings.MEDIA_ROOT)
    except Exception:
        return Path.cwd() / "media"


def render_video(props: dict, job_id: Union[int, str]) -> Path:
    """Render ``props`` and return the path to the finished mp4.

    ``props`` must contain ``scenes`` with per-scene ``title``, ``bullets``,
    ``keywords``, ``layout``, ``assumption``, ``audio`` (absolute path to
    an mp3) and ``durationInFrames``. Audio is
    copied into ``video-service/public/jobs/<job_id>/`` so the composition
    can resolve it with ``staticFile``.
    """
    project = _project_dir()
    if not (project / "render.mjs").exists():
        raise RenderError(f"Remotion project not found at {project}")

    job_dir = project / "public" / "jobs" / str(job_id)
    if job_dir.exists():
        shutil.rmtree(job_dir)
    job_dir.mkdir(parents=True)

    scenes = []
    for i, scene in enumerate(props.get("scenes") or []):
        audio_src = Path(scene["audio"])
        audio_name = f"scene-{i}{audio_src.suffix or '.mp3'}"
        shutil.copyfile(audio_src, job_dir / audio_name)
        scenes.append({
            "title": scene.get("title") or f"Scene {i + 1}",
            "bullets": scene.get("bullets") or [],
            "keywords": scene.get("keywords") or [],
            "layout": scene.get("layout") or "definition",
            "visual": scene.get("visual") or "",
            "assumption": scene.get("assumption"),
            "audio": f"jobs/{job_id}/{audio_name}",
            "durationInFrames": int(scene["durationInFrames"]),
        })
    if not scenes:
        raise RenderError("no scenes to render")

    props_path = job_dir / "props.json"
    props_path.write_text(
        json.dumps({"fps": FPS, "scenes": scenes}, ensure_ascii=False),
        encoding="utf-8",
    )

    out_dir = _media_root() / "videos"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{job_id}.mp4"

    timeout = int(_env("RENDER_TIMEOUT_S", "300"))
    try:
        result = subprocess.run(
            ["node", "render.mjs", str(props_path), str(out_path)],
            cwd=project, capture_output=True, text=True, timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise RenderError("node is not installed or not on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise RenderError(f"render timed out after {timeout}s") from exc

    if result.returncode != 0 or not out_path.exists():
        detail = (result.stderr or result.stdout or "").strip()[-400:]
        raise RenderError(f"render failed (exit {result.returncode}): {detail}")
    return out_path
