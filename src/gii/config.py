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

    # LLM provider: "nvidia" or "bedrock"
    llm_provider: str = "nvidia"
    llm_model: str = "nvidia/llama-3.3-nemotron-super-49b-v1.5"

    # NVIDIA NIM
    nvidia_api_key: str = ""

    # AWS Bedrock
    bedrock_model_id: str = "us.anthropic.claude-sonnet-4-20250514-v1:0"
    bedrock_region: str = "us-east-1"

    # LangSmith observability
    langsmith_api_key: str = ""
    langsmith_project: str = "gii"
    langsmith_tracing: str = "true"

    # Index weights
    weight_trade: float = 0.40
    weight_travel: float = 0.30
    weight_geopolitics: float = 0.30

    # Tavily web search
    tavily_api_key: str = ""
    tavily_trade_domains: str = "tradingeconomics.com,wto.org,reuters.com,bloomberg.com,economist.com,ft.com"
    tavily_travel_domains: str = "iata.org,reuters.com,icao.int,skift.com,travelpulse.com,apnews.com,dw.com"
    tavily_geopolitics_domains: str = "foreignaffairs.com,reuters.com,bbc.com,aljazeera.com,apnews.com,dw.com"

    # Data
    data_dir: str = "data"


settings = Settings()
