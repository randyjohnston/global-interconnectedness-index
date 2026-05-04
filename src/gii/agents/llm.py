"""Shared LLM and LangSmith configuration for agents."""

import logging
import os
import re

from langchain_core.language_models.chat_models import BaseChatModel
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
        f"LLM API retryable error (attempt {rs.attempt_number}), retrying: {rs.outcome.exception()}"
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


def _build_nvidia(**kwargs) -> RetryingChatNVIDIA:
    kwargs.pop("streaming", None)  # NVIDIA always streams; ignore flag
    defaults = {
        "model": settings.llm_model,
        "api_key": settings.nvidia_api_key,
        "temperature": 0.6,
        "top_p": 0.95,
        "max_tokens": 32768,
    }
    defaults.update(kwargs)
    return RetryingChatNVIDIA(**defaults)


def _build_bedrock(**kwargs) -> BaseChatModel:
    from langchain_aws import ChatBedrockConverse

    # Map streaming=True/False to ChatBedrockConverse's disable_streaming flag
    streaming = kwargs.pop("streaming", False)

    defaults = {
        "model_id": settings.bedrock_model_id,
        "region_name": settings.bedrock_region,
        "temperature": 0.3,
        "max_tokens": 32768,
        "disable_streaming": not streaming,
    }
    defaults.update(kwargs)
    return ChatBedrockConverse(**defaults)


def is_llm_configured() -> bool:
    """Return True if the active LLM provider has credentials configured."""
    provider = settings.llm_provider.lower()
    if provider == "bedrock":
        # Bedrock uses IAM roles/env — always considered configured
        return True
    return bool(settings.nvidia_api_key)


def get_llm(**kwargs) -> BaseChatModel:
    """Build the configured LLM.

    Set GII_LLM_PROVIDER=nvidia (default) or GII_LLM_PROVIDER=bedrock.
    """
    configure_langsmith()

    provider = settings.llm_provider.lower()
    if provider == "bedrock":
        return _build_bedrock(**kwargs)
    return _build_nvidia(**kwargs)
