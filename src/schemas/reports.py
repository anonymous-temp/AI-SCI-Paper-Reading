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
            f"## 📊 Summary",
            f"",
            f"| Category | Count | Priority |",
            f"|----------|-------|----------|",
            f"| ❗ Critical Issues | **{len(self.critical_issues)}** | **Must Fix** |",
            f"| ⚠️ Major Issues | **{len(self.major_issues)}** | **Should Fix** |",
            f"| ℹ️ Minor Issues | {len(self.minor_issues)} | Recommended |",
            f"| **Total** | **{self.total_issues}** | |",
            f"",
            f"**Reporting Guidelines Applied:** {', '.join(self.checklists_applied)}",
            f"",
        ]

        # Add Quick Action Checklist
        must_fix_count = len(self.critical_issues) + len(self.major_issues)
        if must_fix_count > 0:
            lines.extend([
                f"## ✅ Quick Action Checklist",
                f"",
                f"**Priority items to address before resubmission:**",
                f"",
            ])

            checklist_num = 1
            if self.critical_issues:
                lines.append(f"**Critical (Must Fix):**")
                lines.append(f"")
                for issue in self.critical_issues:
                    lines.append(f"- [ ] {issue.category}: {issue.description[:80]}..." if len(issue.description) > 80 else f"- [ ] {issue.category}: {issue.description}")
                    checklist_num += 1
                lines.append(f"")

            if self.major_issues:
                lines.append(f"**Major (Should Fix):**")
                lines.append(f"")
                for issue in self.major_issues:
                    lines.append(f"- [ ] {issue.category}: {issue.description[:80]}..." if len(issue.description) > 80 else f"- [ ] {issue.category}: {issue.description}")
                    checklist_num += 1
                lines.append(f"")

            lines.extend([
                f"---",
                f"",
            ])

        lines.extend([
            f"## 📝 Detailed Findings",
            f"",
        ])

        if self.critical_issues:
            lines.extend([
                f"### ❗ Critical Issues (Must Fix)",
                f"",
                f"**Priority Level:** HIGHEST - These are fundamental flaws that may prevent publication.",
                f"**Action Required:** Address ALL critical issues before resubmission.",
                f"",
            ])
            for idx, issue in enumerate(self.critical_issues, 1):
                lines.extend(self._format_issue(idx, issue, "CRITICAL"))

        if self.major_issues:
            lines.extend([
                f"### ⚠️ Major Issues (Should Fix)",
                f"",
                f"**Priority Level:** HIGH - Significant methodological or reporting concerns.",
                f"**Action Required:** Address as many as possible to strengthen the manuscript.",
                f"",
            ])
            for idx, issue in enumerate(self.major_issues, 1):
                lines.extend(self._format_issue(idx, issue, "MAJOR"))

        if self.minor_issues:
            lines.extend([
                f"### ℹ️ Minor Issues (Recommended)",
                f"",
                f"**Priority Level:** MODERATE - Improvements that enhance manuscript quality.",
                f"**Action Required:** Consider addressing to improve overall clarity and completeness.",
                f"",
            ])
            for idx, issue in enumerate(self.minor_issues, 1):
                lines.extend(self._format_issue(idx, issue, "MINOR"))

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

    def _format_issue(self, number: int, issue: IssueItem, priority: str = "MAJOR") -> List[str]:
        """Format a single issue for markdown output with enhanced actionability"""
        priority_icons = {
            "CRITICAL": "🔴",
            "MAJOR": "🟡",
            "MINOR": "🔵"
        }

        lines = [
            f"#### {priority_icons.get(priority, '🔵')} {number}. {issue.category}",
            f"",
            f"**Checklist Item:** {issue.checklist_reference}",
            f"",
            f"**Issue Identified:** {issue.description}",
            f"",
        ]

        if issue.evidence:
            lines.append(f"**Current Status in Manuscript:**")
            for evidence in issue.evidence:
                lines.append(f"> {evidence}")
            lines.append(f"")

        lines.extend([
            f"**✏️ How to Fix:** {issue.recommendation}",
            f"",
            f"---",
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

    # Quantitative scoring (0-100)
    overall_quality_score: float = Field(
        default=0.0,
        description="Overall manuscript quality score (0-100). >=80: Excellent, 60-79: Good, 40-59: Fair, <40: Poor"
    )
    reporting_completeness_score: float = Field(
        default=0.0,
        description="Reporting standard compliance score (0-100)"
    )
    methodological_rigor_score: float = Field(
        default=0.0,
        description="Methodological quality score (0-100)"
    )

    # Alerts
    security_alerts: List[str] = Field(default_factory=list)

    # Disclaimer
    disclaimer: str = Field(
        default="This report was generated with AI assistance for pre-screening purposes only. Final editorial decisions should be based on comprehensive peer review."
    )

    def _score_to_rating(self, score: float) -> str:
        """Convert numerical score to qualitative rating"""
        if score >= 80:
            return "⭐ Excellent"
        elif score >= 60:
            return "✓ Good"
        elif score >= 40:
            return "△ Fair"
        else:
            return "✗ Poor"

    def _get_recommendation_explanation(self) -> str:
        """Provide explanation for the recommendation"""
        explanations = {
            "REJECT": "**Rationale:** Critical methodological flaws or ethical concerns identified. Manuscript requires substantial redesign before resubmission.",
            "MAJOR_REVISION": "**Rationale:** Significant issues found that require major revision. Authors should address all critical and major issues before resubmission.",
            "MINOR_REVISION": "**Rationale:** Manuscript is generally sound but requires minor improvements. Address all flagged issues to meet publication standards.",
            "SEND_FOR_REVIEW": "**Rationale:** Manuscript meets basic quality standards and reporting guidelines. Suitable for peer review process."
        }
        return explanations.get(self.recommendation, "")

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
            f"## 📊 Quantitative Assessment",
            f"",
            f"| Metric | Score | Rating |",
            f"|--------|-------|--------|",
            f"| **Overall Quality** | **{self.overall_quality_score:.1f}/100** | **{self._score_to_rating(self.overall_quality_score)}** |",
            f"| Reporting Completeness | {self.reporting_completeness_score:.1f}/100 | {self._score_to_rating(self.reporting_completeness_score)} |",
            f"| Methodological Rigor | {self.methodological_rigor_score:.1f}/100 | {self._score_to_rating(self.methodological_rigor_score)} |",
            f"",
            f"**Issues Summary:** {self.total_issues} total ({self.critical_count} critical, {self.major_count} major, {self.minor_count} minor)",
            f"",
            f"---",
            f"",
            f"## ✅ Decision Recommendation",
            f"",
            f"### **{self.recommendation}**",
            f"",
            f"{self._get_recommendation_explanation()}",
            f"",
            f"---",
            f"",
            f"## 📝 Executive Summary",
            f"",
            f"{self.executive_summary}",
            f"",
            f"---",
            f"",
            f"## ⚠️ Risk Assessment",
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
