from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    app_name: str = "Nexus ERP Integration Platform"
    app_env: str = Field("development", validation_alias="APP_ENV")
    debug: bool = Field(False, validation_alias="DEBUG")
    secret_key: str = Field("dev-secret-change-me", validation_alias="SECRET_KEY")
    cors_origins: str = Field("http://localhost:3000", validation_alias="CORS_ORIGINS")

    # Database
    postgres_host: str = Field("localhost", validation_alias="POSTGRES_HOST")
    postgres_port: int = Field(5432, validation_alias="POSTGRES_PORT")
    postgres_user: str = Field("nexus", validation_alias="POSTGRES_USER")
    postgres_password: str = Field("nexus_dev_password", validation_alias="POSTGRES_PASSWORD")
    postgres_db: str = Field("nexus_erp", validation_alias="POSTGRES_DB")

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_sync(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # Redis
    redis_url: str = Field("redis://localhost:6379/0", validation_alias="REDIS_URL")

    # Kafka
    kafka_bootstrap_servers: str = Field("localhost:29092", validation_alias="KAFKA_BOOTSTRAP_SERVERS")
    kafka_connect_url: str = Field("http://localhost:8083", validation_alias="KAFKA_CONNECT_URL")
    kafka_schema_registry_url: str = Field("http://localhost:8081", validation_alias="SCHEMA_REGISTRY_URL")

    # LLM
    anthropic_api_key: str = Field("", validation_alias="ANTHROPIC_API_KEY")
    llm_model: str = Field("claude-opus-4-5-20251101", validation_alias="LLM_MODEL")

    # Encryption
    fernet_key: str = Field("", validation_alias="FERNET_KEY")

    # Celery
    celery_broker_url: str = Field("redis://localhost:6379/1", validation_alias="CELERY_BROKER_URL")
    celery_result_backend: str = Field("redis://localhost:6379/2", validation_alias="CELERY_RESULT_BACKEND")

    # NAM (Neural Addressed Memory) - semantic storage layer
    nam_query_url: str = Field("http://localhost:8010", validation_alias="NAM_QUERY_URL")
    nam_encoder_url: str = Field("http://localhost:8011", validation_alias="NAM_ENCODER_URL")

    # NNLM (multi-agent retrieval + synthesis layer on top of NAM)
    nnlm_encoder_url: str = Field("http://localhost:8001", validation_alias="NNLM_ENCODER_URL")
    nnlm_decoder_url: str = Field("http://localhost:8002", validation_alias="NNLM_DECODER_URL")

    # Feature flags
    enable_cdc: bool = Field(True, validation_alias="ENABLE_CDC")
    enable_agent: bool = Field(True, validation_alias="ENABLE_AGENT")
    enable_nnlm: bool = Field(True, validation_alias="ENABLE_NNLM")
    human_in_loop_required: bool = Field(True, validation_alias="HUMAN_IN_LOOP_REQUIRED")

    model_config = {"env_file": ".env", "case_sensitive": False, "extra": "ignore"}


settings = Settings()
