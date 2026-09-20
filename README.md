# SillyTree

SillyTree turns a course syllabus into an interactive knowledge map. Upload a
PDF or DOCX syllabus and the app extracts course topics, infers prerequisite
relationships, and lays everything out as a visual graph you can organize and
use for studying. Selected topics can also be turned into short narrated
explainer videos.

## Features

- Create separate course sandboxes and rename or delete them.
- Generate topics and prerequisite links from an uploaded syllabus.
- Add, edit, move, multi-select, and connect topics manually.
- Attach lecture notes or slides to one or more topics.
- Create tags such as `Exam 1` and filter the map by tag.
- Rate confidence in each topic and filter by confidence level.
- Focus the graph on selected topics and their prerequisites.
- Generate five-question study quizzes using topic, prerequisite, and uploaded
  document context.
- Generate narrated explainer videos for selected topics.

## Tech stack

- Python 3.10+
- Django 5.2
- SQLite
- Vanilla JavaScript, HTML, CSS, and SVG
- OpenAI API for topic extraction, prerequisite inference, quizzes, and video
  scripts
- Remotion (Node 18+) and edge-tts for explainer video generation

### Python libraries

All Python dependencies are pinned in `requirements.txt`.

| Library           |     Version | Purpose                                                                 |
| ----------------- | ----------: | ----------------------------------------------------------------------- |
| `Django`          |      5.2.17 | Web framework, ORM, routing, templates, forms, and development server.  |
| `openai`          |     1.109.1 | Sends syllabus-analysis and quiz-generation requests to the OpenAI API. |
| `pypdf`           |      6.19.0 | Extracts text from uploaded PDF syllabi and study materials.            |
| `python-dateutil` | 2.9.0.post0 | Parses and normalizes dates found in syllabus text.                     |
| `python-dotenv`   |       1.2.3 | Loads local environment variables from the `.env` file.                 |
| `asgiref`         |      3.12.1 | Provides Django's ASGI and async compatibility utilities.               |
| `sqlparse`        |       0.6.0 | Supports SQL parsing and formatting used by Django.                     |

### Frontend libraries and resources

| Library or resource                       | Version | Purpose                                                        |
| ----------------------------------------- | ------: | -------------------------------------------------------------- |
| [Lucide Icons](https://lucide.dev/)       | 0.468.0 | Supplies the interface icons and is loaded from the unpkg CDN. |
| [Google Fonts](https://fonts.google.com/) |  Hosted | Provides the Manrope and DM Mono typefaces.                    |

The interactive knowledge graph itself is implemented with native browser SVG
and JavaScript; it does not require a separate graph-rendering library.

## Local setup

Python 3.10 or newer is recommended.

1. Clone the repository and enter the project directory.

   ```bash
   git clone <repository-url>
   cd my_django_app
   ```

2. Create and activate a virtual environment.

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

   On Windows PowerShell, activate it with:

   ```powershell
   .venv\Scripts\Activate.ps1
   ```

3. Install the dependencies.

   ```bash
   pip install -r requirements.txt
   ```

4. Create a `.env` file in the project root.

   ```dotenv
   DJANGO_SECRET_KEY=replace-with-a-random-secret-key
   OPENAI_API_KEY=replace-with-your-openai-api-key
   ```

   Create or manage an OpenAI API key in the
   [OpenAI dashboard](https://platform.openai.com/api-keys). The application
   loads it on the Django server; it is never needed in the browser.

   | Variable             | Required        | Purpose                                                       |
   | -------------------- | --------------- | ------------------------------------------------------------- |
   | `DJANGO_SECRET_KEY`  | Yes             | Signs Django sessions and other protected data.               |
   | `OPENAI_API_KEY`     | For AI features | Authenticates syllabus analysis and quiz-generation requests. |
   | `OPENAI_GRAPH_MODEL` | No              | Overrides the model used to extract topics and prerequisites. |
   | `OPENAI_QUIZ_MODEL`  | No              | Overrides the model used to create topic quizzes.             |

   The default AI model is `gpt-4.1-mini`. You can override it independently
   for each feature:

   ```dotenv
   OPENAI_GRAPH_MODEL=gpt-4.1-mini
   OPENAI_QUIZ_MODEL=gpt-4.1-mini
   ```

   Keep `.env` out of version control, never paste a real key into this README,
   and never expose the key in frontend JavaScript. If a key is accidentally
   shared or committed, revoke it in the OpenAI dashboard and create a new one.

5. Set up the database and start the development server.

   ```bash
   python manage.py migrate
   python manage.py runserver
   ```

6. For video generation, also install the Remotion service (requires Node 18+).

   ```bash
   cd video-service
   npm install
   ```

7. Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in a browser.

## Using the app

1. Select **New sandbox** in the sidebar.
2. Open the add menu and upload a syllabus, or create a topic manually.
3. Explore the generated graph; click a topic to see its details.
4. Select topics to add tags, upload study materials, or create prerequisite
   connections.
5. Rate your confidence, filter the map, and generate quizzes as you study.
6. Select one or more topics and click **Generate video** to create a narrated
   explainer.

Uploads must be PDF or DOCX files no larger than 20 MB. Uploading a new
syllabus replaces the existing topics and prerequisite relationships in that
sandbox.

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

### Video env vars (see `.env.example`)

| Var | Purpose |
| --- | --- |
| `OPENAI_SCRIPT_MODEL` | default `gpt-4o-mini` |
| `EDGE_TTS_VOICE` | default `en-US-AriaNeural` |
| `EDGE_TTS_RATE` / `EDGE_TTS_PITCH` | default `+0%` / `+0Hz` |
| `RENDER_TIMEOUT_S` | default `300` |
| `REMOTION_PROJECT_DIR` | default `<repo>/video-service` |

## Run the tests

```bash
python manage.py test
```

The tests cover sandbox and topic operations, tags, uploads, graph generation,
confidence ratings, quiz responses, and the video pipeline. All external calls
(OpenAI, edge-tts, the node subprocess) are mocked in the test suite.

## Project structure

```text
my_django_app/
├── core/
│   ├── services/          # Syllabus parsing, graph building, quizzes, video
│   ├── static/core/       # Workspace styles and browser-side behavior
│   ├── templates/core/    # Main workspace page
│   ├── models.py          # Sandboxes, topics, edges, tags, and documents
│   ├── urls.py            # JSON API routes
│   └── views.py           # API handlers
├── video-service/         # Minimal Remotion project for video rendering
├── mysite/                # Django project configuration
├── media/                 # Local development uploads
├── manage.py
└── requirements.txt
```

## Notes

This project is optimized for a polished hackathon demo. It currently uses
local SQLite storage and Django's development media serving, so production
deployment would require hardened settings, durable file storage, and a
production web server.
