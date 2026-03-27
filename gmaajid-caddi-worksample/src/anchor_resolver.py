"""Anchor-based word voting resolver.

Canonical names are fixed anchors. Input names are scored against them
by having each word in the input vote for the canonical whose words
it best matches. TF-IDF weighting ensures rare words (QuickFab) count
more than common ones (Manufacturing).

Split votes (words voting for 2+ canonicals) signal potential M&A events.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from src.supplier_clustering import (
    tokenize_company,
    compute_idf,
    _normalize_chars,
    _strip_legal_suffixes,
)


@dataclass
class AnchorResult:
    """Result of resolving a name against canonical anchors."""
    canonical: Optional[str] = None
    confidence: float = 0.0
    split_vote: bool = False
    voted_canonicals: list[dict] = field(default_factory=list)
    word_votes: dict = field(default_factory=dict)


class AnchorResolver:
    """Resolves supplier names by voting each word against canonical anchors."""

    def __init__(self, canonical_names: list[str]):
        self.canonical_names = canonical_names
        self._build_index()

    def _build_index(self) -> None:
        """Build word→canonical reverse index with TF-IDF weights."""
        # Tokenize each canonical
        self._canonical_tokens: dict[str, set[str]] = {}
        all_token_sets = []
        for name in self.canonical_names:
            tokens = tokenize_company(name)
            self._canonical_tokens[name] = tokens
            all_token_sets.append(tokens)

        # Compute IDF across canonical names
        self._idf = compute_idf(all_token_sets)

        # Build reverse index: token → [(canonical_name, idf_weight)]
        self._token_to_canonicals: dict[str, list[tuple[str, float]]] = {}
        for name, tokens in self._canonical_tokens.items():
            for token in tokens:
                weight = self._idf.get(token, 1.0)
                self._token_to_canonicals.setdefault(token, []).append((name, weight))

    def _get_matches_for_token(self, token: str) -> list[tuple[str, float]]:
        """Return (canonical_name, idf_weight) pairs for a token, including fuzzy."""
        matches = self._token_to_canonicals.get(token, [])
        if not matches:
            for canon_token, entries in self._token_to_canonicals.items():
                if _is_fuzzy_match(token, canon_token):
                    matches = matches + entries
        return matches

    def _best_canonical_for_tokens(self, tokens: set[str]) -> Optional[str]:
        """Return the canonical that receives the most votes from a token set."""
        votes: dict[str, float] = {}
        for token in tokens:
            weight = self._idf.get(token, 1.0)
            for canonical_name, canon_weight in self._get_matches_for_token(token):
                vote_weight = (weight + canon_weight) / 2
                votes[canonical_name] = votes.get(canonical_name, 0) + vote_weight
        if not votes:
            return None
        return max(votes, key=lambda k: votes[k])

    def resolve(self, name: str) -> AnchorResult:
        """Resolve a name by word voting against canonical anchors.

        Each token in the input name votes for the canonical(s) that
        contain that token (after normalization). Votes are weighted
        by IDF — rare tokens count more.

        Returns AnchorResult with:
          - canonical: best-matching canonical (or None)
          - confidence: weighted vote fraction
          - split_vote: True if tokens voted for 2+ canonicals
          - voted_canonicals: all canonicals that received votes, ranked
        """
        # Pre-split on hyphens to handle compound names like "Apex-QuickFab"
        # by checking whether different parts resolve to different canonicals
        if "-" in name:
            parts = [p.strip() for p in name.split("-") if p.strip()]
            if len(parts) >= 2:
                return self._resolve_compound(parts)

        input_tokens = tokenize_company(name)
        if not input_tokens:
            return AnchorResult()

        return self._resolve_tokens(input_tokens)

    def _resolve_compound(self, parts: list[str]) -> AnchorResult:
        """Resolve a hyphenated compound name by merging votes across parts.

        Detects split votes by checking whether different hyphen-separated
        parts resolve to different canonicals.
        """
        # Resolve each part independently to detect split votes
        part_top_canonicals: list[Optional[str]] = []
        all_votes: dict[str, float] = {}
        all_word_votes: dict[str, list[str]] = {}

        for part in parts:
            tokens = tokenize_company(part)
            part_top = self._best_canonical_for_tokens(tokens)
            part_top_canonicals.append(part_top)

            for token in tokens:
                weight = self._idf.get(token, 1.0)
                all_word_votes[token] = []
                for canonical_name, canon_weight in self._get_matches_for_token(token):
                    vote_weight = (weight + canon_weight) / 2
                    all_votes[canonical_name] = all_votes.get(canonical_name, 0) + vote_weight
                    if canonical_name not in all_word_votes[token]:
                        all_word_votes[token].append(canonical_name)

        if not all_votes:
            return AnchorResult(word_votes=all_word_votes)

        ranked = sorted(all_votes.items(), key=lambda x: -x[1])
        voted_canonicals = [
            {"canonical": cname, "score": round(cscore, 3)}
            for cname, cscore in ranked
        ]

        # Split vote: parts resolve to different non-None canonicals
        unique_tops = {c for c in part_top_canonicals if c is not None}
        split_vote = len(unique_tops) >= 2

        # Also check score-ratio split
        if not split_vote and len(ranked) >= 2:
            best_score = ranked[0][1]
            second_score = ranked[1][1]
            if second_score > best_score * 0.4:
                split_vote = True

        if split_vote:
            return AnchorResult(
                canonical=None,
                confidence=0.4,
                split_vote=True,
                voted_canonicals=voted_canonicals,
                word_votes=all_word_votes,
            )

        best_name = ranked[0][0]
        return AnchorResult(
            canonical=best_name,
            confidence=0.5,
            split_vote=False,
            voted_canonicals=voted_canonicals,
            word_votes=all_word_votes,
        )

    def _resolve_tokens(self, input_tokens: set[str]) -> AnchorResult:
        """Core resolution logic given a set of input tokens."""
        # Tally votes: canonical → total weighted votes
        votes: dict[str, float] = {}
        word_votes: dict[str, list[str]] = {}
        # Track which input tokens voted for which canonicals
        token_canonical_map: dict[str, set[str]] = {}

        for token in input_tokens:
            matches = self._get_matches_for_token(token)
            weight = self._idf.get(token, 1.0)
            word_votes[token] = []
            token_canonical_map[token] = set()

            for canonical_name, canon_weight in matches:
                vote_weight = (weight + canon_weight) / 2
                votes[canonical_name] = votes.get(canonical_name, 0) + vote_weight
                if canonical_name not in word_votes[token]:
                    word_votes[token].append(canonical_name)
                token_canonical_map[token].add(canonical_name)

        if not votes:
            return AnchorResult(word_votes=word_votes)

        # Rank canonicals by vote weight
        ranked = sorted(votes.items(), key=lambda x: -x[1])
        best_name, best_score = ranked[0]

        canonical_tokens = self._canonical_tokens.get(best_name, set())

        # --- Confidence calculation ---
        #
        # Three-factor scoring:
        #
        # 1. Canon coverage: what fraction of canonical's tokens were matched
        #    (exactly or fuzzily) by input tokens? Ensures input "covers" the canonical.
        #
        # 2. Input coverage: what fraction of input tokens voted for THIS canonical?
        #    Critical false-positive guard: "Apex Farms" has 2 tokens, only "apex"
        #    matches → input_coverage = 0.5.
        #
        # 3. Input coverage penalty factor (input_coverage^2): aggressively penalizes
        #    low input coverage. This brings:
        #    - Apex Farms: harmonic(0.5,0.5) * 0.25 = 0.125 → below threshold
        #    - AeroTech Systems: harmonic(0.67,0.67) * 0.44 = 0.30 → below threshold
        #    while keeping legitimate matches high (both coverages near 1.0).

        # Canonical coverage: fuzzy match input tokens against canonical tokens
        canon_matched = 0
        for inp_tok in input_tokens:
            for can_tok in canonical_tokens:
                if _is_fuzzy_match(inp_tok, can_tok):
                    canon_matched += 1
                    break
        canon_coverage = canon_matched / len(canonical_tokens) if canonical_tokens else 0.0

        # Input coverage: how many input tokens voted for best_name?
        input_matched = sum(
            1 for tok in input_tokens
            if best_name in token_canonical_map.get(tok, set())
        )
        input_coverage = input_matched / len(input_tokens) if input_tokens else 0.0

        # Harmonic mean of both coverages × input_coverage^2 penalty
        if canon_coverage > 0 and input_coverage > 0:
            harmonic = 2 * canon_coverage * input_coverage / (canon_coverage + input_coverage)
        else:
            harmonic = 0.0

        # Apply input coverage penalty: low input coverage kills confidence
        confidence = harmonic * (input_coverage ** 2)
        confidence = round(confidence, 3)

        # Detect split votes: do the top 2 canonicals both have significant votes?
        split_vote = False
        if len(ranked) >= 2:
            second_name, second_score = ranked[1]
            # Split if second place has > 40% of first's votes
            if second_score > best_score * 0.4:
                split_vote = True

        # Build voted_canonicals list
        voted_canonicals = [
            {"canonical": cname, "score": round(cscore, 3)}
            for cname, cscore in ranked
        ]

        # Threshold: below 0.35 confidence, don't return a match
        if confidence < 0.35:
            return AnchorResult(
                split_vote=split_vote,
                voted_canonicals=voted_canonicals,
                word_votes=word_votes,
            )

        return AnchorResult(
            canonical=best_name,
            confidence=confidence,
            split_vote=split_vote,
            voted_canonicals=voted_canonicals,
            word_votes=word_votes,
        )

    def _group_by_token(self) -> dict[str, list[tuple[str, float]]]:
        """Group canonical entries by token for fuzzy matching."""
        return self._token_to_canonicals


def _is_fuzzy_match(a: str, b: str, threshold: float = 0.75) -> bool:
    """Check if two tokens are fuzzy matches (edit distance based).

    Handles: missing letter (Stellr/Stellar), doubled letter (Apexx/Apex),
    transposition (Ttian/Titan), compound split (titanforge vs titan+forge).
    """
    if a == b:
        return True
    # One is substring of the other (compound word handling)
    if len(a) >= 4 and len(b) >= 4:
        if a in b or b in a:
            return True
    # Edit distance ratio
    if not a or not b:
        return False
    max_len = max(len(a), len(b))
    if max_len == 0:
        return True
    distance = _levenshtein(a, b)
    ratio = 1 - (distance / max_len)
    return ratio >= threshold


def _levenshtein(s1: str, s2: str) -> int:
    """Compute Levenshtein edit distance."""
    if len(s1) < len(s2):
        return _levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (c1 != c2)
            curr_row.append(min(insertions, deletions, substitutions))
        prev_row = curr_row
    return prev_row[-1]
