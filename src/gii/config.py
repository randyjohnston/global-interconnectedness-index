from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "GII_", "env_file": ".env", "extra": "ignore"}

    # Supabase Postgres
    database_url: str = "postgresql+psycopg://postgres.wlkioilaxtygtqvdgdjh@aws-1-us-west-2.pooler.supabase.com:5432/postgres"

    # Temporal
    temporal_host: str = "localhost:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "gii-pipeline"

    # UN Comtrade
    comtrade_api_key: str = ""
    comtrade_base_url: str = "https://comtradeapi.un.org/data/v1/get"

    # Google Cloud / GDELT
    gcp_project_id: str = ""
    gcp_credentials_path: str = ""
    gdelt_dataset: str = "gdelt-bq.gdeltv2"

    # NVIDIA AI
    nvidia_api_key: str = ""
    llm_model: str = "minimaxai/minimax-m2.7"

    # Index weights
    weight_trade: float = 0.40
    weight_travel: float = 0.30
    weight_geopolitics: float = 0.30

    # Data
    data_dir: str = "data"


settings = Settings()
