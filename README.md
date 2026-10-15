# ProductPix: AI Product Image Generator

![CI](https://github.com/Amulya012005/ai-content-generation-engine/actions/workflows/ci.yml/badge.svg)

A backend service that turns a product description into an image-generation prompt with an LLM, then into a product image. Jobs run asynchronously, so other software can submit work and poll for results.

**Live demo:** https://ai-content-generation-engine.onrender.com
*(Hosted on Render's free tier, so the first load after idle can take up to a minute.)*

![ProductPix screenshot](docs/screenshot.png)

## What it does

1. You send a product name and a short description.
2. The API saves a job as `pending` and returns immediately.
3. A background worker calls the Groq LLM to write an image prompt, then builds the image from it.
4. The job moves `pending` → `processing` → `completed` (or `failed`, with the error stored).
5. You poll the job to get the prompt and image.

## Architecture

```mermaid
flowchart LR
    A[Browser / API client] -->|POST /generate| B[Flask API]
    B -->|insert pending job| C[(PostgreSQL)]
    B -->|submit| D[Background worker pool]
    D -->|write prompt| E[Groq LLM API]
    D -->|build image URL| F[Pollinations.ai]
    D -->|update status + result| C
    A -->|GET /jobs/:id| B
    B -->|read job| C
```

## API

| Method | Endpoint | Description |
|---|---|---|
| POST | `/generate` | Submit a job. Returns `202` with `job_id`. |
| GET | `/jobs/<id>` | Get one job: status, prompt, image URL, error. |
| GET | `/jobs` | List all jobs. |
| GET | `/health` | Health check. |

```bash
curl -X POST http://localhost:5000/generate \
  -H "Content-Type: application/json" \
  -d '{"product_name":"Mug","description":"Blue ceramic coffee mug"}'
# {"job_id":"...","status":"pending"}

curl http://localhost:5000/jobs/<job_id>
```

## Reliability and safety

- **Async jobs:** a thread pool processes jobs so requests don't block on the LLM.
- **Failure handling:** failed jobs are marked `failed` and the error is saved.
- **Rate limiting:** 5 requests per minute and 50 per day per IP on `/generate`.
- **Input validation:** type and length checks on the server (name up to 120 chars, description up to 600).
- **Safe rendering:** the UI inserts user text as plain text, never as HTML.
- **Configurable model:** the LLM model is set with an environment variable, so a retired model is a config change, not a code change.

## Tech stack

Python, Flask, PostgreSQL (psycopg2), Groq API, Flask-Limiter, pytest, Docker, GitHub Actions, Render.

## Run locally

```bash
git clone https://github.com/Amulya012005/ai-content-generation-engine.git
cd ai-content-generation-engine
python -m venv venv
venv\Scripts\activate        # Windows (use: source venv/bin/activate on Mac/Linux)
pip install -r requirements-dev.txt
```

Create a `.env` file:

```
DATABASE_URL=postgresql://user:password@localhost:5432/yourdb
GROQ_API_KEY=your_key_here
GROQ_MODEL=openai/gpt-oss-20b   # optional
```

Then:

```bash
python app.py        # http://localhost:5000
python -m pytest -q  # run the tests
```

Or with Docker:

```bash
docker build -t productpix .
docker run --env-file .env -p 5000:5000 productpix
```

## Tests and CI

pytest covers validation, the health check and the rate limit. GitHub Actions runs the tests and builds the Docker image on every push.

## Known limitations and next steps

- The rate limiter and job pool live in memory: they reset on restart and wouldn't be shared across multiple servers. Next step: Redis and a real job queue (Celery or RQ).
- A job running during a server restart is lost. A persistent queue would fix this.
- Images come from the free Pollinations.ai API, which can be slow or rate-limited.
- Add a batch endpoint for submitting many products at once.