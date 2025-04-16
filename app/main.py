from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from redis import Redis
from rq import Queue
from openai import OpenAI
from sentence_transformers import SentenceTransformer
from bson import ObjectId

from db import db, collection
from config import settings
from tasks import process_url

app = FastAPI(title="Web Article RAG API")

# Setup Redis and RQ
redis_conn = Redis(host=settings.redis_host, port=settings.redis_port)
queue = Queue(connection=redis_conn)

# Load embedding model and initialize OpenAI client
embedding_model = SentenceTransformer(settings.embedding_model_name)
client = OpenAI(api_key=settings.openai_api_key)

# Setup templates for simple frontend
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
def get_ui(request: Request):
    """Serve the single-page frontend."""
    return templates.TemplateResponse("index.html", {"request": request})

def obj_id(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except:
        raise HTTPException(status_code=400, detail=f"Invalid document ID: {id_str}")

class URLItem(BaseModel):
    url: str

class QueryItem(BaseModel):
    question: str
    top_k: int = settings.top_k

@app.post("/add-url")
def add_url(item: URLItem):
    job = queue.enqueue(process_url, item.url)
    return {"message": "URL queued for processing", "task_id": job.get_id()}

@app.get("/tasks/{task_id}")
def get_task(task_id: str):
    job = queue.fetch_job(task_id)
    if not job:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"task_id": task_id, "status": job.get_status(), "result": job.result}

@app.post("/query")
def query(item: QueryItem):
    # Embed question
    embedding = embedding_model.encode(item.question).tolist()
    # Query ChromaDB
    results = collection.query(
        query_embeddings=[embedding],
        n_results=item.top_k,
    )
    metadatas = results.get("metadatas", [[]])[0]

    seen = set()
    contexts = []
    sources = []
    for meta in metadatas:
        mongo_id = meta.get("mongo_id")
        chunk_key = meta.get("chunk_key")
        source_url = meta.get("source_url")
        if (mongo_id, chunk_key) in seen:
            continue
        seen.add((mongo_id, chunk_key))
        doc = db.documents.find_one({"_id": obj_id(mongo_id)})
        if not doc:
            continue
        data = doc.get("data", {})
        text = None
        if "sections" in data and isinstance(data["sections"], dict):
            section = data["sections"].get(chunk_key)
            if section:
                text = section.get("text")
        elif "text" in data and chunk_key == "content":
            text = data.get("text")
        if text:
            contexts.append(text)
            sources.append(source_url)

    # Prepare context for LLM
    context_str = "\n\n".join(contexts)
    prompt = (
        f"Use the following contexts to answer the question.\n{context_str}\n\n"
        f"Question: {item.question}\nAnswer:"
    )
    # Call LLM
    resp = client.chat.completions.create(
        model=settings.rag_model_name,
        messages=[
            {"role": "system", "content": "Answer based on context."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
    )
    answer = resp.choices[0].message.content
    return {"answer": answer, "sources": list(set(sources))}
 
@app.get("/documents")
def list_documents(page: int = 1):
    """List stored documents with pagination (100 per page)."""
    page_size = 100
    if page < 1:
        page = 1
    skip = (page - 1) * page_size
    total = db.documents.count_documents({})
    cursor = db.documents.find().sort([("_id", -1)]).skip(skip).limit(page_size)
    docs = []
    for doc in cursor:
        data = doc.get("data", {})
        title = data.get("title") if isinstance(data.get("title"), str) else None
        docs.append({"id": str(doc.get("_id")), "url": doc.get("url"), "title": title})
    return {"page": page, "page_size": page_size, "total": total, "documents": docs}
 
@app.get("/stats")
def get_stats():
    """Return basic system statistics: number of documents and vectors."""
    # Count documents in MongoDB
    doc_count = db.documents.count_documents({})
    # Count vectors in ChromaDB collection
    try:
        vector_count = collection.count()
    except Exception:
        # Fallback if count() not available
        vector_count = None
    return {"documents": doc_count, "vectors": vector_count}