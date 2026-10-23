"""Layer B Semantic Cache Matcher for JARVIS Multi-Layer AI Caching Engine."""

import re
import logging
from typing import Optional, List, Tuple
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from core.ai.caching.models import CacheEntry

logger = logging.getLogger("Jarvis.SemanticMatcher")


class SemanticMatcher:
    """Computes semantic similarity over candidate cache entries using local TF-IDF vectorization
    and strict contextual attribute guards (explanation style, target language, technical concepts).
    """

    def __init__(self, similarity_threshold: float = 0.88):
        self.similarity_threshold = similarity_threshold
        # Vectorizer using sub-word and word tokens with stop words
        self._vectorizer = TfidfVectorizer(
            analyzer="word",
            ngram_range=(1, 2),
            stop_words="english",
            strip_accents="unicode",
            lowercase=True
        )

    def extract_style(self, text: str) -> str:
        """Extracts requested explanation style from natural language text."""
        clean = text.lower()
        if any(s in clean for s in ["beginner", "like i'm a beginner", "like im a beginner", "simple language", "simple english", "simply", "for a 5 year old", "like i'm 5"]):
            return "beginner"
        if any(s in clean for s in ["line by line", "code line by line", "step by step in code"]):
            return "code_line_by_line"
        if any(s in clean for s in ["technical", "in detail", "detailed explanation", "architectural", "deep dive"]):
            return "technical"
        if any(s in clean for s in ["step by step", "step-by-step", "steps"]):
            return "step_by_step"
        if any(s in clean for s in ["example", "with an example", "practical example", "code example"]):
            return "example_based"
        if any(s in clean for s in ["exam", "for exam", "revision"]):
            return "exam_oriented"
        if any(s in clean for s in ["interview", "for interview", "trade offs", "edge cases"]):
            return "interview_oriented"
        if any(s in clean for s in ["short answer", "short summary", "briefly", "in short", "concise"]):
            return "short_summary"
        return "default"

    def extract_target_language(self, text: str) -> str:
        """Extracts target programming language constraint from query."""
        clean = text.lower()
        if re.search(r"\b(c\+\+|cpp)\b", clean):
            return "cpp"
        if re.search(r"\b(python|py)\b", clean):
            return "python"
        if re.search(r"\b(javascript|js|node\.?js)\b", clean):
            return "javascript"
        if re.search(r"\b(typescript|ts)\b", clean):
            return "typescript"
        if re.search(r"\b(react|jsx|tsx)\b", clean):
            return "react"
        if re.search(r"\b(java)\b", clean):
            return "java"
        if re.search(r"\b(c#|csharp)\b", clean):
            return "csharp"
        if re.search(r"\b(rust)\b", clean):
            return "rust"
        if re.search(r"\b(sql|database schema)\b", clean):
            return "sql"
        if re.search(r"\b(go|golang)\b", clean):
            return "go"
        return "any"

    def extract_negation(self, text: str) -> bool:
        """Detects negative or contradictory constraints in user prompts."""
        clean = text.lower()
        return bool(re.search(r"\b(?:not|without|never|don'?t|no\b|non-)", clean))

    def extract_core_concept(self, text: str) -> str:
        """Extracts the primary concept or subject noun phrase."""
        clean = text.lower()
        # Strip common question frames
        patterns = [
            r"^(?:what\s+is|what\s+are|explain|can\s+you\s+explain|can\s+you\s+write|can\s+you\s+show|tell\s+me\s+about|how\s+does|how\s+do|define|write|implement|create|show\s+me)\s+",
            r"\b(?:in\s+simple\s+language|in\s+simple\s+terms|like\s+i'm\s+a\s+beginner|in\s+detail|again|with\s+an\s+example)\b",
            r"\b(?:in\s+c\+\+|in\s+python|in\s+java|in\s+c#|in\s+rust|in\s+go)\b"
        ]
        for pat in patterns:
            clean = re.sub(pat, " ", clean)
        clean = re.sub(r"[^\w\s]", "", clean)
        return " ".join(clean.split()).strip()

    def find_best_semantic_match(
        self,
        query: str,
        candidates: List[CacheEntry]
    ) -> Tuple[Optional[CacheEntry], float]:
        """Compares incoming query against candidates, applying strict attribute guards.
        Returns: (best_matching_entry, similarity_score) or (None, 0.0)
        """
        if not candidates or not query or not query.strip():
            return None, 0.0

        query_style = self.extract_style(query)
        query_lang = self.extract_target_language(query)
        query_concept = self.extract_core_concept(query)
        query_negation = self.extract_negation(query)

        # Filter candidates by non-negotiable compatibility guards
        eligible_candidates: List[CacheEntry] = []
        for c in candidates:
            # 1. Disputed or invalidated entries are strictly barred
            if c.is_disputed:
                continue

            # 2. Style guard: Both must match requested style
            cand_style = c.style or self.extract_style(c.query)
            if query_style != cand_style:
                continue

            # 3. Programming language guard: Both must match target language
            cand_lang = c.language or self.extract_target_language(c.query)
            if query_lang != cand_lang:
                continue

            # 4. Negation guard: Queries with opposing negative constraints must not cross-match
            cand_negation = self.extract_negation(c.query)
            if query_negation != cand_negation:
                continue

            # 5. Core concept sanity check: Candidate must share at least one non-trivial concept token
            cand_concept = self.extract_core_concept(c.query)
            if query_concept and cand_concept:
                q_words = set(w for w in query_concept.split() if len(w) > 2)
                c_words = set(w for w in cand_concept.split() if len(w) > 2)
                if q_words and c_words and not (q_words & c_words):
                    continue

            eligible_candidates.append(c)

        if not eligible_candidates:
            return None, 0.0

        clean_query = query_concept or query.strip().lower()
        clean_candidates = [self.extract_core_concept(c.query) or c.query.strip().lower() for c in eligible_candidates]

        # Fast path: check for exact core concept match
        for idx, (cand_clean, candidate) in enumerate(zip(clean_candidates, eligible_candidates)):
            if clean_query and clean_query == cand_clean and len(clean_query) >= 3:
                logger.info(
                    f"[SEMANTIC_CACHE_HIT] Exact core concept match: '{clean_query}' ~= '{cand_clean}'"
                )
                return candidate, 1.0

        # Compute TF-IDF Cosine Similarity
        corpus = [clean_query] + clean_candidates
        try:
            tfidf_matrix = self._vectorizer.fit_transform(corpus)
            query_vector = tfidf_matrix[0:1]
            candidate_vectors = tfidf_matrix[1:]

            similarities = cosine_similarity(query_vector, candidate_vectors)[0]
            best_idx = int(similarities.argmax())
            best_score = float(similarities[best_idx])

            if best_score >= self.similarity_threshold:
                match = eligible_candidates[best_idx]
                logger.info(
                    f"[SEMANTIC_CACHE_HIT] Match found ({best_score:.1%}): "
                    f"'{query}' ~= '{match.query}' (Style: {match.style})"
                )
                return match, best_score
            else:
                logger.debug(
                    f"[SEMANTIC_CACHE_REJECT] Best candidate '{eligible_candidates[best_idx].query}' "
                    f"scored {best_score:.1%}, below threshold {self.similarity_threshold:.1%}"
                )
                return None, best_score
        except Exception as e:
            logger.error(f"[SEMANTIC_CACHE] Error computing similarity: {e}")
            return None, 0.0
