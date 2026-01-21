"""
Editor Synthesizer Agent - Final report generation and synthesis
"""
from typing import List, Dict
from collections import defaultdict

from ..schemas.rubric import BlockReviewResult, RubricItemOutputSchema, SeverityLevel
from ..schemas.reports import AuthorReport, EditorReport, IssueItem
from ..schemas.review_state import SecurityAlert
from ..services.llm_gateway import LLMGateway, ModelTier


class EditorSynthesizerAgent:
    """
    Final synthesis agent that aggregates all review results and generates reports.

    This is the ONLY serial bottleneck after concurrent review completion.
    Uses the most advanced LLM for high-quality report generation.
    """

    def __init__(self, llm_gateway: LLMGateway):
        self.llm = llm_gateway

    async def synthesize(
        self,
        job_id: str,
        manuscript_title: str,
        study_types: List[str],
        checklists_applied: List[str],
        review_results: List[BlockReviewResult],
        security_alerts: List[SecurityAlert]
    ) -> tuple[AuthorReport, EditorReport]:
        """
        Synthesize all review results into final reports.

        Args:
            job_id: Unique job identifier
            manuscript_title: Title of the manuscript
            study_types: Identified study methodology types
            checklists_applied: Names of checklists that were applied
            review_results: Results from all reviewer agents
            security_alerts: Security and ethics alerts

        Returns:
            Tuple of (AuthorReport, EditorReport)
        """
        # Step 1: Aggregate and deduplicate all findings
        all_findings = self._aggregate_findings(review_results)

        # Step 2: Deduplicate and merge similar issues
        unique_findings = self._deduplicate_findings(all_findings)

        # Step 3: Categorize by severity
        critical_findings = [f for f in unique_findings if f.severity == SeverityLevel.CRITICAL]
        major_findings = [f for f in unique_findings if f.severity == SeverityLevel.MAJOR]
        minor_findings = [f for f in unique_findings if f.severity == SeverityLevel.MINOR]

        # Step 4: Generate Author Report (detailed, constructive)
        author_report = await self._generate_author_report(
            job_id=job_id,
            manuscript_title=manuscript_title,
            checklists_applied=checklists_applied,
            critical_findings=critical_findings,
            major_findings=major_findings,
            minor_findings=minor_findings
        )

        # Step 5: Generate Editor Report (concise, decision-focused)
        editor_report = await self._generate_editor_report(
            job_id=job_id,
            manuscript_title=manuscript_title,
            study_types=study_types,
            checklists_applied=checklists_applied,
            critical_findings=critical_findings,
            major_findings=major_findings,
            minor_findings=minor_findings,
            security_alerts=security_alerts
        )

        return author_report, editor_report

    def _aggregate_findings(self, review_results: List[BlockReviewResult]) -> List[RubricItemOutputSchema]:
        """Collect all findings from all review blocks"""
        all_findings = []

        for block_result in review_results:
            for item_result in block_result.results:
                # Only include findings that are not fully met (score < 2)
                if item_result.score < 2 and item_result.severity != SeverityLevel.NONE:
                    all_findings.append(item_result)

        return all_findings

    def _deduplicate_findings(self, findings: List[RubricItemOutputSchema]) -> List[RubricItemOutputSchema]:
        """
        Remove duplicate findings.

        In production, this would use more sophisticated similarity detection.
        For now, we just deduplicate by item_id.
        """
        seen_ids = set()
        unique = []

        for finding in findings:
            if finding.item_id not in seen_ids:
                unique.append(finding)
                seen_ids.add(finding.item_id)

        return unique

    async def _generate_author_report(
        self,
        job_id: str,
        manuscript_title: str,
        checklists_applied: List[str],
        critical_findings: List[RubricItemOutputSchema],
        major_findings: List[RubricItemOutputSchema],
        minor_findings: List[RubricItemOutputSchema]
    ) -> AuthorReport:
        """Generate detailed author-facing report with constructive feedback"""

        # Convert findings to IssueItems
        critical_issues = [self._finding_to_issue(f) for f in critical_findings]
        major_issues = [self._finding_to_issue(f) for f in major_findings]
        minor_issues = [self._finding_to_issue(f) for f in minor_findings]

        total_issues = len(critical_issues) + len(major_issues) + len(minor_issues)

        # Use LLM to generate polished introduction and conclusion if there are issues
        if total_issues > 0:
            summary_prompt = self._build_author_summary_prompt(
                manuscript_title,
                critical_issues,
                major_issues,
                minor_issues
            )

            try:
                result = await self.llm.call_with_retry(
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a constructive, supportive academic editor helping authors improve their manuscript."
                        },
                        {
                            "role": "user",
                            "content": summary_prompt
                        }
                    ],
                    model_tier=ModelTier.ADVANCED,
                    temperature=0.5,
                    max_tokens=1000
                )

                intro_and_conclusion = result["content"]
                # Parse into intro and conclusion (simple split for now)
                parts = intro_and_conclusion.split("---CONCLUSION---")
                introduction = parts[0].strip() if parts else AuthorReport.__fields__["introduction"].default
                conclusion = parts[1].strip() if len(parts) > 1 else AuthorReport.__fields__["conclusion"].default

            except Exception:
                # Fallback to defaults
                introduction = AuthorReport.__fields__["introduction"].default
                conclusion = AuthorReport.__fields__["conclusion"].default
        else:
            introduction = "Congratulations! Our automated pre-review found no significant issues with your manuscript."
            conclusion = "Your manuscript appears to meet all major reporting standards. Good luck with peer review!"

        return AuthorReport(
            job_id=job_id,
            manuscript_title=manuscript_title,
            critical_issues=critical_issues,
            major_issues=major_issues,
            minor_issues=minor_issues,
            total_issues=total_issues,
            checklists_applied=checklists_applied,
            introduction=introduction,
            conclusion=conclusion
        )

    async def _generate_editor_report(
        self,
        job_id: str,
        manuscript_title: str,
        study_types: List[str],
        checklists_applied: List[str],
        critical_findings: List[RubricItemOutputSchema],
        major_findings: List[RubricItemOutputSchema],
        minor_findings: List[RubricItemOutputSchema],
        security_alerts: List[SecurityAlert]
    ) -> EditorReport:
        """Generate concise editor-facing report with decision recommendation"""

        # Determine recommendation based on findings
        recommendation = self._determine_recommendation(
            len(critical_findings),
            len(major_findings),
            security_alerts
        )

        # Generate executive summary using LLM
        summary_prompt = self._build_editor_summary_prompt(
            manuscript_title,
            recommendation,
            critical_findings,
            major_findings
        )

        try:
            result = await self.llm.call_with_retry(
                messages=[
                    {
                        "role": "system",
                        "content": "You are a senior journal editor writing a concise pre-review assessment."
                    },
                    {
                        "role": "user",
                        "content": summary_prompt
                    }
                ],
                model_tier=ModelTier.ADVANCED,
                temperature=0.4,
                max_tokens=500
            )

            executive_summary = result["content"]

        except Exception:
            # Fallback summary
            executive_summary = f"Manuscript identified as {', '.join(study_types)}. Found {len(critical_findings)} critical and {len(major_findings)} major methodological issues."

        # Extract risk summaries
        critical_risks = [f"{f.item_id}: {f.risk_reason}" for f in critical_findings if f.risk_reason][:5]
        major_risks = [f"{f.item_id}: {f.risk_reason}" for f in major_findings if f.risk_reason][:5]

        # Security alert summaries
        security_alert_texts = [f"{a.alert_type.value}: {a.evidence[:100]}" for a in security_alerts]

        return EditorReport(
            job_id=job_id,
            manuscript_title=manuscript_title,
            recommendation=recommendation,
            executive_summary=executive_summary,
            critical_risks=critical_risks,
            major_risks=major_risks,
            study_types_identified=study_types,
            checklists_applied=checklists_applied,
            total_issues=len(critical_findings) + len(major_findings) + len(minor_findings),
            critical_count=len(critical_findings),
            major_count=len(major_findings),
            minor_count=len(minor_findings),
            security_alerts=security_alert_texts
        )

    def _finding_to_issue(self, finding: RubricItemOutputSchema) -> IssueItem:
        """Convert RubricItemOutputSchema to IssueItem for report"""
        # Extract category from item_id (e.g., "CONSORT_8a" -> "Randomization")
        # This is a simplified version; in production, maintain a proper mapping
        category = finding.item_id.split("_")[0] if "_" in finding.item_id else "General"

        return IssueItem(
            category=category,
            severity=finding.severity,
            description=finding.missing_detail or "Issue identified",
            evidence=finding.evidence_quote,
            recommendation=finding.actionable_fix or "Please review this section.",
            checklist_reference=finding.item_id
        )

    def _determine_recommendation(
        self,
        critical_count: int,
        major_count: int,
        security_alerts: List[SecurityAlert]
    ) -> str:
        """Determine editorial recommendation based on findings"""

        # Check for critical security issues
        has_critical_security = any(a.severity == "CRITICAL" for a in security_alerts)

        if has_critical_security:
            return "REJECT"
        elif critical_count >= 3:
            return "REJECT"
        elif critical_count >= 1 or major_count >= 5:
            return "MAJOR_REVISION"
        elif major_count >= 1:
            return "MINOR_REVISION"
        else:
            return "SEND_FOR_REVIEW"

    def _build_author_summary_prompt(
        self,
        title: str,
        critical_issues: List[IssueItem],
        major_issues: List[IssueItem],
        minor_issues: List[IssueItem]
    ) -> str:
        """Build prompt for generating author report introduction and conclusion"""
        return f"""
Write a brief, constructive introduction and conclusion for an automated manuscript review report.

Manuscript: "{title}"
Issues found: {len(critical_issues)} critical, {len(major_issues)} major, {len(minor_issues)} minor

Write:
1. A warm, encouraging 2-3 sentence introduction thanking the authors and explaining the purpose of the automated review
2. Then write: ---CONCLUSION---
3. Then a brief 2-3 sentence conclusion encouraging revision and providing next steps

Tone: Professional, constructive, supportive. Not harsh or discouraging.
"""

    def _build_editor_summary_prompt(
        self,
        title: str,
        recommendation: str,
        critical_findings: List[RubricItemOutputSchema],
        major_findings: List[RubricItemOutputSchema]
    ) -> str:
        """Build prompt for generating editor executive summary"""
        findings_text = ""
        if critical_findings:
            findings_text += f"\nCritical issues: {', '.join([f.item_id for f in critical_findings[:3]])}"
        if major_findings:
            findings_text += f"\nMajor issues: {', '.join([f.item_id for f in major_findings[:3]])}"

        return f"""
Write a concise executive summary (3-4 sentences) for a journal editor about this manuscript pre-review.

Manuscript: "{title}"
Recommendation: {recommendation}
{findings_text}

Summarize the key findings and why this recommendation was made. Be objective and professional.
"""
