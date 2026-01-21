"""
Main Review Orchestrator - End-to-end manuscript review pipeline
"""
import asyncio
import uuid
from typing import Tuple
from pathlib import Path

from .schemas.review_state import ReviewState, JobStatus
from .schemas.reports import AuthorReport, EditorReport
from .services.document_parser import DocumentParser
from .services.llm_gateway import LLMGateway, LLMProvider
from .agents.document_analyzer import DocumentAnalyzerAgent
from .agents.integrity_guard import IntegrityEthicsGuard
from .agents.rubric_orchestrator import RubricOrchestrator
from .agents.methodology_reviewer import MethodologyReviewerAgent
from .agents.statistician_reviewer import StatisticianReviewerAgent
from .agents.editor_synthesizer import EditorSynthesizerAgent
from .utils.rubric_loader import RubricLoader


class ReviewOrchestrator:
    """
    Main orchestrator for the end-to-end manuscript review pipeline.

    Coordinates all agents and implements the complete workflow:
    1. Document parsing and cleaning
    2. Structured IR generation (Document Analyzer)
    3. Security and ethics checks (Integrity Guard)
    4. Rubric orchestration
    5. Concurrent methodology review
    6. Statistical review
    7. Report synthesis (Editor Synthesizer)
    """

    def __init__(
        self,
        llm_api_key: str = None,
        llm_provider: str = "openai",
        rubrics_dir: str = None
    ):
        """
        Initialize the review orchestrator.

        Args:
            llm_api_key: API key for LLM provider
            llm_provider: LLM provider ("openai" or "anthropic")
            rubrics_dir: Custom directory for rubric files (optional)
        """
        # Initialize services
        provider = LLMProvider.OPENAI if llm_provider == "openai" else LLMProvider.ANTHROPIC
        self.llm_gateway = LLMGateway(provider=provider, api_key=llm_api_key)
        self.document_parser = DocumentParser()
        self.rubric_loader = RubricLoader(rubrics_dir)

        # Initialize agents
        self.document_analyzer = DocumentAnalyzerAgent(self.llm_gateway)
        self.integrity_guard = IntegrityEthicsGuard()
        self.rubric_orchestrator = RubricOrchestrator(self.rubric_loader)
        self.editor_synthesizer = EditorSynthesizerAgent(self.llm_gateway)

    async def review_manuscript(
        self,
        manuscript_path: str,
        job_id: str = None
    ) -> Tuple[ReviewState, AuthorReport, EditorReport]:
        """
        Execute complete review pipeline for a manuscript.

        Args:
            manuscript_path: Path to the manuscript file (.docx, .pdf, .txt)
            job_id: Optional job ID (will be generated if not provided)

        Returns:
            Tuple of (ReviewState, AuthorReport, EditorReport)
        """
        # Initialize job
        if job_id is None:
            job_id = str(uuid.uuid4())

        review_state = ReviewState(
            job_id=job_id,
            manuscript_path=manuscript_path,
            status=JobStatus.PENDING
        )

        try:
            # ============================================================
            # STAGE 1: Document Parsing and Cleaning
            # ============================================================
            print(f"\n[{job_id}] Stage 1/6: Parsing document...")
            review_state.status = JobStatus.PARSING
            review_state.update_progress()

            manuscript_text, metadata = self.document_parser.parse(manuscript_path)

            # ============================================================
            # STAGE 2: Structured IR Generation + Study Type ID
            # ============================================================
            print(f"[{job_id}] Stage 2/6: Analyzing manuscript structure...")

            document_ir, study_profile, evidence_map = await self.document_analyzer.analyze(
                manuscript_text
            )

            review_state.document_ir = document_ir
            review_state.study_profile = study_profile
            review_state.evidence_map = evidence_map

            print(f"  → Identified study types: {', '.join(study_profile.study_types)}")

            # ============================================================
            # STAGE 3: Security and Ethics Checks (Concurrent with next stage)
            # ============================================================
            print(f"[{job_id}] Stage 3/6: Running security and ethics checks...")

            security_alerts = await self.integrity_guard.check(manuscript_text)
            review_state.security_alerts = security_alerts

            if security_alerts:
                print(f"  → Found {len(security_alerts)} security/ethics alerts")
                for alert in security_alerts:
                    if alert.severity == "CRITICAL":
                        print(f"     ⚠️  CRITICAL: {alert.alert_type.value}")

            # ============================================================
            # STAGE 4: Rubric Orchestration
            # ============================================================
            print(f"[{job_id}] Stage 4/6: Orchestrating rubrics...")

            rubric_blocks = self.rubric_orchestrator.orchestrate(study_profile)
            review_state.orchestration.rubric_blocks = rubric_blocks
            review_state.orchestration.total_blocks = len(rubric_blocks)

            print(f"  → Created {len(rubric_blocks)} review blocks")

            # ============================================================
            # STAGE 5: Concurrent Review Execution
            # ============================================================
            print(f"[{job_id}] Stage 5/6: Executing concurrent reviews...")
            review_state.status = JobStatus.REVIEWING
            review_state.update_progress()

            # Create concurrent tasks for all rubric blocks
            review_tasks = []
            for block in rubric_blocks:
                methodology_reviewer = MethodologyReviewerAgent(self.llm_gateway)
                task = methodology_reviewer.review_block(
                    rubric_block=block,
                    document_ir=document_ir,
                    evidence_map=evidence_map
                )
                review_tasks.append(task)

            # Also run statistical review concurrently
            statistician_reviewer = StatisticianReviewerAgent(self.llm_gateway)
            stats_task = statistician_reviewer.review_statistics(
                document_ir=document_ir,
                evidence_map=evidence_map
            )
            review_tasks.append(stats_task)

            # Execute all reviews concurrently
            print(f"  → Running {len(review_tasks)} concurrent review tasks...")
            review_results = await asyncio.gather(*review_tasks, return_exceptions=True)

            # Filter out exceptions and collect successful results
            successful_results = []
            for i, result in enumerate(review_results):
                if isinstance(result, Exception):
                    print(f"     ⚠️  Block {i+1} failed: {str(result)}")
                    review_state.add_error("3005", f"Block {i+1} execution failed", {"error": str(result)})
                else:
                    successful_results.append(result)
                    review_state.review_results[result.block_id] = result
                    review_state.orchestration.completed_blocks += 1
                    print(f"     ✓ Completed block: {result.block_name} ({result.execution_time_seconds:.1f}s)")

            review_state.update_progress()

            # ============================================================
            # STAGE 6: Report Synthesis
            # ============================================================
            print(f"[{job_id}] Stage 6/6: Synthesizing final reports...")
            review_state.status = JobStatus.SYNTHESIZING
            review_state.update_progress()

            # Get list of checklists that were actually applied
            checklists_applied = list(set(
                item.checklist_name
                for block in rubric_blocks
                for item in block.items
            ))

            author_report, editor_report = await self.editor_synthesizer.synthesize(
                job_id=job_id,
                manuscript_title=document_ir.title or Path(manuscript_path).stem,
                study_types=study_profile.study_types,
                checklists_applied=checklists_applied,
                review_results=successful_results,
                security_alerts=security_alerts
            )

            # Store reports in review state
            review_state.final_reports["author_report"] = author_report.to_markdown()
            review_state.final_reports["editor_report"] = editor_report.to_markdown()

            # ============================================================
            # COMPLETION
            # ============================================================
            review_state.status = JobStatus.COMPLETED
            review_state.update_progress()

            print(f"\n[{job_id}] ✅ Review completed successfully!")
            print(f"  → Total issues found: {author_report.total_issues}")
            print(f"  → Critical: {len(author_report.critical_issues)}, Major: {len(author_report.major_issues)}, Minor: {len(author_report.minor_issues)}")
            print(f"  → Editor recommendation: {editor_report.recommendation}")

            return review_state, author_report, editor_report

        except Exception as e:
            # Handle failures
            review_state.status = JobStatus.FAILED
            review_state.add_error("9001", "Review pipeline failed", {"error": str(e)})
            print(f"\n[{job_id}] ❌ Review failed: {str(e)}")
            raise


async def main():
    """Example usage of the review orchestrator"""
    import os
    import sys

    # Get API key from environment
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
    provider = "openai" if os.getenv("OPENAI_API_KEY") else "anthropic"

    if not api_key:
        print("Error: Please set OPENAI_API_KEY or ANTHROPIC_API_KEY environment variable")
        sys.exit(1)

    # Check if manuscript path provided
    if len(sys.argv) < 2:
        print("Usage: python -m src.main <path_to_manuscript>")
        print("Example: python -m src.main /path/to/paper.pdf")
        sys.exit(1)

    manuscript_path = sys.argv[1]

    # Initialize orchestrator
    orchestrator = ReviewOrchestrator(
        llm_api_key=api_key,
        llm_provider=provider
    )

    # Run review
    review_state, author_report, editor_report = await orchestrator.review_manuscript(
        manuscript_path=manuscript_path
    )

    # Save reports
    output_dir = Path("./review_output")
    output_dir.mkdir(exist_ok=True)

    author_report_path = output_dir / f"{review_state.job_id}_author_report.md"
    editor_report_path = output_dir / f"{review_state.job_id}_editor_report.md"

    with open(author_report_path, "w", encoding="utf-8") as f:
        f.write(author_report.to_markdown())

    with open(editor_report_path, "w", encoding="utf-8") as f:
        f.write(editor_report.to_markdown())

    print(f"\n📄 Reports saved:")
    print(f"  → Author report: {author_report_path}")
    print(f"  → Editor report: {editor_report_path}")


if __name__ == "__main__":
    asyncio.run(main())
