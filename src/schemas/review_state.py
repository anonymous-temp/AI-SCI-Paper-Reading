"""
Review state and security alerts
"""
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime

from .document_ir import DocumentIR, StudyProfile, EvidenceMap
from .rubric import RubricBlock, BlockReviewResult


class JobStatus(str, Enum):
    """Overall job status"""
    PENDING = "PENDING"
    PARSING = "PARSING"
    REVIEWING = "REVIEWING"
    SYNTHESIZING = "SYNTHESIZING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class SecurityAlertType(str, Enum):
    """Types of security alerts"""
    PROMPT_INJECTION = "PROMPT_INJECTION"
    INVISIBLE_TEXT = "INVISIBLE_TEXT"
    ETHICS_MISSING = "ETHICS_MISSING"
    SUSPICIOUS_CONTENT = "SUSPICIOUS_CONTENT"


class SecurityAlert(BaseModel):
    """Security or integrity alert"""
    alert_type: SecurityAlertType
    severity: str  # CRITICAL, WARNING, INFO
    evidence: str
    location: Optional[str] = None
    detected_at: datetime = Field(default_factory=datetime.now)

    class Config:
        json_schema_extra = {
            "example": {
                "alert_type": "ETHICS_MISSING",
                "severity": "WARNING",
                "evidence": "No mention of ethics committee approval found in methods section",
                "location": "methods.ethics",
                "detected_at": "2026-01-21T12:00:00Z"
            }
        }


class OrchestrationState(BaseModel):
    """State of rubric orchestration"""
    rubric_blocks: List[RubricBlock] = Field(default_factory=list)
    task_status: Dict[str, str] = Field(
        default_factory=dict,
        description="Maps block_id to status (PENDING, RUNNING, COMPLETED, FAILED)"
    )
    total_blocks: int = 0
    completed_blocks: int = 0


class ReviewState(BaseModel):
    """
    Central state object for an entire review job.
    This is the main coordination structure between all agents.
    """
    # Job identification
    job_id: str = Field(..., description="Unique job identifier")
    manuscript_path: str = Field(..., description="Path to original manuscript file")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    # Current status
    status: JobStatus = Field(default=JobStatus.PENDING)
    progress_percentage: float = Field(default=0.0, ge=0.0, le=100.0)

    # Core data products
    document_ir: Optional[DocumentIR] = None
    study_profile: Optional[StudyProfile] = None
    evidence_map: Optional[EvidenceMap] = None

    # Security checks
    security_alerts: List[SecurityAlert] = Field(default_factory=list)

    # Orchestration
    orchestration: OrchestrationState = Field(default_factory=OrchestrationState)

    # Review results
    review_results: Dict[str, BlockReviewResult] = Field(
        default_factory=dict,
        description="Maps block_id to its review results"
    )

    # Final outputs
    final_reports: Dict[str, str] = Field(
        default_factory=dict,
        description="Final report content (author_report, editor_report)"
    )

    # Error tracking
    error_log: List[Dict[str, Any]] = Field(default_factory=list)

    # Metrics
    metrics: Dict[str, Any] = Field(
        default_factory=dict,
        description="Performance metrics (processing time, token usage, etc.)"
    )

    def add_error(self, error_code: str, message: str, details: Optional[Dict] = None):
        """Add an error to the error log"""
        self.error_log.append({
            "timestamp": datetime.now().isoformat(),
            "error_code": error_code,
            "message": message,
            "details": details or {}
        })

    def add_security_alert(self, alert: SecurityAlert):
        """Add a security alert"""
        self.security_alerts.append(alert)

    def update_progress(self):
        """Update progress percentage based on orchestration state"""
        if self.orchestration.total_blocks > 0:
            base_progress = (self.orchestration.completed_blocks / self.orchestration.total_blocks) * 70
            # Add fixed percentages for other stages
            if self.status == JobStatus.PARSING:
                self.progress_percentage = 10.0
            elif self.status == JobStatus.REVIEWING:
                self.progress_percentage = 20.0 + base_progress
            elif self.status == JobStatus.SYNTHESIZING:
                self.progress_percentage = 90.0
            elif self.status == JobStatus.COMPLETED:
                self.progress_percentage = 100.0
        self.updated_at = datetime.now()

    class Config:
        json_schema_extra = {
            "example": {
                "job_id": "uuid-1234-abcd",
                "manuscript_path": "/path/to/manuscript.docx",
                "status": "REVIEWING",
                "progress_percentage": 45.0,
                "document_ir": None,
                "study_profile": None,
                "security_alerts": [],
                "orchestration": {
                    "total_blocks": 10,
                    "completed_blocks": 4
                },
                "review_results": {},
                "final_reports": {},
                "error_log": []
            }
        }
