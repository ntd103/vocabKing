import re

from src.services.cloze import (
    MASK_CHAR,
    _is_correct,
    fully_revealed,
    mask_word,
    reveal_letters,
    strip_diacritics,
)


class TestMaskWord:
    def test_simple_word_keeps_first_letter(self):
        # "Hello" = 5 letters -> H + 4 masks (first letter always visible).
        assert mask_word("Hello") == f"H{MASK_CHAR * 4}"

    def test_punctuation_and_spaces_preserved(self):
        assert mask_word("bonjour, Paul!") == f"b{MASK_CHAR * 6}, P{MASK_CHAR * 3}!"

    def test_new_word_after_punctuation_keeps_first_letter(self):
        # After ", " the P of Paul is the first letter of a new word -> visible.
        assert mask_word("bonjour, Paul!")[9] == "P"

    def test_ipa_like_unicode(self):
        out = mask_word("həˈloʊ")
        assert out[0] == "h"  # first letter stays
        assert MASK_CHAR in out
        # Non-letter phonetic marks are preserved
        assert all(
            ch == MASK_CHAR or not re.match(r"[^\W\d_]", ch, re.UNICODE)
            for ch in out[1:]
        )

    def test_vietnamese_diacritics(self):
        out = mask_word("xin chào")
        assert out.startswith("x") and out[4] == "c"

    def test_hyphenated(self):
        # Letter after "-" starts a new word -> its first letter stays visible.
        out = mask_word("well-known")
        assert out == f"w{MASK_CHAR * 3}-k{MASK_CHAR * 4}"


class TestRevealLetters:
    def test_reveals_requested_count(self):
        masked = mask_word("Hello")
        out = reveal_letters("Hello", masked, 2, seed=1)
        assert sum(1 for c in out if c == MASK_CHAR) == 2

    def test_no_duplicate_reveal(self):
        word = "Mississippi"
        masked = mask_word(word)
        out = masked
        for n in range(1, 6):
            out = reveal_letters(word, out, 1, seed=n)
        # After 5 sequential reveals, 5 distinct letters are visible beyond 'M'.
        assert sum(1 for c in out if c != MASK_CHAR) == 6

    def test_spread_far_from_revealed(self):
        # With one revealed letter in the middle, next reveal prefers far away.
        word = "abcdef"
        masked = mask_word(word)
        # manually reveal index 3
        masked = masked[:3] + word[3] + masked[4:]
        out = reveal_letters(word, masked, 1, seed=0)
        new_positions = [
            i for i, c in enumerate(out) if c != MASK_CHAR and i not in (0, 3)
        ]
        assert len(new_positions) == 1
        assert abs(new_positions[0] - 3) >= 2

    def test_nothing_left_to_reveal(self):
        # "Hi" has only one maskable letter; count=0 keeps it hidden,
        # count>=1 reveals it (all remaining letters).
        word = "Hi"
        masked = mask_word(word)
        assert reveal_letters(word, masked, 0, seed=1) == masked
        assert reveal_letters(word, masked, 3, seed=1) == "Hi"

    def test_deterministic_given_seed(self):
        word = "Hello"
        masked = mask_word(word)
        a = reveal_letters(word, masked, 2, seed=42)
        b = reveal_letters(word, masked, 2, seed=42)
        assert a == b

    def test_eventually_fully_revealed(self):
        word = "Testing"
        masked = mask_word(word)
        out = masked
        for n in range(20):
            out = reveal_letters(word, out, 1, seed=n)
            if fully_revealed(word, out):
                break
        assert fully_revealed(word, out)


class TestCorrectness:
    def test_exact(self):
        assert _is_correct("Hello", "Hello")

    def test_case_insensitive(self):
        assert _is_correct("Hello", "hello")

    def test_diacritics_loose(self):
        assert _is_correct("cafe", "café")

    def test_wrong(self):
        assert not _is_correct("Hello", "Helo")

    def test_strip_diacritics(self):
        assert strip_diacritics("phở") == "pho"


class TestFullyRevealed:
    def test_masked_false(self):
        assert not fully_revealed("Hello", mask_word("Hello"))

    def test_full_true(self):
        assert fully_revealed("Hello", "Hello")
