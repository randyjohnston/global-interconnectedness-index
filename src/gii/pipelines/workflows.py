"""Temporal workflow definitions for the GII data pipeline."""

from datetime import timedelta

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from gii.pipelines.activities import (
        MultiPeriodPipelineParams,
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
        )


@workflow.defn
class TravelDataWorkflow:
    """Fetch flight routes from OpenFlights."""

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

        # Phase 1: Ingest data sources in parallel (only enabled ones)
        handles = {}
        if params.step_trade:
            handles["trade"] = await workflow.start_child_workflow(
                TradeDataWorkflow.run, params, id=f"trade-{params.period}",
            )
        if params.step_travel:
            handles["travel"] = await workflow.start_child_workflow(
                TravelDataWorkflow.run, params, id=f"travel-{params.period}",
            )
        if params.step_geopolitics:
            handles["geopolitics"] = await workflow.start_child_workflow(
                GeopoliticsDataWorkflow.run, params, id=f"geo-{params.period}",
            )

        for key, handle in handles.items():
            results[key] = await handle

        # Phase 2: Quality check
        if params.step_quality:
            results["quality"] = await workflow.execute_activity(
                run_quality_check,
                params,
                start_to_close_timeout=timedelta(minutes=15),
            )

        # Phase 3: Compute composite index
        if params.step_index:
            results["index_count"] = await workflow.execute_activity(
                compute_and_store_index,
                params,
                start_to_close_timeout=timedelta(minutes=10),
            )

        # Phase 4: Generate narratives for top movers
        if params.step_narratives:
            results["narratives"] = await workflow.execute_activity(
                generate_narratives,
                params,
                start_to_close_timeout=timedelta(minutes=60),
            )

        return results


@workflow.defn
class MultiPeriodRefreshWorkflow:
    """Process multiple years sequentially: data + quality + index for each year,
    then narratives only for the final year."""

    @workflow.run
    async def run(self, params: MultiPeriodPipelineParams) -> dict:
        all_results = {}

        for year in range(params.start_year, params.end_year + 1):
            year_params = PipelineParams(
                year=year, period=str(year),
                step_trade=params.step_trade, step_travel=params.step_travel,
                step_geopolitics=params.step_geopolitics, step_quality=params.step_quality,
                step_index=params.step_index,
            )
            year_key = str(year)
            all_results[year_key] = {}

            # Phase 1: Ingest data sources in parallel (only enabled ones)
            handles = {}
            if params.step_trade:
                handles["trade"] = await workflow.start_child_workflow(
                    TradeDataWorkflow.run, year_params, id=f"trade-{year}",
                )
            if params.step_travel:
                handles["travel"] = await workflow.start_child_workflow(
                    TravelDataWorkflow.run, year_params, id=f"travel-{year}",
                )
            if params.step_geopolitics:
                handles["geopolitics"] = await workflow.start_child_workflow(
                    GeopoliticsDataWorkflow.run, year_params, id=f"geo-{year}",
                )

            for key, handle in handles.items():
                all_results[year_key][key] = await handle

            # Phase 2: Quality check
            if params.step_quality:
                all_results[year_key]["quality"] = await workflow.execute_activity(
                    run_quality_check,
                    year_params,
                    start_to_close_timeout=timedelta(minutes=15),
                )

            # Phase 3: Compute composite index
            if params.step_index:
                all_results[year_key]["index_count"] = await workflow.execute_activity(
                    compute_and_store_index,
                    year_params,
                    start_to_close_timeout=timedelta(minutes=10),
                )

        # Phase 4: Generate narratives only for the final year
        if params.step_narratives:
            final_params = PipelineParams(
                year=params.end_year, period=str(params.end_year),
                narrative_top_n=params.narrative_top_n,
                step_trade=params.step_trade, step_travel=params.step_travel,
                step_geopolitics=params.step_geopolitics, step_quality=params.step_quality,
                step_index=params.step_index, step_narratives=params.step_narratives,
            )
            all_results["narratives"] = await workflow.execute_activity(
                generate_narratives,
                final_params,
                start_to_close_timeout=timedelta(minutes=60),
            )

        return all_results
