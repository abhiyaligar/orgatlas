from pathlib import Path
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent

# Resolved by absolute path so the service behaves the same whether it is
# started from the repository root or from backend/.
ENV_FILES = (str(REPO_ROOT / ".env"), str(BACKEND_DIR / ".env"))


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

# Answer synthesis. On by default so /ask is model-written; set false to
    # answer from retrieved graph facts only. Tests disable it so the suite
    # never depends on a reachable or billable provider.
    ASK_SYNTHESIS_ENABLED: bool = True
    # Generous because a reasoning model on a multi-source evidence package
    # exceeds shorter limits and returns an empty completion.
    ASK_SYNTHESIS_TIMEOUT_SECONDS: int = 45

    # Nebius LLM inference configuration (OpenAI-compatible)
    # Used only as a fallback for files whose authors wrote no usable
    # documentation. It is never called from the E2B sandbox, which receives no
    # provider credentials.
    NEBIUS_API_KEY: Optional[str] = None
    NEBIUS_API_BASE_URL: str = "https://api.studio.nebius.ai/v1"
    NEBIUS_MODEL_NAME: str = "zai-org/GLM-5.3-Flash"

    # MCP context server security
    MCP_API_TOKEN: Optional[str] = None

    # --- Slack (optional) ---------------------------------------------------
    # Socket Mode is used rather than an Events API webhook because it opens an
    # outbound connection. A developer can therefore run the bot from a laptop
    # with no public URL and no inbound firewall rule, which is the same reason
    # the MCP HTTP route is development-only.
    SLACK_BOT_TOKEN: Optional[str] = None
    SLACK_APP_TOKEN: Optional[str] = None
    # Channels the bot will answer in. Empty means it stays silent everywhere,
    # which is the safe default: a bot added to a workspace should not start
    # talking until someone has said where it is allowed to.
    SLACK_ALLOWED_CHANNELS: str = ""
    # A question longer than this is not a question, it is a paste.
    SLACK_MAX_QUESTION_CHARS: int = 800

    # Track A: repository ingestion via isolated E2B sandbox workers.
    # The sandbox clones and parses only; it never receives database or
    # model-provider credentials.
    # Every Track A value is supplied by the environment. None are defaulted
    # here, so a missing setting surfaces as None instead of a silent fallback.
    E2B_API_KEY: Optional[str] = None
    E2B_INGEST_TEMPLATE: Optional[str] = None
    E2B_SANDBOX_TIMEOUT: Optional[int] = None
    INGEST_COMMIT_DEPTH: Optional[int] = None
    INGEST_CACHE_DIR: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
