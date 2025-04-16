from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    mongo_host: str = "mongodb"
    mongo_port: int = 27017
    redis_host: str = "redis"
    redis_port: int = 6379
    chroma_host: str = "chromadb"
    chroma_port: int = 8000
    openai_api_key: str
    embedding_model_name: str = "all-MiniLM-L6-v2"
    nano_model_name: str = "gpt-4.1-nano"
    rag_model_name: str = "gpt-4.1-nano"
    top_k: int = 5

    class Config:
        env_file = ".env"


settings = Settings()