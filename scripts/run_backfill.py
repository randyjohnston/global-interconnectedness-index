"""One-time historical data backfill — triggers a MainRefreshWorkflow for a given year."""

import asyncio
import sys

from temporalio.client import Client

from gii.config import settings
from gii.pipelines.activities import PipelineParams
from gii.pipelines.workflows import MainRefreshWorkflow


async def main(year: int):
    client = await Client.connect(settings.temporal_host, namespace=settings.temporal_namespace)
    params = PipelineParams(year=year, period=str(year))

    result = await client.execute_workflow(
        MainRefreshWorkflow.run,
        params,
        id=f"backfill-{year}",
        task_queue=settings.temporal_task_queue,
    )
    print(f"Backfill for {year} completed: {result}")


if __name__ == "__main__":
    year = int(sys.argv[1]) if len(sys.argv) > 1 else 2024
    asyncio.run(main(year))
