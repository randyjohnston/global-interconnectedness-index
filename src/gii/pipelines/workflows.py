"""Temporal workflow definitions for the GII data pipeline."""

from datetime import timedelta

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from gii.pipelines.activities import (
        PipelineParams,
        compute_and_store_index,
        fetch_and_store_flights,
        fetch_and_store_gdelt,
        fetch_and_store_trade,
        generate_narratives,
        run_quality_check,
    )


@workflow.defn
class TradeDataWorkflow:
    """Fetch and normalize bilateral trade data from Comtrade."""

    @workflow.run
    async def run(self, params: PipelineParams) -> int:
        return await workflow.execute_activity(
            fetch_and_store_trade,
            params,
            start_to_close_timeout=timedelta(minutes=30),
            heartbeat_timeout=timedelta(minutes=2),
        )


@workflow.defn
class TravelDataWorkflow:
    """Fetch flight routes from airline route dataset."""

    @workflow.run
    async def run(self, params: PipelineParams) -> int:
        return await workflow.execute_activity(
            fetch_and_store_flights,
            params,
            start_to_close_timeout=timedelta(minutes=10),
        )


@workflow.defn
class GeopoliticsDataWorkflow:
    """Fetch GDELT geopolitics data from BigQuery."""

    @workflow.run
    async def run(self, params: PipelineParams) -> int:
        return await workflow.execute_activity(
            fetch_and_store_gdelt,
            params,
            start_to_close_timeout=timedelta(minutes=15),
        )


@workflow.defn
class MainRefreshWorkflow:
    """Top-level workflow: orchestrates all pillars, quality check, index computation, and narratives."""

    @workflow.run
    async def run(self, params: PipelineParams) -> dict:
        results = {}

        # Phase 1: Ingest all data sources (can run in parallel via child workflows)
        trade_handle = await workflow.start_child_workflow(
            TradeDataWorkflow.run, params, id=f"trade-{params.period}",
        )
        travel_handle = await workflow.start_child_workflow(
            TravelDataWorkflow.run, params, id=f"travel-{params.period}",
        )
        geo_handle = await workflow.start_child_workflow(
            GeopoliticsDataWorkflow.run, params, id=f"geo-{params.period}",
        )

        results["trade"] = await trade_handle
        results["travel"] = await travel_handle
        results["geopolitics"] = await geo_handle

        # Phase 2: Quality check
        results["quality"] = await workflow.execute_activity(
            run_quality_check,
            params,
            start_to_close_timeout=timedelta(minutes=15),
        )

        # Phase 3: Compute composite index
        results["index_count"] = await workflow.execute_activity(
            compute_and_store_index,
            params,
            start_to_close_timeout=timedelta(minutes=10),
        )

        # Phase 4: Generate narratives for top movers
        results["narratives"] = await workflow.execute_activity(
            generate_narratives,
            params,
            start_to_close_timeout=timedelta(minutes=10),
            heartbeat_timeout=timedelta(minutes=2),
        )

        return results
