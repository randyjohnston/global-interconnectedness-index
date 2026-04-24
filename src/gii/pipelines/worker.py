"""Temporal worker entrypoint — run with: uv run python -m gii.pipelines.worker"""

import asyncio
import logging
import os

from gii.config import settings

if settings.langsmith_api_key and settings.langsmith_tracing == "true":
    os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
    os.environ["LANGSMITH_TRACING"] = settings.langsmith_tracing

from temporalio.client import Client
from temporalio.worker import Worker

from gii.pipelines.activities import (
    compute_and_store_index,
    fetch_and_store_flights,
    fetch_and_store_gdelt,
    fetch_and_store_trade,
    generate_narratives,
    run_quality_check,
)
from gii.pipelines.workflows import (
    GeopoliticsDataWorkflow,
    MainRefreshWorkflow,
    TradeDataWorkflow,
    TravelDataWorkflow,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    logger.info(f"Connecting to Temporal at {settings.temporal_host}")
    client = await Client.connect(settings.temporal_host, namespace=settings.temporal_namespace)

    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[
            MainRefreshWorkflow,
            TradeDataWorkflow,
            TravelDataWorkflow,
            GeopoliticsDataWorkflow,
        ],
        activities=[
            fetch_and_store_trade,
            fetch_and_store_flights,
            fetch_and_store_gdelt,
            compute_and_store_index,
            run_quality_check,
            generate_narratives,
        ],
    )

    logger.info(f"Worker listening on queue: {settings.temporal_task_queue}")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
