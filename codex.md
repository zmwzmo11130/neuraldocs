**Let's Make a Plan for the Basic Web Article System:**

Okay, here's a plan focusing on the core functionality with the technologies discussed, designed for local Docker deployment and an API-first approach.

**1. Core Technologies:**

- **Language/Framework:** Python 3.x with FastAPI (for the API - fast, modern, async support, auto-docs).
- **Containerization:** Docker & Docker Compose (to manage all services).
- **Web Fetching:** `httpx` (modern async HTTP client) or `requests`.
- **Content Extraction:** `trafilatura` (good baseline for extracting main article content).
- **Preprocessing/Structuring:** OpenAI `gpt-4.1-nano` via their API (using the `openai` Python library).
- **Embedding Model:** `sentence-transformers` library (Python). Start with `all-MiniLM-L6-v2` (good balance of speed/quality, runs well locally). _Ensure MPS acceleration is enabled on M1 Max_.
- **Vector Database:** ChromaDB (runs well in Docker, simple API, persists to disk).
- **Content/Metadata Database:** MongoDB (runs well in Docker, good for storing the JSON output from nano and other metadata).
- **Background Task Queue:** Redis + RQ (Python `rq` library - simpler than Celery for this scale, handles background ingestion).

**2. Architecture & Docker Compose Setup (`docker-compose.yml`):**

Define these services:

- **`api`:**
  - Builds from your FastAPI application code.
  - Exposes a port (e.g., 8000).
  - Depends on `redis`, `mongodb`, `chromadb`.
  - Handles incoming HTTP requests for adding URLs and querying.
  - Enqueues ingestion tasks to Redis.
  - Performs query embedding, vector search, MongoDB lookup, and RAG LLM calls during querying.
- **`worker`:**
  - Builds from the same application code (or a specific worker entry point).
  - _Does not_ expose ports.
  - Depends on `redis`, `mongodb`, `chromadb`.
  - Runs the `rq` worker process, listening for tasks on the Redis queue.
  - Executes the ingestion pipeline (fetch, extract, preprocess via nano, embed via sentence-transformers, store in Mongo/Chroma).
  - Needs access to the OpenAI API key.
  - Needs the `sentence-transformers` model downloaded/cached within the container (or via a volume).
- **`mongodb`:**
  - Uses the official `mongo` image.
  - Mounts a volume for data persistence (`./mongo_data:/data/db`).
  - Exposes MongoDB port internally (e.g., 27017).
- **`chromadb`:**
  - Uses the official `chromadb/chroma` image.
  - Mounts a volume for data persistence (`./chroma_data:/chroma/chroma`).
  - Exposes ChromaDB port internally (e.g., 8001 or default).
- **`redis`:**
  - Uses the official `redis` image.
  - Used by `rq` for task queuing.

**3. Ingestion Flow (Handled by `worker`):**

1.  `api` receives `POST /add-url` request with `{ "url": "..." }`.
2.  `api` validates the URL and enqueues a task like `process_url(url)` to the Redis queue handled by `rq`.
3.  `worker` picks up the task.
4.  `worker`: Fetch URL content using `httpx`.
5.  `worker`: Extract main content using `trafilatura`. Handle potential errors.
6.  `worker`: Prepare prompt for `gpt-4.1-nano` asking it to structure the content into meaningful JSON blocks.
7.  `worker`: Call OpenAI API (`gpt-4.1-nano`). Handle potential errors (API errors, malformed JSON).
8.  `worker`: Parse the JSON response.
9.  `worker`: Store the entire structured JSON (or the raw text if nano fails) in MongoDB (e.g., in a `documents` collection). Get the MongoDB `_id`.
10. `worker`: Iterate through the text values (the chunks) in the JSON response.
11. `worker`: For each text chunk:
    - Generate embedding using local `sentence-transformers` model (leveraging MPS).
    - Store the vector in ChromaDB (e.g., in a collection named `articles`). Include metadata: `{ "mongo_id": "<mongodb_id>", "chunk_key": "<key_from_json>", "source_url": url }`.

**4. Query Flow (Handled by `api`):**

1.  `api` receives `POST /query` request with `{ "question": "..." }`.
2.  `api`: Generate embedding for the `question` using the _same_ local `sentence-transformers` model.
3.  `api`: Query ChromaDB's `articles` collection using the question embedding to find the top K (e.g., K=5) most similar chunks.
4.  `api`: Extract the `mongo_id` and `chunk_key` (or just the text if stored directly) from the ChromaDB results' metadata.
5.  `api`: Use the `mongo_id`s to fetch the corresponding original text chunks from MongoDB (looking up by ID and potentially key). _Deduplicate chunks if multiple come from the same document._
6.  `api`: Construct a prompt for the final answer synthesis LLM (can be `gpt-4.1-nano`, `gpt-4o-mini`, or another): Include the retrieved text chunks as context and the original user question.
7.  `api`: Call the chosen LLM API.
8.  `api`: Return the LLM's generated answer, potentially along with source URLs from the retrieved chunks' metadata. Response: `{ "answer": "...", "sources": ["url1", "url2"] }`.

**5. API Endpoints (FastAPI):**

- `POST /add-url` (accepts JSON body `{"url": "string"}`) -> Returns `{"message": "URL queued for processing", "task_id": "string"}`
- `POST /query` (accepts JSON body `{"question": "string"}`) -> Returns `{"answer": "string", "sources": ["list", "of", "urls"]}`
- _(Optional)_ `GET /documents` -> Returns a list of processed documents (e.g., URLs and titles fetched from MongoDB).
- _(Optional)_ `GET /tasks/{task_id}` -> Check status of an ingestion task via `rq`.

**6. Frontend (Bonus - Separate or Simple Integration):**

- A very simple HTML page served by FastAPI (using Jinja2 templates) or a separate static frontend (React/Vue/Svelte) served by another simple web server (like `nginx` in another container, or directly).
- Contains two forms: one for submitting a URL (`POST /add-url`), one for asking a question (`POST /query`).
- Uses JavaScript (`fetch` API) to interact with the FastAPI backend endpoints.
- Displays the results (processing confirmation, answers, sources).

**Key Considerations:**

- **API Keys:** Securely manage the OpenAI API key (e.g., via environment variables injected into the Docker containers).
- **Error Handling:** Implement robust error handling for network issues, website scraping failures, LLM API errors, malformed data, etc.
- **Configuration:** Make things like the embedding model name, ChromaDB collection name, top-K retrieval count, and LLM model used for RAG configurable.
- **Data Persistence:** Ensure the Docker volumes for MongoDB and ChromaDB are correctly configured to save data outside the containers.

This plan provides a solid foundation for your core idea, emphasizing local control, API-first design, and leveraging the specific technologies you're interested in. You can build this incrementally, starting with the core ingestion and query pipelines.
