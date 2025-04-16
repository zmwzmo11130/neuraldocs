from pymongo import MongoClient
from redis import Redis
import chromadb
from chromadb.config import Settings as ChromaSettings

from config import settings

# MongoDB client
mongo_client = MongoClient(host=settings.mongo_host, port=settings.mongo_port)
db = mongo_client.articles_db

# Redis client for RQ (used by rq via connection URL)
redis_client = Redis(host=settings.redis_host, port=settings.redis_port)

# Chroma client
chroma_client = chromadb.HttpClient(
    host=settings.chroma_host,
    port=settings.chroma_port # HttpClient expects an int, ensure settings.chroma_port is int
)

collection = chroma_client.get_or_create_collection(name="articles")