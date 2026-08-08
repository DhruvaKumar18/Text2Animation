# Text2Animation Studio

Text2Animation Studio is a production-ready Django web application that generates animated video storyboards based on text prompts. The project leverages **Django REST Framework (DRF)** for services APIs, **Celery** and **Redis** for distributed task queues, and **FFmpeg** to handle the heavy lifting of video clip rendering and stitching.

## Tech Stack Overview

- **Backend Framework**: Django 5.x (Python 3.12+)
- **API Engine**: Django REST Framework (DRF)
- **Task Orchestration**: Celery (with Redis broker)
- **Media Engine**: FFmpeg (via system-level commands) & Pillow (for image layouts)
- **Frontend Layer**: Bootstrap 5 (dark glassmorphism styling) & Vanilla JavaScript (polling/live update loops)
- **Database**: PostgreSQL (with automatic SQLite fallback for rapid local prototyping)

---

## File Structure

```text
t2v_7_8_26/
│
├── text2animation/           # Core Project Configuration
│   ├── settings.py           # Production-hardened settings
│   ├── urls.py               # Dispatcher URL mappings
│   ├── celery.py             # Celery App init
│   └── wsgi.py / asgi.py     # Server gateway adapters
│
├── stories/                  # Core Story and Scene database models
├── media_manager/            # Media assets indexing and utilities
├── history/                  # Pipeline execution logging and tracebacks
├── ai/                       # Mock service for text, images, and clips
├── ffmpeg_service/           # FFmpeg subprocess wrappers for stitching/subtitles
├── pipeline/                 # Background Celery orchestration tasks
├── api/                      # DRF Serializers, ViewSets, and routers
├── dashboard/                # Main UI Views & web dashboard
│
├── templates/                # Global HTML blueprints (base.html, dashboard pages)
├── static/                   # Global style sheets & JS overlays
│
├── requirements.txt          # Package dependencies listing
├── .env.example              # Environments template
└── manage.py                 # Django command manager
```

---

## Getting Started

### 1. Prerequisites

Ensure you have the following installed on your machine:
- **Python 3.12+**
- **Redis Server** (required as the Celery broker)
- **FFmpeg** (installed on your system path, so that `ffmpeg` and `ffprobe` are accessible via shell commands)
- **PostgreSQL** (Optional; by default, the app falls back to SQLite if no PostgreSQL URL is declared in `.env`).

### 2. Installation & Setup

1. **Clone/Open the workspace** and create a Python virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows, use: venv\Scripts\activate
   ```

2. **Install the dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables**:
   Copy the example environment file and update variables if necessary (e.g. database credentials or custom Redis URL):
   ```bash
   cp .env.example .env
   ```

4. **Run Migrations**:
   Create the database schema:
   ```bash
   python manage.py makemigrations
   python manage.py migrate
   ```

5. **Collect Static Files**:
   Gather static resources for deployment or serving:
   ```bash
   python manage.py collectstatic --noinput
   ```

---

## Running the Application

To run the complete system, you need to start both the Django web server and the Celery worker process.

### Step A: Start the Django Development Server
Launch the main web console interface:
```bash
python manage.py runserver
```
The dashboard will be available at [http://127.0.0.1:8000/](http://127.0.0.1:8000/).

### Step B: Start the Celery Worker Process
Open a second terminal window, activate your virtual environment, and run:
```bash
celery -A text2animation worker --loglevel=info
```
On Windows machines, if you encounter task execution issues, you can run Celery in solo pool mode:
```bash
celery -A text2animation worker --loglevel=info -P solo
```

---

## API Endpoints

The API is fully open and unauthenticated as per standard requirements:
- **List Stories**: `GET /api/stories/`
- **Create Animation Task**: `POST /api/stories/` (Body: `{ "title": "Optional Title", "prompt": "Your descriptive prompt" }`)
- **Get Story Details (with scenes & logs)**: `GET /api/stories/<id>/`
- **Re-trigger / Retry Pipeline**: `POST /api/stories/<id>/retry/`
