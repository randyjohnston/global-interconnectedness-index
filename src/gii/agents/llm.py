"""Shared LLM and LangSmith configuration for agents."""

import logging
import os
import re

from langchain_nvidia_ai_endpoints import ChatNVIDIA
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from gii.config import settings

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS_CODES = re.compile(r"\b(502|503|429)\b")


def _is_retryable(exc: BaseException) -> bool:
    """Return True for HTTP 502, 503, and 429 errors."""
    return bool(_RETRYABLE_STATUS_CODES.search(str(exc)))


_retry_decorator = retry(
    retry=retry_if_exception(_is_retryable),
    wait=wait_exponential_jitter(initial=2, max=30),
    stop=stop_after_attempt(5),
    before_sleep=lambda rs: logger.warning(
        f"NVIDIA API retryable error (attempt {rs.attempt_number}), retrying: {rs.outcome.exception()}"
    ),
)


class RetryingChatNVIDIA(ChatNVIDIA):
    """ChatNVIDIA with automatic retries on 502, 503, and 429 responses."""

    def _generate(self, *args, **kwargs):
        return _retry_decorator(super()._generate)(*args, **kwargs)

    async def _agenerate(self, *args, **kwargs):
        return await _retry_decorator(super()._agenerate)(*args, **kwargs)


def configure_langsmith() -> None:
    """Set LangSmith env vars from settings if an API key is configured."""
    if settings.langsmith_api_key and settings.langsmith_tracing == "true":
        os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
        os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
        os.environ["LANGSMITH_TRACING"] = str(settings.langsmith_tracing)


def get_llm(**kwargs) -> RetryingChatNVIDIA:
    """Build a ChatNVIDIA instance with default settings and retry logic."""
    configure_langsmith()
    defaults = {
        "model": settings.llm_model,
        "api_key": settings.nvidia_api_key,
        "temperature": 0.6,
        "top_p": 0.95,
        "max_tokens": 32768,
    }
    defaults.update(kwargs)
    return RetryingChatNVIDIA(**defaults)
