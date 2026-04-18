"""Temporal worker entrypoint — run with: uv run python -m gii.pipelines.worker"""

import asyncio
import logging

from temporalio.client import Client
from temporalio.worker import Worker

from gii.config import settings
from gii.pipelines.activities import (
    compute_and_store_index,
    fetch_and_store_flights,
    fetch_and_store_gdelt,
    fetch_and_store_trade,
    generate_narratives,
    ingest_and_store_unwto,
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
            ingest_and_store_unwto,
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
