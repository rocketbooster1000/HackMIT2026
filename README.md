# EdTech Knowledge Map

Turns a course syllabus into an interactive knowledge map, with short
narrated video explainers generated for selected topics.

## Setup

```bash
python -m venv venv
venv/Scripts/activate           # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # fill in DJANGO_SECRET_KEY, OPENAI_API_KEY
python manage.py migrate
python manage.py runserver
```

For video generation, also install the Remotion service:

```bash
cd video-service
npm install                     # requires Node 18+
```

## Video pipeline

Selecting one or more topics on the map can trigger a narrated explainer
video:

1. `POST /api/videos/generate` with `{ "sandbox_id": N, "topic_ids": [...] }`
   creates a `VideoJob` and returns `{ "job_id", "status": "queued" }`
   immediately (202). Work runs on a background thread — no Celery needed.
2. `GET /api/videos/jobs/<id>/` polls status:
   `queued → generating_script → generating_audio → rendering → done|failed`.
   When `done`, `video_url` points at `/media/videos/<id>.mp4`.

Stages:

- **Script** (`core/services/script_writer.py`) — OpenAI strict JSON schema
  call producing `{ title, scenes: [{ title, narration, on_screen_text,
  visual, keywords: [{term, icon}], layout, assumption, duration_hint }] }`.
  `layout` is one of `definition`/`process`/`recap` and picks the scene
  variant; `keywords` drive icon chips (optional lucide icon name per
  term); `visual` is an advisory build description that is never shown;
  `assumption` flags simplifications as an on-screen footnote. Retries
  once on malformed output or transient API errors. Source material is
  topic name + description + tags, with prerequisite names for context.
  Multiple selected topics merge into one video.
- **Audio** (`core/services/tts.py`) — edge-tts per scene; real durations
  come from `WordBoundary` metadata, `duration_hint` is only a fallback.
- **Render** (`core/services/remotion_renderer.py`) — copies audio into
  `video-service/public/jobs/<id>/`, writes `props.json`, and invokes
  `node render.mjs` as a subprocess. `video-service/` is a minimal Remotion
  project (`Video` composition): per-scene layout variants with spring
  entrances, staggered bullets, keyword icon chips (lucide-react;
  LLM-suggested icon → keyword map → fallback), deterministic per-keyword
  accent colors for cross-video motif consistency, and an exit fade.

### Env vars (see `.env.example`)

| Var | Purpose |
| --- | --- |
| `OPENAI_API_KEY` | script generation (shared with graph builder) |
| `OPENAI_SCRIPT_MODEL` | default `gpt-4o-mini` |
| `EDGE_TTS_VOICE` | default `en-US-AriaNeural` |
| `EDGE_TTS_RATE` / `EDGE_TTS_PITCH` | default `+0%` / `+0Hz` |
| `RENDER_TIMEOUT_S` | default `300` |
| `REMOTION_PROJECT_DIR` | default `<repo>/video-service` |

## Tests

```bash
python manage.py test
```

All external calls (OpenAI, edge-tts, the node subprocess) are mocked.
