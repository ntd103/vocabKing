"""Cloze (fill-in-the-blank) utilities.

Pure functions — no Telegram/Workers dependencies, fully unit-testable.

Masking rule: keep the first letter of the word, mask remaining letters with
"_", keep non-alphabetic characters (spaces, punctuation) as-is. Word
comparison is case-insensitive; the user answer matches when every masked
letter matches ignoring case.
"""

import random
import re
import unicodedata

MASK_CHAR = "_"

# Letters per Unicode category (L*). Covers IPA and Vietnamese diacritics too.
_LETTER_RE = re.compile(r"[^\W\d_]", re.UNICODE)


def _letter_indices(word: str) -> list[int]:
    """Indices of alphabetic characters, skipping the first letter of each word."""
    indices: list[int] = []
    seen_first_of_word = False
    for i, ch in enumerate(word):
        if _LETTER_RE.match(ch):
            if not seen_first_of_word:
                seen_first_of_word = True  # keep the first letter of the word visible
            else:
                indices.append(i)
        else:
            seen_first_of_word = False  # punctuation/space starts a new "word"
    return indices


def mask_word(word: str) -> str:
    """`Hello` -> `H____`; `bonjour, Paul!` -> `b______, P___!`."""
    chars = list(word)
    for i in _letter_indices(word):
        chars[i] = MASK_CHAR
    return "".join(chars)


def strip_diacritics(s: str) -> str:
    """Loose comparison: normalize diacritics away (NFD, drop combining marks)."""
    return "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    )


def _is_correct(word: str, answer: str) -> bool:
    normalize = lambda s: re.sub(r"\s+", " ", strip_diacritics(s)).strip().lower()
    return normalize(word) == normalize(answer)


def reveal_letters(word: str, masked: str, count: int, seed: int) -> str:
    """Reveal up to `count` masked letters in `masked`, chosen to be spread out
    from each other and from already-revealed letters (hangman-style).

    Deterministic given `seed` (card id + reveal count) so re-rendering the same
    state is stable. Returns the original masked string if nothing left to reveal.
    """
    revealed = [i for i, ch in enumerate(masked) if ch != MASK_CHAR]
    candidates = [i for i in _letter_indices(word) if masked[i] == MASK_CHAR]
    if not candidates or count <= 0:
        return masked

    rng = random.Random(seed)
    chosen: list[int] = []
    pool = list(candidates)
    while pool and len(chosen) < count:
        # Score: prefer candidates far from all revealed/chosen positions.
        anchors = revealed + chosen
        scored = [
            (
                min(abs(i - a) for a in anchors) if anchors else float("inf"),
                rng.random(),  # tie-break randomly but deterministically
                i,
            )
            for i in pool
        ]
        scored.sort(key=lambda t: (t[0], t[1]))
        best = scored[-1]  # farthest anchor wins
        chosen.append(best[2])
        pool.remove(best[2])

    chars = list(masked)
    for i in chosen:
        chars[i] = word[i]
    return "".join(chars)


def fully_revealed(word: str, masked: str) -> bool:
    return all(masked[i] != MASK_CHAR for i in _letter_indices(word))


def count_masked(word: str, masked: str) -> int:
    """Number of still-masked letters."""
    return sum(1 for i in _letter_indices(word) if masked[i] == MASK_CHAR)


def check_answer(word: str, answer: str) -> bool:
    return _is_correct(word, answer)


def render_cloze_prompt(masked: str, hint: str) -> str:
    """Message body for a fill-in-the-blank question."""
    return f"Điền từ vào chỗ trống:\n\n{masked}\n\nGợi ý: {hint}"


__all__ = [
    "MASK_CHAR",
    "mask_word",
    "reveal_letters",
    "fully_revealed",
    "count_masked",
    "check_answer",
    "render_cloze_prompt",
    "_is_correct",
    "strip_diacritics",
]
