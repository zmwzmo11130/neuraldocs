import json
import uuid

import httpx
import trafilatura
from openai import OpenAI
from rq import get_current_job
from sentence_transformers import SentenceTransformer

from db import db, collection
from config import settings

# Initialize embedding model and OpenAI client
embedding_model = SentenceTransformer(settings.embedding_model_name)
client = OpenAI(api_key=settings.openai_api_key)

def process_url(url: str):
    """
    Fetches the URL, extracts content, structures it with OpenAI, stores in MongoDB,
    generates embeddings, and stores vectors in ChromaDB.
    """
    job = get_current_job()
    try:
        response = httpx.get(url, timeout=30.0)
        response.raise_for_status()
        content = trafilatura.extract(response.text, url=url)
        if not content:
            raise ValueError("Failed to extract content")
    except Exception as e:
        return {"error": f"Fetch/Extract error: {e}"}

    # Structure content via OpenAI
    # Build a prompt that asks the model to structure the article into JSON
    prompt = f'''
You are to analyze the following article and output a JSON object with keys like title, author, date, and sections.
The sections key should be an object where each section has a heading and text.

Article URL: {url}
Article content:
"""{content}"""

Output only the JSON.
'''
    try:
        resp = client.chat.completions.create(
            model=settings.nano_model_name,
            messages=[
                {"role": "system", "content": "Structure the article into JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
        )
        structured = resp.choices[0].message.content
        data = json.loads(structured)
    except Exception:
        # Fallback to raw text
        data = {"text": content}

    # Store document in MongoDB
    doc = {"url": url, "data": data}
    result = db.documents.insert_one(doc)
    doc_id = str(result.inserted_id)

    # Prepare chunks for embedding
    chunks = []
    if "sections" in data and isinstance(data["sections"], dict):
        for key, section in data["sections"].items():
            text = section.get("text", "")
            chunks.append((key, text))
    elif "text" in data:
        chunks.append(("content", data.get("text", "")))

    # Generate embeddings and store in ChromaDB
    for key, text in chunks:
        if not text or not text.strip():
            continue
        embedding = embedding_model.encode(text).tolist()
        collection.add(
            embeddings=[embedding],
            metadatas=[{"mongo_id": doc_id, "chunk_key": key, "source_url": url}],
            ids=[str(uuid.uuid4())],
        )

    return {"status": "completed", "doc_id": doc_id}