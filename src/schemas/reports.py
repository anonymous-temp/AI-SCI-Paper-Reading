"""
Report data structures
"""
from typing import List, Dict, Optional
from pydantic import BaseModel, Field
from datetime import datetime

from .rubric import SeverityLevel


class IssueItem(BaseModel):
    """A single issue identified in the manuscript"""
    category: str = Field(..., description="Issue category, e.g., 'Randomization', 'Statistics'")
    severity: SeverityLevel
    description: str = Field(..., description="Description of the issue")
    evidence: List[str] = Field(default_factory=list, description="Supporting evidence quotes")
    recommendation: str = Field(..., description="Actionable fix recommendation")
    checklist_reference: str = Field(..., description="Source checklist item, e.g., 'CONSORT 8a'")


class AuthorReport(BaseModel):
    """
    Report for manuscript authors.
    Focuses on constructive feedback and actionable recommendations.
    """
    job_id: str
    manuscript_title: str
    generated_at: datetime = Field(default_factory=datetime.now)

    # Greeting and introduction
    introduction: str = Field(
        default="Thank you for your submission. Our automated pre-review system has conducted a preliminary assessment of your manuscript based on international reporting guidelines."
    )

    # Issues organized by severity
    critical_issues: List[IssueItem] = Field(default_factory=list)
    major_issues: List[IssueItem] = Field(default_factory=list)
    minor_issues: List[IssueItem] = Field(default_factory=list)

    # Summary statistics
    total_issues: int = 0
    checklists_applied: List[str] = Field(default_factory=list)

    # Closing statement
    conclusion: str = Field(
        default="Please address the issues identified above before resubmission. For questions about specific recommendations, please consult the relevant reporting guidelines."
    )

    # Disclaimer
    disclaimer: str = Field(
        default="This report was generated with AI assistance and is for reference only. It does not constitute a final peer-review decision."
    )

    def to_markdown(self) -> str:
        """Generate markdown formatted report"""
        lines = [
            f"# Automated Pre-Review Report",
            f"",
            f"**Manuscript:** {self.manuscript_title}",
            f"**Generated:** {self.generated_at.strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Job ID:** {self.job_id}",
            f"",
            f"---",
            f"",
            f"{self.introduction}",
            f"",
            f"## Summary",
            f"",
            f"- **Total Issues Identified:** {self.total_issues}",
            f"- **Critical Issues:** {len(self.critical_issues)}",
            f"- **Major Issues:** {len(self.major_issues)}",
            f"- **Minor Issues:** {len(self.minor_issues)}",
            f"- **Reporting Guidelines Applied:** {', '.join(self.checklists_applied)}",
            f"",
        ]

        if self.critical_issues:
            lines.extend([
                f"## Critical Issues",
                f"",
                "*These are fundamental flaws that may invalidate the study.*",
                f"",
            ])
            for idx, issue in enumerate(self.critical_issues, 1):
                lines.extend(self._format_issue(idx, issue))

        if self.major_issues:
            lines.extend([
                f"## Major Issues",
                f"",
                "*These are significant methodological concerns that should be addressed.*",
                f"",
            ])
            for idx, issue in enumerate(self.major_issues, 1):
                lines.extend(self._format_issue(idx, issue))

        if self.minor_issues:
            lines.extend([
                f"## Minor Issues",
                f"",
                "*These are minor points that would improve the manuscript.*",
                f"",
            ])
            for idx, issue in enumerate(self.minor_issues, 1):
                lines.extend(self._format_issue(idx, issue))

        lines.extend([
            f"",
            f"---",
            f"",
            f"## Conclusion",
            f"",
            f"{self.conclusion}",
            f"",
            f"---",
            f"",
            f"*{self.disclaimer}*",
        ])

        return "\n".join(lines)

    def _format_issue(self, number: int, issue: IssueItem) -> List[str]:
        """Format a single issue for markdown output"""
        lines = [
            f"### {number}. {issue.category} ({issue.checklist_reference})",
            f"",
            f"**Issue:** {issue.description}",
            f"",
        ]

        if issue.evidence:
            lines.append(f"**Evidence:**")
            for evidence in issue.evidence:
                lines.append(f"> {evidence}")
            lines.append(f"")

        lines.extend([
            f"**Recommendation:** {issue.recommendation}",
            f"",
        ])

        return lines


class EditorDecision(str):
    """Recommended decision for editor"""
    REJECT = "REJECT"
    MAJOR_REVISION = "MAJOR_REVISION"
    MINOR_REVISION = "MINOR_REVISION"
    SEND_FOR_REVIEW = "SEND_FOR_REVIEW"


class EditorReport(BaseModel):
    """
    Concise report for journal editors.
    Focuses on decision support and risk assessment.
    """
    job_id: str
    manuscript_title: str
    generated_at: datetime = Field(default_factory=datetime.now)

    # Recommendation
    recommendation: str = Field(
        ...,
        description="Overall recommendation: REJECT, MAJOR_REVISION, MINOR_REVISION, SEND_FOR_REVIEW"
    )

    # Executive summary
    executive_summary: str = Field(..., description="Brief summary of key findings")

    # Risk assessment
    critical_risks: List[str] = Field(default_factory=list)
    major_risks: List[str] = Field(default_factory=list)

    # Methodology assessment
    study_types_identified: List[str] = Field(default_factory=list)
    checklists_applied: List[str] = Field(default_factory=list)

    # Quality metrics
    total_issues: int = 0
    critical_count: int = 0
    major_count: int = 0
    minor_count: int = 0

    # Alerts
    security_alerts: List[str] = Field(default_factory=list)

    # Disclaimer
    disclaimer: str = Field(
        default="This report was generated with AI assistance for pre-screening purposes only. Final editorial decisions should be based on comprehensive peer review."
    )

    def to_markdown(self) -> str:
        """Generate markdown formatted editor report"""
        lines = [
            f"# Editor Pre-Review Report",
            f"",
            f"**Manuscript:** {self.manuscript_title}",
            f"**Generated:** {self.generated_at.strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Job ID:** {self.job_id}",
            f"",
            f"---",
            f"",
            f"## Recommendation",
            f"",
            f"**{self.recommendation}**",
            f"",
            f"## Executive Summary",
            f"",
            f"{self.executive_summary}",
            f"",
            f"## Risk Assessment",
            f"",
            f"**Total Issues:** {self.total_issues} ({self.critical_count} critical, {self.major_count} major, {self.minor_count} minor)",
            f"",
        ]

        if self.critical_risks:
            lines.extend([
                f"### Critical Risks",
                f"",
            ])
            for risk in self.critical_risks:
                lines.append(f"- {risk}")
            lines.append(f"")

        if self.major_risks:
            lines.extend([
                f"### Major Risks",
                f"",
            ])
            for risk in self.major_risks:
                lines.append(f"- {risk}")
            lines.append(f"")

        if self.security_alerts:
            lines.extend([
                f"### Security Alerts",
                f"",
            ])
            for alert in self.security_alerts:
                lines.append(f"- ⚠️ {alert}")
            lines.append(f"")

        lines.extend([
            f"## Methodology Assessment",
            f"",
            f"**Study Types Identified:** {', '.join(self.study_types_identified)}",
            f"",
            f"**Reporting Guidelines Applied:** {', '.join(self.checklists_applied)}",
            f"",
            f"---",
            f"",
            f"*{self.disclaimer}*",
        ])

        return "\n".join(lines)
