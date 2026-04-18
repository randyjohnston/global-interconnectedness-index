"""Pipeline management endpoints — trigger and monitor Temporal workflows."""

import uuid

from fastapi import APIRouter

from gii.api.schemas import PipelineStatusResponse, PipelineTriggerRequest
from gii.config import settings
from gii.pipelines.activities import PipelineParams

router = APIRouter(prefix="/api/pipelines", tags=["pipelines"])


@router.post("/trigger", response_model=PipelineStatusResponse)
async def trigger_pipeline(req: PipelineTriggerRequest):
    """Trigger a MainRefreshWorkflow via Temporal."""
    from temporalio.client import Client

    try:
        client = await Client.connect(settings.temporal_host, namespace=settings.temporal_namespace)
    except Exception as e:
        return PipelineStatusResponse(status="error", message=f"Cannot connect to Temporal: {e}")

    period = req.period or str(req.year)
    params = PipelineParams(year=req.year, period=period)
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


@router.get("/status", response_model=PipelineStatusResponse)
async def pipeline_status():
    """Check if Temporal is reachable."""
    from temporalio.client import Client

    try:
        await Client.connect(settings.temporal_host, namespace=settings.temporal_namespace)
        return PipelineStatusResponse(status="connected", message="Temporal is reachable")
    except Exception as e:
        return PipelineStatusResponse(status="disconnected", message=str(e))
