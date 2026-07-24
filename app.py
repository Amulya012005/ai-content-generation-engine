import os
import uuid
import requests
from flask import Flask, request, jsonify, render_template
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")


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
        "model": "llama-3.1-8b-instant",
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


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/generate", methods=["POST"])
def generate():
    data = request.get_json()
    if not data or "product_name" not in data or "description" not in data:
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
        cur.execute("UPDATE jobs SET status = %s WHERE id = %s", ("failed", job_id))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"error": str(e), "job_id": job_id}), 500

    cur.close()
    conn.close()
    return jsonify({"job_id": job_id, "status": "completed"}), 201


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


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)