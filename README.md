# SillyTree

SillyTree turns a course syllabus into an interactive knowledge map. Upload a
PDF or DOCX syllabus and the app extracts course topics, infers prerequisite
relationships, and lays everything out as a visual graph you can organize and
use for studying.

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

## Tech stack

- Python 3.10+
- Django 5.2
- SQLite
- Vanilla JavaScript, HTML, CSS, and SVG
- OpenAI API for topic extraction, prerequisite inference, and quizzes

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

6. Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in a browser.

## Using the app

1. Select **New sandbox** in the sidebar.
2. Open the add menu and upload a syllabus, or create a topic manually.
3. Explore the generated graph; click a topic to see its details.
4. Select topics to add tags, upload study materials, or create prerequisite
   connections.
5. Rate your confidence, filter the map, and generate quizzes as you study.

Uploads must be PDF or DOCX files no larger than 20 MB. Uploading a new
syllabus replaces the existing topics and prerequisite relationships in that
sandbox.

## Run the tests

```bash
python manage.py test
```

The tests cover sandbox and topic operations, tags, uploads, graph generation,
confidence ratings, and quiz responses. Calls to the OpenAI API are mocked in
the test suite.

## Project structure

```text
my_django_app/
├── core/
│   ├── services/          # Syllabus parsing, graph building, and quizzes
│   ├── static/core/       # Workspace styles and browser-side behavior
│   ├── templates/core/    # Main workspace page
│   ├── models.py          # Sandboxes, topics, edges, tags, and documents
│   ├── urls.py            # JSON API routes
│   └── views.py           # API handlers
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
