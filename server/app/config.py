from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://user:password@localhost:5432/decidoctor"

    # Redis
    REDIS_URL: str = "redis://localhost:6379"

    # LLM API Keys
    ANTHROPIC_API_KEY: str = ""
    PERPLEXITY_API_KEY: str = ""

    # Models
    JUDGE_MODEL: str = "claude-haiku-4-5-20251001"
    PERSONA_MODEL: str = "claude-sonnet-4-6"
    SYNTHESIZER_MODEL: str = "claude-sonnet-4-6"

    # Perplexity / Grounding
    PERPLEXITY_MODEL: str = "sonar"
    PERPLEXITY_SEARCH_CONTEXT: str = "low"
    GROUNDING_TIMEOUT_SEC: int = 6
    GROUNDING_MAX_TOKENS: int = 1000

    # Session
    SESSION_TTL_SEC: int = 3600
    MAX_REQUESTION_COUNT: int = 3
    CONTEXT_WINDOW_TURNS: int = 5

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
