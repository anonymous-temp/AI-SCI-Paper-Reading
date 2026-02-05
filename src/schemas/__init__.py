"""
Core data schemas for the Medical SCI Paper Review System
"""
from .document_ir import DocumentIR, StudyProfile
from .rubric import RubricItem, RubricBlock, RubricItemOutputSchema
from .review_state import ReviewState, SecurityAlert
from .reports import AuthorReport, EditorReport

__all__ = [
    "DocumentIR",
    "StudyProfile",
    "RubricItem",
    "RubricBlock",
    "RubricItemOutputSchema",
    "ReviewState",
    "SecurityAlert",
    "AuthorReport",
    "EditorReport",
]
