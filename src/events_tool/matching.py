"""Score a raw event candidate's text against the user's active interests.

This is intentionally simple keyword matching, not ML classification: the
interest list in profile.json IS the user's curation mechanism (per the
"update interests to inform the next round of events" requirement), so the
matcher's job is just to apply that list consistently, not to be clever.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from events_tool.models import Interest, RawEventCandidate


@dataclass
class MatchResult:
    matched: bool
    category: str
    score: float
    matched_keywords: list[str]


def score_candidate(candidate: RawEventCandidate, interests: list[Interest]) -> MatchResult:
    text = f"{candidate.title} {candidate.description}".lower()
    best: Optional[MatchResult] = None
    category_scores: dict[str, tuple[float, list[str]]] = {}

    for interest in interests:
        if not interest.active:
            continue
        if interest.keyword.lower() in text:
            total, keywords = category_scores.get(interest.category, (0.0, []))
            category_scores[interest.category] = (total + interest.weight, keywords + [interest.keyword])

    if not category_scores:
        return MatchResult(matched=False, category="uncategorized", score=0.0, matched_keywords=[])

    top_category = max(category_scores.items(), key=lambda kv: kv[1][0])
    category, (score, keywords) = top_category
    return MatchResult(matched=True, category=category, score=score, matched_keywords=keywords)


def filter_matching(
    candidates: list[RawEventCandidate], interests: list[Interest]
) -> list[tuple[RawEventCandidate, MatchResult]]:
    """Return only candidates that matched at least one active interest, paired with their match."""
    results = []
    for candidate in candidates:
        result = score_candidate(candidate, interests)
        if result.matched:
            results.append((candidate, result))
    return results
