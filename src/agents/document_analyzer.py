"""
Document Analyzer Agent - Converts raw manuscript text to structured DocumentIR
"""
import json
import re
from typing import Tuple, Dict, Any, List
from jsonschema import validate, ValidationError

from ..schemas.document_ir import (
    DocumentIR, StudyProfile, EvidenceMap,
    SectionText, MethodsSection, ResultsSection, DiscussionSection,
    RECOGNIZED_STUDY_TYPES
)
from ..services.llm_gateway import LLMGateway, ModelTier


class DocumentAnalyzerAgent:
    """
    Agent responsible for converting raw manuscript text into structured DocumentIR.

    This is a critical optimization point - it performs ALL of these tasks in a SINGLE LLM call:
    1. Section segmentation (Title, Abstract, Methods, Results, etc.)
    2. Structured information extraction
    3. Study type multi-label classification
    4. Evidence map preparation
    """

    def __init__(self, llm_gateway: LLMGateway):
        self.llm = llm_gateway

    async def analyze(self, manuscript_text: str) -> Tuple[DocumentIR, StudyProfile, EvidenceMap]:
        """
        Perform all-in-one analysis of manuscript.

        Args:
            manuscript_text: Raw text extracted from manuscript file

        Returns:
            Tuple of (DocumentIR, StudyProfile, EvidenceMap)
        """
        # Build the comprehensive prompt for all-in-one extraction
        prompt = self._build_analysis_prompt(manuscript_text)

        # Single LLM call for everything
        try:
            result = await self.llm.call_with_json_response(
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert medical manuscript analyzer. Extract structured information from manuscripts with high precision. CRITICAL: Correctly distinguish between review articles (Systematic Review, Meta-Analysis, Narrative Review, etc.) and original research studies (RCT, Cohort, Case-Control, etc.). Review articles synthesize existing literature and should NEVER be classified as observational or interventional studies."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                model_tier=ModelTier.ADVANCED,  # Use advanced model for this critical task
                temperature=0.1,  # Low temperature for consistency
                max_tokens=8000
            )

            # Parse the JSON response
            analysis = result["parsed_json"]

            # Convert to structured objects
            document_ir = self._build_document_ir(analysis)
            study_profile = self._build_study_profile(analysis)
            evidence_map = self._build_evidence_map(document_ir, manuscript_text)

            return document_ir, study_profile, evidence_map

        except Exception as e:
            raise RuntimeError(f"Document analysis failed: {str(e)}")

    def _build_analysis_prompt(self, manuscript_text: str) -> str:
        """Build comprehensive prompt for all-in-one extraction"""
        return f"""
Analyze the following medical research manuscript and extract structured information.

MANUSCRIPT TEXT:
{manuscript_text[:25000]}

TASK: Extract the following information and return as JSON:

1. **Section Segmentation**: Identify and extract text for these sections:
   - title (string)
   - abstract (array of paragraph strings)
   - keywords (array of strings)
   - introduction (array of paragraph strings)
   - methods (object with subsections):
     - study_design
     - participants
     - eligibility
     - randomization
     - blinding
     - interventions
     - outcomes
     - sample_size
     - statistics
     - ethics
     - model_development (if applicable)
     - model_validation (if applicable)
   - results (object with subsections):
     - participant_flow
     - baseline
     - outcomes
     - adverse_events
   - discussion (object with subsections):
     - limitations
     - generalizability
     - interpretation
   - references (array of reference strings)

2. **Study Type Classification** (multi-label): Identify ALL applicable study types from this list:
{', '.join(RECOGNIZED_STUDY_TYPES)}

CRITICAL GUIDELINES for study type identification:
- **Review Articles**: If the paper primarily reviews and synthesizes existing literature (rather than collecting original data):
  * "Systematic Review": Has systematic search strategy, PRISMA-like methodology, explicit inclusion/exclusion criteria
  * "Meta-Analysis": Includes quantitative synthesis with pooled effect sizes, forest plots
  * "Narrative Review": Traditional review without systematic search methodology
  * "Literature Review": General term for non-systematic reviews
  * "Scoping Review": Maps the literature on a broad topic
  * "Umbrella Review": Review of reviews

- **Original Research**: If the paper collects and analyzes new data:
  * "RCT": Randomized controlled trial with intervention assignment
  * "Cohort Study": Follows participants over time
  * "Case-Control Study": Compares cases with disease to controls
  * "Cross-Sectional Study": Single time point observational study

- **DO NOT** classify a review article as "Observational Study", "Cohort Study", or "RCT"
- A paper can have multiple types (e.g., "Systematic Review" + "Meta-Analysis")

3. **Key Metadata**: Extract:
   - primary_outcome
   - secondary_outcomes (array)
   - sample_size
   - sample_size_calculation
   - statistical_methods (array)
   - registration_id (e.g., NCT number)
   - funding_source
   - conflicts_of_interest

Return JSON in this exact format:
{{
  "sections": {{
    "title": "...",
    "abstract": ["para1", "para2"],
    "keywords": ["kw1", "kw2"],
    "introduction": ["para1", "para2"],
    "methods": {{
      "study_design": ["para1"],
      "participants": ["para1"],
      "eligibility": ["para1"],
      "randomization": ["para1"],
      "blinding": ["para1"],
      "interventions": ["para1"],
      "outcomes": ["para1"],
      "sample_size": ["para1"],
      "statistics": ["para1"],
      "ethics": ["para1"],
      "model_development": ["para1"],
      "model_validation": ["para1"]
    }},
    "results": {{
      "participant_flow": ["para1"],
      "baseline": ["para1"],
      "outcomes": ["para1"],
      "adverse_events": ["para1"]
    }},
    "discussion": {{
      "limitations": ["para1"],
      "generalizability": ["para1"],
      "interpretation": ["para1"]
    }},
    "references": ["ref1", "ref2"]
  }},
  "study_types": ["RCT", "AI"],
  "metadata": {{
    "primary_outcome": "...",
    "secondary_outcomes": [],
    "sample_size": "...",
    "sample_size_calculation": "...",
    "statistical_methods": [],
    "registration_id": "...",
    "funding_source": "...",
    "conflicts_of_interest": "..."
  }}
}}

IMPORTANT:
- If a section/subsection is not found, use empty array [] or empty string ""
- Be precise and extract verbatim text where possible
- For study_types, include ALL that apply (it's multi-label)
- Focus on accuracy over completeness
"""

    def _build_document_ir(self, analysis: Dict[str, Any]) -> DocumentIR:
        """Build DocumentIR from parsed analysis"""
        sections = analysis.get("sections", {})

        # Build methods section
        methods_data = sections.get("methods", {})
        methods = MethodsSection(
            study_design=SectionText(text=methods_data.get("study_design", [])),
            participants=SectionText(text=methods_data.get("participants", [])),
            eligibility=SectionText(text=methods_data.get("eligibility", [])),
            randomization=SectionText(text=methods_data.get("randomization", [])),
            blinding=SectionText(text=methods_data.get("blinding", [])),
            interventions=SectionText(text=methods_data.get("interventions", [])),
            outcomes=SectionText(text=methods_data.get("outcomes", [])),
            sample_size=SectionText(text=methods_data.get("sample_size", [])),
            statistics=SectionText(text=methods_data.get("statistics", [])),
            ethics=SectionText(text=methods_data.get("ethics", [])),
            model_development=SectionText(text=methods_data.get("model_development", [])),
            model_validation=SectionText(text=methods_data.get("model_validation", []))
        )

        # Build results section
        results_data = sections.get("results", {})
        results = ResultsSection(
            participant_flow=SectionText(text=results_data.get("participant_flow", [])),
            baseline=SectionText(text=results_data.get("baseline", [])),
            outcomes=SectionText(text=results_data.get("outcomes", [])),
            adverse_events=SectionText(text=results_data.get("adverse_events", []))
        )

        # Build discussion section
        discussion_data = sections.get("discussion", {})
        discussion = DiscussionSection(
            limitations=SectionText(text=discussion_data.get("limitations", [])),
            generalizability=SectionText(text=discussion_data.get("generalizability", [])),
            interpretation=SectionText(text=discussion_data.get("interpretation", []))
        )

        # Build DocumentIR
        document_ir = DocumentIR(
            title=sections.get("title", ""),
            abstract=SectionText(text=sections.get("abstract", [])),
            keywords=sections.get("keywords", []),
            introduction=SectionText(text=sections.get("introduction", [])),
            methods=methods,
            results=results,
            discussion=discussion,
            references=sections.get("references", []),
            extracted_info=analysis.get("metadata", {})
        )

        return document_ir

    def _build_study_profile(self, analysis: Dict[str, Any]) -> StudyProfile:
        """Build StudyProfile from parsed analysis"""
        return StudyProfile(
            study_types=analysis.get("study_types", []),
            metadata=analysis.get("metadata", {})
        )

    def _build_evidence_map(self, document_ir: DocumentIR, original_text: str) -> EvidenceMap:
        """
        Build evidence map by indexing key medical terms to their locations in DocumentIR.

        This is a simplified version - in production, you'd use more sophisticated
        medical NER and concept extraction.
        """
        term_locations: Dict[str, List[str]] = {}

        # Key medical terms to index
        key_terms = [
            "p-value", "p value", "confidence interval", "CI", "hazard ratio", "odds ratio",
            "randomization", "randomisation", "random sequence", "allocation concealment",
            "blinding", "masking", "double-blind", "single-blind",
            "informed consent", "ethics committee", "IRB", "institutional review board",
            "sample size", "power calculation", "statistical significance",
            "primary outcome", "secondary outcome", "endpoint",
            "intention-to-treat", "ITT", "per-protocol",
            "adverse event", "serious adverse event", "SAE",
            "sensitivity", "specificity", "AUC", "ROC",
            "regression", "logistic regression", "cox regression",
            "machine learning", "deep learning", "neural network", "random forest",
            "validation", "external validation", "internal validation", "cross-validation",
            "CONSORT", "PRISMA", "STROBE", "TRIPOD"
        ]

        # Search in methods section
        self._index_section(term_locations, document_ir.methods.randomization.text, "methods.randomization", key_terms)
        self._index_section(term_locations, document_ir.methods.blinding.text, "methods.blinding", key_terms)
        self._index_section(term_locations, document_ir.methods.statistics.text, "methods.statistics", key_terms)
        self._index_section(term_locations, document_ir.methods.ethics.text, "methods.ethics", key_terms)
        self._index_section(term_locations, document_ir.methods.sample_size.text, "methods.sample_size", key_terms)
        self._index_section(term_locations, document_ir.methods.outcomes.text, "methods.outcomes", key_terms)

        # Search in results section
        self._index_section(term_locations, document_ir.results.outcomes.text, "results.outcomes", key_terms)
        self._index_section(term_locations, document_ir.results.adverse_events.text, "results.adverse_events", key_terms)

        # Search in discussion
        self._index_section(term_locations, document_ir.discussion.limitations.text, "discussion.limitations", key_terms)

        return EvidenceMap(term_locations=term_locations)

    def _index_section(
        self,
        term_locations: Dict[str, List[str]],
        paragraphs: List[str],
        section_path: str,
        key_terms: List[str]
    ):
        """Index key terms in a section"""
        for idx, para in enumerate(paragraphs):
            para_lower = para.lower()
            for term in key_terms:
                if term.lower() in para_lower:
                    location = f"{section_path}.text[{idx}]"
                    if term.lower() not in term_locations:
                        term_locations[term.lower()] = []
                    if location not in term_locations[term.lower()]:
                        term_locations[term.lower()].append(location)
