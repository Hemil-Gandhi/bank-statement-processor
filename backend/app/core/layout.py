"""Word-box layout helpers shared by account and table extraction."""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from app.core.types import Word


@dataclass(slots=True)
class Line:
    words: list[Word]
    y0: float
    y1: float

    @property
    def text(self) -> str:
        return " ".join(word.text for word in self.words).strip()

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2


def group_lines(words: list[Word], tolerance_factor: float = 0.55) -> list[Line]:
    if not words:
        return []
    heights = [max(1.0, word.y1 - word.y0) for word in words]
    tolerance = max(2.0, median(heights) * tolerance_factor)
    ordered = sorted(words, key=lambda word: (word.cy, word.x0))
    clusters: list[list[Word]] = []
    centers: list[float] = []
    for word in ordered:
        placed = False
        for index in range(len(clusters) - 1, -1, -1):
            if abs(word.cy - centers[index]) <= tolerance:
                clusters[index].append(word)
                centers[index] = sum(w.cy for w in clusters[index]) / len(clusters[index])
                placed = True
                break
        if not placed:
            clusters.append([word])
            centers.append(word.cy)
    lines: list[Line] = []
    for cluster in clusters:
        cluster.sort(key=lambda word: word.x0)
        lines.append(
            Line(
                words=cluster,
                y0=min(word.y0 for word in cluster),
                y1=max(word.y1 for word in cluster),
            )
        )
    lines.sort(key=lambda line: line.y0)
    return lines


def line_text(words: list[Word]) -> str:
    return " ".join(word.text for word in sorted(words, key=lambda w: w.x0)).strip()
