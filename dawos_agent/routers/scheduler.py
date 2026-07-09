"""Task scheduler API endpoints.

Provides REST endpoints for CRUD management of cron-like scheduled
jobs on the BNG agent.  Jobs are stored in-memory and can be
listed, created, deleted, or triggered for immediate execution.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from ..auth import ApiKey, ViewerKey
from ..models.schemas import (
    SchedulerJobRequest,
    SchedulerJobResponse,
    SchedulerListResponse,
    SchedulerRunResponse,
)
from ..services import scheduler

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/scheduler", tags=["scheduler"])


@router.get("/jobs", response_model=SchedulerListResponse)
async def list_jobs(_key: str = ViewerKey):
    """List all scheduled jobs.

    Returns every registered job with its name, command, interval,
    enabled flag, and last-run timestamp.

    Returns:
        SchedulerListResponse: Count and list of job records.
    """
    jobs = scheduler.list_jobs()
    return SchedulerListResponse(
        count=len(jobs),
        jobs=[SchedulerJobResponse(**j) for j in jobs],
    )


@router.post("/jobs", response_model=SchedulerJobResponse, status_code=201)
async def add_job(req: SchedulerJobRequest, _key: str = ApiKey):
    """Register a new scheduled job.

    Creates a job that runs the given shell command at the specified
    interval.

    Args:
        req: Request body with name, command, interval_seconds, and
            enabled flag.

    Returns:
        SchedulerJobResponse: The newly created job record.

    Raises:
        HTTPException(409): If a job with the same name already exists.
        HTTPException(500): If the job cannot be created.
    """
    try:
        job = scheduler.add_job(
            name=req.name,
            command=req.command,
            interval_seconds=req.interval_seconds,
            enabled=req.enabled,
        )
        return SchedulerJobResponse(**job)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/jobs/{name}", status_code=204)
async def remove_job(name: str, _key: str = ApiKey):
    """Remove a scheduled job by name.

    Deletes the job from the scheduler.  Returns 204 on success.

    Args:
        name: The job name to remove (path parameter).

    Raises:
        HTTPException(404): If no job with the given name exists.
    """
    try:
        scheduler.remove_job(name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/jobs/{name}/run", response_model=SchedulerRunResponse)
async def run_job(name: str, _key: str = ApiKey):
    """Execute a scheduled job immediately.

    Runs the job's command right now regardless of its interval
    schedule and returns the output.

    Args:
        name: The job name to execute (path parameter).

    Returns:
        SchedulerRunResponse: Command output, return code, and timestamp.

    Raises:
        HTTPException(404): If no job with the given name exists.
        HTTPException(500): If the command execution fails.
    """
    try:
        result = await scheduler.run_job(name)
        return SchedulerRunResponse(
            success=result["returncode"] == 0,
            output=result["output"],
            returncode=result["returncode"],
            timestamp=result["timestamp"],
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
