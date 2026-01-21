"""
Statistician Reviewer Agent - Specialized statistical methodology review
"""
from typing import List
import time

from ..schemas.document_ir import DocumentIR, EvidenceMap
from ..schemas.rubric import RubricBlock, RubricItemOutputSchema, BlockReviewResult
from ..services.llm_gateway import LLMGateway
from .methodology_reviewer import MethodologyReviewerAgent


class StatisticianReviewerAgent(MethodologyReviewerAgent):
    """
    Specialized reviewer for statistical methodology.

    Extends MethodologyReviewerAgent with statistics-focused prompts and evaluation.
    Focuses on:
    - Statistical test selection and appropriateness
    - Sample size calculations
    - Multiple comparisons handling
    - Model validation (for predictive models)
    - P-values and confidence intervals
    """

    def __init__(self, llm_gateway: LLMGateway):
        super().__init__(llm_gateway)

    async def review_statistics(
        self,
        document_ir: DocumentIR,
        evidence_map: EvidenceMap
    ) -> BlockReviewResult:
        """
        Perform specialized statistical review.

        This method focuses on extracted statistical information rather than
        processing a predefined rubric block.
        """
        start_time = time.time()

        # Extract key statistical information from DocumentIR
        stats_info = self._extract_statistical_info(document_ir)

        # Build a focused statistical review prompt
        prompt = self._build_statistics_review_prompt(stats_info)

        try:
            result = await self.llm.call_with_json_response(
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert biostatistician reviewing medical research. Evaluate statistical methodology for appropriateness, rigor, and potential issues."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                model_tier="standard",
                temperature=0.2,
                max_tokens=3000
            )

            evaluation = result["parsed_json"]
            results = self._parse_statistics_evaluation(evaluation)

            execution_time = time.time() - start_time

            return BlockReviewResult(
                block_id="statistics_review",
                block_name="Statistical_Methods_Review",
                results=results,
                execution_time_seconds=execution_time,
                error_log=[]
            )

        except Exception as e:
            execution_time = time.time() - start_time
            return BlockReviewResult(
                block_id="statistics_review",
                block_name="Statistical_Methods_Review",
                results=[],
                execution_time_seconds=execution_time,
                error_log=[f"Statistics review failed: {str(e)}"]
            )

    def _extract_statistical_info(self, document_ir: DocumentIR) -> dict:
        """Extract key statistical information from DocumentIR"""
        return {
            "sample_size": document_ir.methods.sample_size.text,
            "statistical_methods": document_ir.methods.statistics.text,
            "results_outcomes": document_ir.results.outcomes.text,
            "extracted_metadata": document_ir.extracted_info
        }

    def _build_statistics_review_prompt(self, stats_info: dict) -> str:
        """Build specialized prompt for statistical review"""
        return f"""
Review the statistical methodology of this manuscript and identify potential issues.

**SAMPLE SIZE AND POWER:**
{chr(10).join(stats_info.get("sample_size", []))}

**STATISTICAL METHODS:**
{chr(10).join(stats_info.get("statistical_methods", []))}

**RESULTS:**
{chr(10).join(stats_info.get("results_outcomes", [])[:5])}  # Limit to first 5 paragraphs

Evaluate the following aspects and return as JSON array of issues:

{{
  "issues": [
    {{
      "aspect": "<sample_size|test_selection|assumptions|multiple_comparisons|effect_sizes|confidence_intervals|model_validation>",
      "severity": "<CRITICAL|MAJOR|MINOR|NONE>",
      "description": "detailed description of the issue",
      "evidence": ["quote1", "quote2"],
      "recommendation": "specific fix"
    }}
  ]
}}

**Focus on:**
1. Sample size justification and power calculation
2. Appropriateness of statistical tests for data type and study design
3. Handling of missing data
4. Multiple comparisons correction (if applicable)
5. Reporting of effect sizes with confidence intervals
6. Model validation methods (if predictive modeling used)
7. Assumptions checking (normality, proportional hazards, etc.)
8. P-value interpretation and potential p-hacking

Return empty array if no statistical issues identified.
"""

    def _parse_statistics_evaluation(self, evaluation: dict) -> List[RubricItemOutputSchema]:
        """Parse statistics evaluation into standardized results"""
        results = []
        issues = evaluation.get("issues", [])

        for idx, issue in enumerate(issues):
            from ..schemas.rubric import ItemStatus, SeverityLevel

            result = RubricItemOutputSchema(
                item_id=f"STATS_{issue['aspect'].upper()}",
                status=ItemStatus.COMPLETED,
                score=0 if issue["severity"] != "NONE" else 2,
                severity=SeverityLevel[issue["severity"]],
                evidence_quote=issue.get("evidence", []),
                evidence_location=["methods.statistics", "results.outcomes"],
                missing_detail=issue.get("description"),
                risk_reason=f"Statistical concern regarding {issue['aspect']}",
                actionable_fix=issue.get("recommendation"),
                confidence_score=0.85
            )
            results.append(result)

        return results
