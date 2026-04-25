"""Pipeline management endpoints — trigger and monitor Temporal workflows."""

import uuid

from fastapi import APIRouter

from gii.api.schemas import MultiPeriodTriggerRequest, PipelineStatusResponse, PipelineTriggerRequest
from gii.config import settings
from gii.pipelines.activities import MultiPeriodPipelineParams, PipelineParams

router = APIRouter(prefix="/api/pipelines", tags=["pipelines"])


@router.post("/trigger", response_model=PipelineStatusResponse)
async def trigger_pipeline(req: PipelineTriggerRequest):
    """Trigger a MainRefreshWorkflow via Temporal."""
    from temporalio.client import Client

    try:
        client = await Client.connect(settings.temporal_host, namespace=settings.temporal_namespace)
    except Exception as e:
        return PipelineStatusResponse(status="error", message=f"Cannot connect to Temporal: {e}")

    period = req.period
    # Extract year from period (e.g. "2025" or "2025-Q1" -> 2025)
    try:
        year = int(period[:4])
    except (ValueError, IndexError):
        return PipelineStatusResponse(status="error", message=f"Invalid period: {period!r} — expected e.g. '2025' or '2025-Q1'")
    params = PipelineParams(year=year, period=period)
    workflow_id = f"main-refresh-{period}-{uuid.uuid4().hex[:8]}"

    try:
        from gii.pipelines.workflows import MainRefreshWorkflow
        await client.start_workflow(
            MainRefreshWorkflow.run,
            params,
            id=workflow_id,
            task_queue=settings.temporal_task_queue,
        )
        return PipelineStatusResponse(
            status="started",
            workflow_id=workflow_id,
            message=f"Pipeline started for {period}",
        )
    except Exception as e:
        return PipelineStatusResponse(status="error", message=str(e))


@router.post("/trigger-multi", response_model=PipelineStatusResponse)
async def trigger_multi_period_pipeline(req: MultiPeriodTriggerRequest):
    """Trigger a MultiPeriodRefreshWorkflow via Temporal."""
    from temporalio.client import Client

    if req.end_year < req.start_year:
        return PipelineStatusResponse(status="error", message="end_year must be >= start_year")
    if req.end_year - req.start_year + 1 > 5:
        return PipelineStatusResponse(status="error", message="Maximum 5 year span allowed")

    try:
        client = await Client.connect(settings.temporal_host, namespace=settings.temporal_namespace)
    except Exception as e:
        return PipelineStatusResponse(status="error", message=f"Cannot connect to Temporal: {e}")

    params = MultiPeriodPipelineParams(start_year=req.start_year, end_year=req.end_year)
    workflow_id = f"multi-refresh-{req.start_year}-{req.end_year}-{uuid.uuid4().hex[:8]}"

    try:
        from gii.pipelines.workflows import MultiPeriodRefreshWorkflow
        await client.start_workflow(
            MultiPeriodRefreshWorkflow.run,
            params,
            id=workflow_id,
            task_queue=settings.temporal_task_queue,
        )
        return PipelineStatusResponse(
            status="started",
            workflow_id=workflow_id,
            message=f"Multi-period pipeline started for {req.start_year}–{req.end_year} ({req.end_year - req.start_year + 1} years, narratives for {req.end_year} only)",
        )
    except Exception as e:
        return PipelineStatusResponse(status="error", message=str(e))


@router.get("/status", response_model=PipelineStatusResponse)
async def pipeline_status():
    """Check if Temporal is reachable."""
    from temporalio.client import Client

    try:
        await Client.connect(settings.temporal_host, namespace=settings.temporal_namespace)
        return PipelineStatusResponse(status="connected", message="Temporal is reachable")
    except Exception as e:
        return PipelineStatusResponse(status="disconnected", message=str(e))
