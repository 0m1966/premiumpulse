"""Simple, dependency-free Underwriting Guidelines clause retriever.

Parses data_gen/underwriting_guidelines.md by clause IDs ([UG-xxx])
and retrieves top relevant clauses via token TF-IDF similarity.
"""

import math
import re
from pathlib import Path
from typing import Any

GUIDELINES_PATH = Path(__file__).resolve().parent.parent.parent / "data_gen" / "underwriting_guidelines.md"


class GuidelineClause:
    """Indexed underwriting guideline clause."""

    def __init__(self, clause_id: str, title: str, content: str):
        self.clause_id = clause_id
        self.title = title
        self.content = content
        self.full_text = f"{title}\n{content}"
        self.tokens = self._tokenize(self.full_text)

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        words = re.findall(r"\b[a-zA-Z0-9_\-]{2,}\b", text.lower())
        return words


class GuidelineRetriever:
    """TF-IDF retriever for underwriting guideline clauses."""

    def __init__(self, filepath: Path | None = None):
        self.filepath = filepath or GUIDELINES_PATH
        self.clauses: list[GuidelineClause] = []
        self.doc_freq: dict[str, int] = {}
        self._load_and_index()

    def _load_and_index(self) -> None:
        if not self.filepath.exists():
            return

        with open(self.filepath, mode="r", encoding="utf-8") as f:
            raw = f.read()

        # Split by ### [UG-xxx]
        pattern = r"###\s*\[(UG-\d+)\]\s*([^\n]+)\n(.*?)(?=(?:###\s*\[UG-\d+\]|\Z))"
        matches = re.findall(pattern, raw, flags=re.DOTALL)

        for cid, title, body in matches:
            clause = GuidelineClause(cid.strip(), title.strip(), body.strip())
            self.clauses.append(clause)
            seen_tokens = set(clause.tokens)
            for t in seen_tokens:
                self.doc_freq[t] = self.doc_freq.get(t, 0) + 1

    def retrieve(self, query: str, top_k: int = 3, min_score: float = 0.05) -> list[dict[str, Any]]:
        """Retrieve top-k matching clauses with similarity score."""
        query_tokens = GuidelineClause._tokenize(query)
        if not query_tokens or not self.clauses:
            return []

        scores: list[tuple[float, GuidelineClause]] = []
        num_docs = len(self.clauses)

        for clause in self.clauses:
            score = 0.0
            clause_token_counts: dict[str, int] = {}
            for t in clause.tokens:
                clause_token_counts[t] = clause_token_counts.get(t, 0) + 1

            for qt in query_tokens:
                if qt in clause_token_counts:
                    tf = clause_token_counts[qt] / len(clause.tokens)
                    idf = math.log((num_docs + 1) / (self.doc_freq.get(qt, 1) + 1)) + 1.0
                    score += tf * idf

            if score > min_score:
                scores.append((score, clause))

        scores.sort(key=lambda x: x[0], reverse=True)
        results = []
        for s, c in scores[:top_k]:
            results.append({
                "clause_id": c.clause_id,
                "title": c.title,
                "content": c.content,
                "score": round(s, 4),
            })
        return results
