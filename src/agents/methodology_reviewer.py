"""
Methodology Reviewer Agent - Concurrent rubric block execution
"""
import time
from typing import List, Optional
import json

from ..schemas.document_ir import DocumentIR, EvidenceMap
from ..schemas.rubric import RubricBlock, RubricItem, RubricItemOutputSchema, BlockReviewResult, ItemStatus, SeverityLevel
from ..services.llm_gateway import LLMGateway, ModelTier


class MethodologyReviewerAgent:
    """
    Stateless agent for executing methodology review of a rubric block.

    Each instance processes ONE rubric block containing 5-8 related evaluation items.
    Multiple instances run concurrently for different blocks.
    """

    def __init__(self, llm_gateway: LLMGateway):
        self.llm = llm_gateway

    async def review_block(
        self,
        rubric_block: RubricBlock,
        document_ir: DocumentIR,
        evidence_map: EvidenceMap
    ) -> BlockReviewResult:
        """
        Review a single rubric block.

        Args:
            rubric_block: Block of related rubric items to evaluate
            document_ir: Structured manuscript representation
            evidence_map: Index for fast evidence lookup

        Returns:
            BlockReviewResult containing evaluation of all items in the block
        """
        start_time = time.time()
        results: List[RubricItemOutputSchema] = []
        errors: List[str] = []

        # Process each item in the block
        for item in rubric_block.items:
            try:
                result = await self._evaluate_item(item, document_ir, evidence_map)
                results.append(result)
            except Exception as e:
                # Record error but continue with other items
                error_msg = f"Failed to evaluate {item.item_id}: {str(e)}"
                errors.append(error_msg)

                # Add a failed result
                results.append(RubricItemOutputSchema(
                    item_id=item.item_id,
                    status=ItemStatus.EXECUTION_FAILED,
                    score=0,
                    severity=SeverityLevel.NONE,
                    confidence_score=0.0
                ))

        execution_time = time.time() - start_time

        return BlockReviewResult(
            block_id=rubric_block.block_id,
            block_name=rubric_block.block_name,
            results=results,
            execution_time_seconds=execution_time,
            error_log=errors
        )

    async def _evaluate_item(
        self,
        item: RubricItem,
        document_ir: DocumentIR,
        evidence_map: EvidenceMap
    ) -> RubricItemOutputSchema:
        """Evaluate a single rubric item"""

        # Build context from evidence map
        evidence_hints = self._get_evidence_context(item, document_ir, evidence_map)

        # Build evaluation prompt
        prompt = self._build_evaluation_prompt(item, evidence_hints)

        # Call LLM with JSON response format
        try:
            result = await self.llm.call_with_json_response(
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert medical manuscript reviewer. Evaluate the manuscript against specific reporting criteria with precision and provide evidence-based judgments."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                model_tier=ModelTier.STANDARD,  # Use standard model for focused tasks
                temperature=0.2,
                max_tokens=2000
            )

            # Parse and validate response
            evaluation = result["parsed_json"]
            return self._parse_evaluation_response(item, evaluation)

        except Exception as e:
            raise RuntimeError(f"LLM evaluation failed for {item.item_id}: {str(e)}")

    def _get_evidence_context(
        self,
        item: RubricItem,
        document_ir: DocumentIR,
        evidence_map: EvidenceMap
    ) -> str:
        """
        Extract relevant text context for evaluation.

        Uses evidence_location_hint to focus on the right section of DocumentIR.
        """
        hint = item.evidence_location_hint
        context_parts = []

        try:
            # Parse the hint to navigate DocumentIR
            # Examples: "methods.randomization", "results.outcomes", "abstract"

            if "." in hint:
                # Navigate nested structure
                parts = hint.split(".")
                current = document_ir

                for part in parts:
                    if hasattr(current, part):
                        current = getattr(current, part)
                    else:
                        break

                # Extract text
                if hasattr(current, "text") and isinstance(current.text, list):
                    context_parts.extend(current.text)
                elif isinstance(current, list):
                    context_parts.extend(current)

            else:
                # Top-level section
                if hasattr(document_ir, hint):
                    section = getattr(document_ir, hint)
                    if hasattr(section, "text") and isinstance(section.text, list):
                        context_parts.extend(section.text)

        except Exception:
            # If navigation fails, return empty context
            pass

        # Join context with clear separation
        context = "\n\n".join(context_parts) if context_parts else "[No relevant text found in specified location]"

        # Limit context length
        if len(context) > 3000:
            context = context[:3000] + "... [truncated]"

        return context

    def _build_evaluation_prompt(self, item: RubricItem, evidence_context: str) -> str:
        """Build prompt for evaluating a single rubric item"""
        return f"""
Evaluate the following manuscript excerpt against a specific reporting criterion.

**CRITERION TO EVALUATE:**
- **Checklist:** {item.checklist_name}
- **Item {item.item_number}:** {item.question}
- **Evaluation Standard:** {item.evaluation_criteria}

**RELEVANT MANUSCRIPT TEXT:**
{evidence_context}

**YOUR TASK:**
Evaluate whether the manuscript adequately addresses this criterion. Provide your assessment in JSON format:

{{
  "score": <0, 1, or 2>,
  // 0 = Not met (information missing or inadequate)
  // 1 = Partially met (some information present but incomplete)
  // 2 = Fully met (criterion completely satisfied)

  "severity": "<CRITICAL|MAJOR|MINOR|NONE>",
  // CRITICAL = Fatal flaw that invalidates study
  // MAJOR = Significant concern affecting interpretation
  // MINOR = Minor issue that should be addressed
  // NONE = No issues (score=2)

  "evidence_quote": ["exact quote 1", "exact quote 2"],
  // Direct quotes from the text that support your judgment
  // Use empty array [] if score=0 (no evidence found)

  "evidence_location": ["location1", "location2"],
  // Indicate where evidence was found (e.g., "methods.randomization.text[0]")
  // Use empty array [] if score=0

  "missing_detail": "specific missing information",
  // For score < 2: What exactly is missing or inadequate?
  // Use null if score=2

  "risk_reason": "why this matters",
  // For score < 2: Why does this deficiency introduce bias or reduce quality?
  // Use null if score=2

  "actionable_fix": "concrete recommendation",
  // For score < 2: Specific, actionable guidance for authors to fix the issue
  // Use null if score=2

  "confidence_score": <0.0 to 1.0>
  // Your confidence in this judgment
}}

**IMPORTANT:**
- Be evidence-based: Only cite text that actually appears above
- Be precise: Quote exact phrases, don't paraphrase
- Be fair: If information is present but in a different section, give credit
- Be consistent: Apply the evaluation standard uniformly
"""

    def _parse_evaluation_response(self, item: RubricItem, evaluation: dict) -> RubricItemOutputSchema:
        """Parse LLM response into RubricItemOutputSchema"""

        # Map severity string to enum if needed
        severity_str = evaluation.get("severity", "NONE")
        if isinstance(severity_str, str):
            severity = SeverityLevel[severity_str]
        else:
            severity = severity_str

        return RubricItemOutputSchema(
            item_id=item.item_id,
            status=ItemStatus.COMPLETED,
            score=evaluation.get("score", 0),
            severity=severity,
            evidence_quote=evaluation.get("evidence_quote", []),
            evidence_location=evaluation.get("evidence_location", []),
            missing_detail=evaluation.get("missing_detail"),
            risk_reason=evaluation.get("risk_reason"),
            actionable_fix=evaluation.get("actionable_fix"),
            confidence_score=evaluation.get("confidence_score", 0.9)
        )
