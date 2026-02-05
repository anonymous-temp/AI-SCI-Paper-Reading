"""
FastAPI application for Medical Review Service
"""
from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks, Depends
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import uuid
import os
import tempfile
from pathlib import Path

from ..main import ReviewOrchestrator
from ..schemas.review_state import ReviewState, JobStatus
from ..schemas.reports import AuthorReport, EditorReport
from ..utils.logging_config import setup_logging, get_logger
from .metrics import (
    setup_metrics,
    REQUEST_COUNT,
    REQUEST_DURATION,
    JOB_STATUS_COUNTER,
    ACTIVE_JOBS
)

# Setup logging
setup_logging(log_level="INFO", log_file="logs/api.log", json_format=True)
logger = get_logger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Medical SCI Paper Review API",
    description="AI-powered automated pre-review system for medical manuscripts",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Setup Prometheus metrics
setup_metrics(app)

# In-memory job storage (use Redis/DB in production)
job_store = {}

# Initialize orchestrator
orchestrator = None


def get_orchestrator() -> ReviewOrchestrator:
    """Get or create review orchestrator"""
    global orchestrator
    if orchestrator is None:
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
        provider = "openai" if os.getenv("OPENAI_API_KEY") else "anthropic"
        orchestrator = ReviewOrchestrator(llm_api_key=api_key, llm_provider=provider)
    return orchestrator


# Request/Response models
class JobSubmitResponse(BaseModel):
    """Response for job submission"""
    job_id: str
    status: str
    message: str


class JobStatusResponse(BaseModel):
    """Response for job status check"""
    job_id: str
    status: str
    progress_percentage: float
    created_at: str
    updated_at: str
    error_count: int


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    version: str
    service: str


# Endpoints
@app.get("/", response_model=HealthResponse)
async def root():
    """Root endpoint - health check"""
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        service="Medical Review API"
    )


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    REQUEST_COUNT.labels(method="GET", endpoint="/health", status="200").inc()
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        service="Medical Review API"
    )


@app.post("/api/v1/review/submit", response_model=JobSubmitResponse)
async def submit_review(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    use_ocr: bool = False
):
    """
    Submit a manuscript for automated review.

    Args:
        file: Manuscript file (.pdf, .docx, .txt)
        use_ocr: Enable OCR for scanned PDFs

    Returns:
        Job submission response with job_id
    """
    REQUEST_COUNT.labels(method="POST", endpoint="/api/v1/review/submit", status="202").inc()

    # Validate file format
    allowed_formats = ['.pdf', '.docx', '.txt']
    file_ext = Path(file.filename).suffix.lower()

    if file_ext not in allowed_formats:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format: {file_ext}. Allowed: {', '.join(allowed_formats)}"
        )

    # Generate job ID
    job_id = str(uuid.uuid4())

    # Save uploaded file to temp location
    temp_dir = Path(tempfile.gettempdir()) / "medical_review" / job_id
    temp_dir.mkdir(parents=True, exist_ok=True)
    file_path = temp_dir / file.filename

    try:
        # Save file
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)

        # Create initial job state
        job_state = ReviewState(
            job_id=job_id,
            manuscript_path=str(file_path),
            status=JobStatus.PENDING
        )
        job_store[job_id] = job_state

        # Schedule background task
        background_tasks.add_task(
            process_review_job,
            job_id=job_id,
            file_path=str(file_path),
            use_ocr=use_ocr
        )

        ACTIVE_JOBS.inc()
        JOB_STATUS_COUNTER.labels(status="submitted").inc()

        logger.info(f"Job {job_id} submitted for review", job_id=job_id, filename=file.filename)

        return JobSubmitResponse(
            job_id=job_id,
            status="accepted",
            message="Manuscript submitted successfully. Check job status with job_id."
        )

    except Exception as e:
        logger.error(f"Failed to submit job {job_id}", job_id=job_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to process upload: {str(e)}")


@app.get("/api/v1/review/{job_id}/status", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    """
    Get status of a review job.

    Args:
        job_id: Job identifier

    Returns:
        Current job status and progress
    """
    REQUEST_COUNT.labels(method="GET", endpoint="/api/v1/review/status", status="200").inc()

    if job_id not in job_store:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    job_state = job_store[job_id]

    return JobStatusResponse(
        job_id=job_id,
        status=job_state.status.value,
        progress_percentage=job_state.progress_percentage,
        created_at=job_state.created_at.isoformat(),
        updated_at=job_state.updated_at.isoformat(),
        error_count=len(job_state.error_log)
    )


@app.get("/api/v1/review/{job_id}/report/author")
async def get_author_report(job_id: str):
    """
    Get author report for completed review.

    Args:
        job_id: Job identifier

    Returns:
        Author report in markdown format
    """
    REQUEST_COUNT.labels(method="GET", endpoint="/api/v1/review/report/author", status="200").inc()

    if job_id not in job_store:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    job_state = job_store[job_id]

    if job_state.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Job not completed. Current status: {job_state.status.value}"
        )

    if "author_report" not in job_state.final_reports:
        raise HTTPException(status_code=404, detail="Author report not available")

    return {
        "job_id": job_id,
        "report_type": "author",
        "content": job_state.final_reports["author_report"],
        "generated_at": job_state.updated_at.isoformat()
    }


@app.get("/api/v1/review/{job_id}/report/editor")
async def get_editor_report(job_id: str):
    """
    Get editor report for completed review.

    Args:
        job_id: Job identifier

    Returns:
        Editor report in markdown format
    """
    REQUEST_COUNT.labels(method="GET", endpoint="/api/v1/review/report/editor", status="200").inc()

    if job_id not in job_store:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    job_state = job_store[job_id]

    if job_state.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Job not completed. Current status: {job_state.status.value}"
        )

    if "editor_report" not in job_state.final_reports:
        raise HTTPException(status_code=404, detail="Editor report not available")

    return {
        "job_id": job_id,
        "report_type": "editor",
        "content": job_state.final_reports["editor_report"],
        "generated_at": job_state.updated_at.isoformat()
    }


@app.get("/api/v1/checklists")
async def list_checklists():
    """
    List all available checklists.

    Returns:
        List of available checklists with metadata
    """
    REQUEST_COUNT.labels(method="GET", endpoint="/api/v1/checklists", status="200").inc()

    from ..utils.rubric_loader import RubricLoader

    loader = RubricLoader()
    rubrics = loader.list_available_rubrics()

    checklist_info = []
    for rubric_name in rubrics:
        try:
            metadata = loader.get_rubric_metadata(rubric_name)
            checklist_info.append({
                "id": rubric_name,
                "name": metadata["name"],
                "version": metadata["version"],
                "applicable_to": metadata["applicable_to"],
                "description": metadata["description"],
                "item_count": metadata["item_count"]
            })
        except Exception as e:
            logger.error(f"Failed to load metadata for {rubric_name}", error=str(e))

    return {
        "total": len(checklist_info),
        "checklists": checklist_info
    }


@app.delete("/api/v1/review/{job_id}")
async def delete_job(job_id: str):
    """
    Delete a review job and associated data.

    Args:
        job_id: Job identifier

    Returns:
        Deletion confirmation
    """
    REQUEST_COUNT.labels(method="DELETE", endpoint="/api/v1/review", status="200").inc()

    if job_id not in job_store:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    # Clean up temp files
    job_state = job_store[job_id]
    try:
        temp_dir = Path(job_state.manuscript_path).parent
        if temp_dir.exists():
            import shutil
            shutil.rmtree(temp_dir)
    except Exception as e:
        logger.warning(f"Failed to clean up temp files for job {job_id}", error=str(e))

    # Remove from store
    del job_store[job_id]

    ACTIVE_JOBS.dec()

    return {
        "job_id": job_id,
        "status": "deleted",
        "message": "Job deleted successfully"
    }


# Background task
async def process_review_job(job_id: str, file_path: str, use_ocr: bool = False):
    """
    Background task to process review job.

    Args:
        job_id: Job identifier
        file_path: Path to manuscript file
        use_ocr: Enable OCR for scanned PDFs
    """
    logger.info(f"Starting review processing for job {job_id}", job_id=job_id)

    try:
        # Get orchestrator
        orch = get_orchestrator()

        # Update status
        job_store[job_id].status = JobStatus.PARSING
        job_store[job_id].update_progress()

        # Execute review
        review_state, author_report, editor_report = await orch.review_manuscript(
            manuscript_path=file_path,
            job_id=job_id
        )

        # Update job store with results
        job_store[job_id] = review_state
        JOB_STATUS_COUNTER.labels(status="completed").inc()

        logger.info(f"Review completed for job {job_id}", job_id=job_id)

    except Exception as e:
        logger.error(f"Review failed for job {job_id}", job_id=job_id, error=str(e))

        # Update job with error
        job_store[job_id].status = JobStatus.FAILED
        job_store[job_id].add_error("9001", f"Review processing failed: {str(e)}")

        JOB_STATUS_COUNTER.labels(status="failed").inc()

    finally:
        ACTIVE_JOBS.dec()


# Run the application
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
