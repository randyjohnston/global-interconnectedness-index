"""Shared LLM and LangSmith configuration for agents."""

import os

from langchain_nvidia_ai_endpoints import ChatNVIDIA

from gii.config import settings


def configure_langsmith() -> None:
    """Set LangSmith env vars from settings if an API key is configured."""
    if settings.langsmith_api_key and settings.langsmith_tracing == "true":
        os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
        os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
        os.environ["LANGSMITH_TRACING"] = str(settings.langsmith_tracing)


def get_llm(**kwargs) -> ChatNVIDIA:
    """Build a ChatNVIDIA instance with default settings."""
    configure_langsmith()
    defaults = {
        "model": settings.llm_model,
        "api_key": settings.nvidia_api_key,
        "temperature": 0.6,
        "top_p": 0.95,
        "max_tokens": 32768,
        "max_retries": 3
    }
    defaults.update(kwargs)
    return ChatNVIDIA(**defaults)
