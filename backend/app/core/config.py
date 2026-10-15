from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api"
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ]

    # Relational/Metadata storage governed strictly via Alembic
    DATABASE_URL: str = "sqlite:///./orgatlas.db"

    # FalkorDB Knowledge Graph configuration
    FALKORDB_HOST: str = "localhost"
    FALKORDB_PORT: int = 6379
    FALKORDB_USERNAME: Optional[str] = None
    FALKORDB_PASSWORD: Optional[str] = None
    FALKORDB_GRAPH_NAME: str = "orgatlas_dev"

    # Nebius LLM inference configuration (OpenAI-compatible)
    NEBIUS_API_KEY: Optional[str] = None
    NEBIUS_API_BASE_URL: str = "https://api.studio.nebius.ai/v1"
    NEBIUS_MODEL_NAME: str = "meta-llama/Meta-Llama-3.1-70B-Instruct"

    # MCP context server security
    MCP_API_TOKEN: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
