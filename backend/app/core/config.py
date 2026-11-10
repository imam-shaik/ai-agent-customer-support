"""Environment-based application configuration.

Rules:
- No hardcoded secrets; values come from the environment / .env.
- LLM_PROVIDER defaults to the real NVIDIA endpoint; NVIDIA_API_KEY is
  not required to START the service (chat returns an explicit 503 until
  a key is configured). The deterministic stub is reachable when
  ENVIRONMENT=testing or when the explicit local Demo mode is selected
  (Demo is refused in production).
"""

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- application ---
    app_name: str = "Vilasat AI Support Intelligence API"
    environment: str = "development"
    debug: bool = False
    log_level: str = "INFO"

    # --- data ---
    # Phase 7: PostgreSQL + pgvector is REQUIRED — semantic search needs the
    # native `vector` type, so SQLite is no longer supported. Start the local
    # development cluster (no Docker needed) with:
    #     python scripts/dev_db.py start
    database_url: str = "postgresql+psycopg://postgres@127.0.0.1:54329/vilasat"

    # --- CORS (comma-separated list, no wildcard) ---
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # --- LLM (Phase 8A) ---
    # Provider selection: "nvidia" (default) = real OpenAI-compatible chat
    # endpoint (requires NVIDIA_API_KEY); "stub" = deterministic TEST
    # generator, reachable only when ENVIRONMENT=testing.
    # The LLM provider and the embedding provider are SEPARATE logical
    # components even though both default to the NVIDIA endpoint/key —
    # either can be moved to another provider without touching the other.
    # Model note: verified working with the strict-JSON contract and
    # DETERMINISTIC at temperature 0.0 (3/3 identical across all four task
    # prompts). Known-bad: deepseek-ai/deepseek-v4.1-flash (listed by
    # /models but inference hangs indefinitely, verified 2026-11-10);
    # meta/llama-3.3-70b-instruct (EOL, HTTP 410);
    # nvidia/nemotron-3.5-super-vl-120b-a12b (a reasoning model — samples
    # its chain-of-thought even at temperature 0.0, so identical questions
    # get different assessments, and reasoning_tokens eat the budget).
    llm_provider: str = "nvidia"
    llm_model: str = "nvidia/nemotron-3.5-bolt-e4b"
    llm_base_url: str = "https://integrate.api.nvidia.com/v1"
    # May equal EMBEDDING_API_KEY when the NVIDIA account serves both
    # services — but it is read by the LLM provider only.
    nvidia_api_key: str | None = None  # never committed, never logged
    llm_timeout_seconds: float = 60.0
    # Grounded structured output wants determinism: 0.0 by default.
    llm_temperature: float = 0.0
    # The endpoint caps max_tokens at 4096 (documented ChatRequest schema).
    # Default to the FULL budget: reasoning models (nemotron-3.5-super)
    # count their reasoning_tokens against this cap, and a smaller value
    # truncates real answers ("LLM response was truncated" → 503).
    llm_max_completion_tokens: int = 4096
    # Evidence controls for the prompt (explicit, no unlimited context):
    # 5 == retrieval top-k default; 5 x 1200 chars ≈ 2.5k tokens — far
    # below the model's 128k window, deliberately conservative.
    llm_max_evidence: int = 5
    llm_evidence_max_chars: int = 1200

    # --- Agent decision layer (Phase 8B) ---
    # Signal A (relevance gate): the best retrieved candidate's cosine
    # similarity must reach this bar before evidence counts as relevant.
    # Permissive by design for LIVE embeddings: nemotron-3-embed-1b scores
    # on-topic and unrelated pairs similarly high, so the cosine bar alone
    # cannot separate them — the coverage gate (signal B) and the support
    # check carry the protection. Re-tune from a labelled live evaluation
    # set; do not raise this blind or on-topic evidence gets rejected.
    agent_min_evidence_relevance: float = 0.05
    # Signal B (coverage gate): fraction of the question's material words
    # that must appear in the retrieved evidence. 0.75 is conservative:
    # it fails "cancel + refund" questions whose refund half is uncovered
    # BEFORE any answer is generated (false-uncertain over false-answer).
    agent_min_coverage_ratio: float = 0.75
    # Bounded conversation context (§14): the last N messages, each
    # truncated, are the ONLY history that ever reaches a prompt.
    agent_context_max_messages: int = 6
    agent_context_max_chars: int = 500

    # --- Embeddings (Phase 7) ---
    # Provider selection: "nvidia" = real OpenAI-compatible endpoint,
    # "fake" = deterministic test provider REJECTED unless ENVIRONMENT=testing
    # (fake embeddings must never serve real traffic).
    # Model note: the original choice (nvidia/nv-embedqa-e5-v5) reached
    # end-of-life on NVIDIA's API (HTTP 410, verified 2026-11-10); the
    # replacement serves the same purpose at 2048 dimensions.
    embedding_provider: str = "nvidia"
    embedding_model: str = "nvidia/nemotron-3-embed-1b"
    embedding_base_url: str = "https://integrate.api.nvidia.com/v1"
    embedding_api_key: str | None = None  # never committed, never logged
    # Role prefixes for models that need them (E5 family). The default
    # model (nvidia/nemotron-3-embed-1b) is SYMMETRIC and needs NONE —
    # both stay empty. Configurable so a future E5-style model can set
    # them. Omitting/adding them wrongly degrades retrieval accuracy.
    embedding_query_prefix: str = ""
    embedding_passage_prefix: str = ""
    # Must equal the pgvector column dimension (schema: vector(2048)) AND the
    # real model's output dimension — validated at indexing/retrieval time.
    embedding_dimensions: int = 2048
    embedding_timeout_seconds: float = 30.0
    # Chunks per embedding request — conservative for hosted rate limits.
    embedding_batch_size: int = 16

    # --- Retrieval (Phase 7) ---
    # Retrieval returns possible evidence only; it never decides sufficiency.
    retrieval_top_k_default: int = 5
    retrieval_top_k_max: int = 20
    retrieval_max_query_chars: int = 2000
    # E5 cosine similarities cluster around 0.7–1.0 (training temperature),
    # so 0.0 (no cutoff) is the honest default. A non-zero value only trims
    # obviously irrelevant results — it is NOT an evidence-sufficiency test.
    retrieval_min_cosine_similarity: float = 0.0

    # --- Knowledge ingestion (Phase 6) ---
    # Upload ceiling for one document (UTF-8 bytes). Small help articles
    # only — this is not a file-sharing service.
    max_document_bytes: int = 1_000_000
    # Chunking defaults (characters). 1200 ≈ 200–300 tokens: small enough
    # for precise retrieval, large enough to stay self-contained.
    chunk_max_chars: int = 1200
    # Overlap applies ONLY when a single oversized paragraph must be split
    # at sentence boundaries (see ingestion/pipeline.py).
    chunk_overlap_chars: int = 120

    # --- Staff authentication (Phase 11) ---
    # How long a staff bearer token stays valid after sign-in. Verified
    # server-side on every request; expired sessions are deleted, never
    # honored.
    auth_session_ttl_days: int = 7

    @field_validator("cors_origins", mode="after")
    @classmethod
    def _strip_origins(cls, value: str) -> str:
        if "*" in value:
            raise ValueError("Wildcard CORS origins are not allowed")
        return value

    @field_validator("chunk_overlap_chars", mode="after")
    @classmethod
    def _validate_overlap(cls, value: int, info) -> int:
        max_chars = info.data.get("chunk_max_chars", 1200)
        if value < 0 or value >= max_chars:
            raise ValueError("chunk_overlap_chars must be >= 0 and < chunk_max_chars")
        return value

    @field_validator("database_url", mode="after")
    @classmethod
    def _require_postgres(cls, value: str) -> str:
        if not value.startswith("postgresql"):
            raise ValueError(
                "Phase 7 requires PostgreSQL + pgvector: DATABASE_URL must start "
                "with 'postgresql' (local dev: python scripts/dev_db.py start)"
            )
        return value

    @field_validator("embedding_dimensions", mode="after")
    @classmethod
    def _validate_dimensions(cls, value: int) -> int:
        if value < 1:
            raise ValueError("embedding_dimensions must be >= 1")
        return value

    @field_validator("embedding_batch_size", mode="after")
    @classmethod
    def _validate_batch_size(cls, value: int) -> int:
        if value < 1:
            raise ValueError("embedding_batch_size must be >= 1")
        return value

    @field_validator("retrieval_min_cosine_similarity", mode="after")
    @classmethod
    def _validate_threshold(cls, value: float) -> float:
        if not -1.0 <= value <= 1.0:
            raise ValueError("retrieval_min_cosine_similarity must be within [-1, 1]")
        return value

    @field_validator("retrieval_top_k_default", mode="after")
    @classmethod
    def _validate_top_k_default(cls, value: int, info) -> int:
        max_k = info.data.get("retrieval_top_k_max", 20)
        if value < 1 or value > max_k:
            raise ValueError("retrieval_top_k_default must be within [1, retrieval_top_k_max]")
        return value

    @field_validator("llm_provider", mode="after")
    @classmethod
    def _validate_llm_provider(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"stub", "nvidia"}:
            raise ValueError(
                f"LLM_PROVIDER must be 'stub' or 'nvidia', got {value!r}"
            )
        return normalized

    @field_validator("llm_temperature", mode="after")
    @classmethod
    def _validate_temperature(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("llm_temperature must be within [0, 1]")
        return value

    @field_validator("llm_max_completion_tokens", mode="after")
    @classmethod
    def _validate_completion_tokens(cls, value: int) -> int:
        if not 1 <= value <= 4096:
            raise ValueError(
                "llm_max_completion_tokens must be within [1, 4096] "
                "(the endpoint's documented maximum)"
            )
        return value

    @field_validator("llm_max_evidence", mode="after")
    @classmethod
    def _validate_max_evidence(cls, value: int) -> int:
        if value < 1:
            raise ValueError("llm_max_evidence must be >= 1")
        return value

    @field_validator("llm_evidence_max_chars", mode="after")
    @classmethod
    def _validate_evidence_chars(cls, value: int) -> int:
        if value < 200:
            raise ValueError("llm_evidence_max_chars must be >= 200")
        return value

    @field_validator("agent_min_evidence_relevance", mode="after")
    @classmethod
    def _validate_agent_relevance(cls, value: float) -> float:
        if not -1.0 <= value <= 1.0:
            raise ValueError("agent_min_evidence_relevance must be within [-1, 1]")
        return value

    @field_validator("agent_min_coverage_ratio", mode="after")
    @classmethod
    def _validate_agent_coverage(cls, value: float) -> float:
        if not 0.0 < value <= 1.0:
            raise ValueError("agent_min_coverage_ratio must be within (0, 1]")
        return value

    @field_validator("agent_context_max_messages", mode="after")
    @classmethod
    def _validate_context_messages(cls, value: int) -> int:
        if value < 2:
            raise ValueError("agent_context_max_messages must be >= 2")
        return value

    @field_validator("agent_context_max_chars", mode="after")
    @classmethod
    def _validate_context_chars(cls, value: int) -> int:
        if value < 100:
            raise ValueError("agent_context_max_chars must be >= 100")
        return value

    @field_validator("auth_session_ttl_days", mode="after")
    @classmethod
    def _validate_session_ttl(cls, value: int) -> int:
        if not 1 <= value <= 90:
            raise ValueError("auth_session_ttl_days must be within [1, 90]")
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
