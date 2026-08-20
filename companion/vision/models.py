"""Data structures shared by vision providers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AnalysisResult:
    """A successful answer to a question about a screenshot."""

    answer: str
    provider: str
    model: str
