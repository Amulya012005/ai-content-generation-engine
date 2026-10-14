import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import requests
from flask import Flask, request, jsonify, render_template
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Background workers so /generate returns immediately and jobs run asynchronously
executor = ThreadPoolExecutor(max_workers=4)

DATABASE_URL = os.environ.get("DATABASE_URL")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b")


def get_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id UUID PRIMARY KEY,
            product_name TEXT NOT NULL,
            description TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            prompt TEXT,
            image_url TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    # Stores the failure reason when a job fails
    cur.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS error TEXT")
    conn.commit()
    cur.close()
    conn.close()


def generate_prompt_with_llm(product_name, description):
    """Call Groq (LLM) to turn product info into an image-generation prompt."""
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "You turn product info into a short, vivid image-generation prompt for a text-to-image model. Return ONLY the prompt, nothing else."
            },
            {
                "role": "user",
                "content": f"Product: {product_name}\nDescription: {description}"
            }
        ],
        "temperature": 0.7
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


def generate_image_mock(prompt):
    """
    Mocked image generation - returns a placeholder image.
    (Assignment explicitly allows mocking this step.)
    """
    seed = abs(hash(prompt)) % 1000
    return f"https://picsum.photos/seed/{seed}/512/512"


def process_job(job_id, product_name, description):
    """Runs in a background thread: pending -> processing -> completed/failed."""
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE jobs SET status = %s WHERE id = %s", ("processing", job_id))
        conn.commit()

        prompt = generate_prompt_with_llm(product_name, description)
        image_url = generate_image_mock(prompt)

        cur.execute(
            "UPDATE jobs SET status = %s, prompt = %s, image_url = %s WHERE id = %s",
            ("completed", prompt, image_url, job_id)
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        cur.execute(
            "UPDATE jobs SET status = %s, error = %s WHERE id = %s",
            ("failed", str(e), job_id)
        )
        conn.commit()
    finally:
        cur.close()
        conn.close()


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/generate", methods=["POST"])
def generate():
    data = request.get_json(silent=True)
    if not data or not data.get("product_name") or not data.get("description"):
        return jsonify({"error": "product_name and description are required"}), 400

    product_name = data["product_name"]
    description = data["description"]
    job_id = str(uuid.uuid4())

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO jobs (id, product_name, description, status) VALUES (%s, %s, %s, %s)",
        (job_id, product_name, description, "pending")
    )
    conn.commit()
    cur.close()
    conn.close()

    # Hand the work to a background thread and respond right away
    executor.submit(process_job, job_id, product_name, description)

    return jsonify({"job_id": job_id, "status": "pending"}), 202


@app.route("/jobs/<job_id>", methods=["GET"])
def get_job(job_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM jobs WHERE id = %s", (job_id,))
    job = cur.fetchone()
    cur.close()
    conn.close()

    if not job:
        return jsonify({"error": "job not found"}), 404
    return jsonify(dict(job)), 200


@app.route("/jobs", methods=["GET"])
def list_jobs():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM jobs ORDER BY created_at DESC")
    jobs = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify([dict(j) for j in jobs]), 200


@app.route("/")
def index():
    return render_template("index.html")


# Create the table when the app starts (works locally and on Render)
init_db()

if __name__ == "__main__":
    app.run(port=5000)