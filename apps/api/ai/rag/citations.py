# === TASK:WP-201:START ===
import re
from typing import Dict, List, Tuple

from packages.contracts.dto import CitationDTO, SearchCandidateDTO

CITATION_MARKER_RE = re.compile(r"\[\[([^\[\]]+)\]\]")
NUMBER_RE = re.compile(r"\b\d+(?::\d+)?(?:[.,]\d+)*%?")
NON_FACTUAL_PREFIXES = (
    "dưới đây là",
    "tôi có thể",
    "chào bạn",
    "xin chào",
    "tôi là",
    "bạn có thể",
    "cảm ơn",
)


def _claim_text(line: str) -> str:
    without_marker = CITATION_MARKER_RE.sub("", line)
    return re.sub(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)", "", without_marker).strip()


def _requires_citation(line: str) -> bool:
    claim = _claim_text(line)
    if not claim or len(claim.split()) < 4:
        return False
    lowered = claim.lower()
    return not (
        line.lstrip().startswith("#")
        or claim.endswith(":")
        or claim.endswith("?")
        or lowered.startswith(NON_FACTUAL_PREFIXES)
    )


def _numbers_supported(claim: str, evidence: List[SearchCandidateDTO]) -> bool:
    numbers = [number for number in NUMBER_RE.findall(claim) if len(number) > 1]
    if not numbers:
        return True
    evidence_text = "\n".join(candidate.content for candidate in evidence)
    return all(number in evidence_text for number in numbers)


def map_citations_to_response(
    response_text: str,
    candidates: List[SearchCandidateDTO],
) -> Tuple[bool, List[CitationDTO]]:
    """Validate explicit claim citations against server-owned search candidates."""
    if not response_text:
        return True, []

    candidates_by_id: Dict[str, SearchCandidateDTO] = {
        candidate.chunk_id: candidate for candidate in candidates
    }
    citations: List[CitationDTO] = []
    all_grounded = True

    for line in response_text.splitlines():
        if not _requires_citation(line):
            continue

        claim = _claim_text(line)
        cited_ids = list(dict.fromkeys(CITATION_MARKER_RE.findall(line)))
        cited_candidates = [
            candidates_by_id[chunk_id]
            for chunk_id in cited_ids
            if chunk_id in candidates_by_id
        ]

        if not cited_ids or len(cited_candidates) != len(cited_ids):
            all_grounded = False
            continue
        if not _numbers_supported(claim, cited_candidates):
            all_grounded = False
            continue

        for candidate in cited_candidates:
            citations.append(CitationDTO(
                chunk_id=candidate.chunk_id,
                source_id=candidate.source_id,
                source_path=candidate.source_path,
                source_section=candidate.sub_topic,
                source_page="",
                version=candidate.version,
                matched_text=claim,
            ))

    return all_grounded, citations


def render_citation_markers(
    response_text: str,
    citations: List[CitationDTO],
) -> str:
    """Replace internal chunk markers with stable user-facing citation numbers."""
    citation_numbers: Dict[str, int] = {}
    for citation in citations:
        citation_numbers.setdefault(citation.chunk_id, len(citation_numbers) + 1)

    def replace(match: re.Match) -> str:
        number = citation_numbers.get(match.group(1))
        return f"[{number}]" if number is not None else ""

    return CITATION_MARKER_RE.sub(replace, response_text)
# === TASK:WP-201:END ===
