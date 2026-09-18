from src.services.word_parser import (
    format_preview,
    join_wrapped_lines,
    parse_add_input,
    parse_line,
)


class TestJoinWrappedLines:
    def test_simple_lines(self):
        text = "a|b|c|d|e\nf|g|h|i|j"
        assert join_wrapped_lines(text) == ["a|b|c|d|e", "f|g|h|i|j"]

    def test_wrapped_line_joins_previous(self):
        # Telegram hard-wrapped a long field; the wrap line has no `|` so it
        # joins the previous record (documented rule, see /help).
        text = "serendipity|/serənˈdɪpəti/|sự tình cờ gặp may\nmắn bất ngờ\nbye|tạm biệt"
        assert join_wrapped_lines(text) == [
            "serendipity|/serənˈdɪpəti/|sự tình cờ gặp may mắn bất ngờ",
            "bye|tạm biệt",
        ]

    def test_blank_lines_ignored(self):
        assert join_wrapped_lines("a|b\n\n\nc|d") == ["a|b", "c|d"]

    def test_first_line_without_pipe_is_own_record(self):
        assert join_wrapped_lines("just a word\na|b") == ["just a word", "a|b"]


class TestParseLine:
    def test_full(self):
        e = parse_line("hello|/həˈloʊ/|xin chào|Hi Paul|greeting")
        assert e == {
            "word": "hello",
            "phonetic": "/həˈloʊ/",
            "meaning": "xin chào",
            "example": "Hi Paul",
            "note": "greeting",
        }

    def test_missing_fields_none(self):
        e = parse_line("hello")
        assert e == {"word": "hello", "phonetic": None, "meaning": None, "example": None, "note": None}

    def test_partial(self):
        e = parse_line("hello|/həˈloʊ/|xin chào")
        assert e["phonetic"] == "/həˈloʊ/" and e["example"] is None

    def test_no_word_returns_none(self):
        assert parse_line("|a|b") is None

    def test_extra_pipes_stay_in_note(self):
        e = parse_line("w|p|m|e|note|with|pipes")
        assert e["note"] == "note|with|pipes"

    def test_special_chars_preserved(self):
        e = parse_line("naïve|/nɑːˈiːv/|ngây thơ — hồn nhiên|It's naïve!|x")
        assert e["word"] == "naïve"
        assert e["phonetic"] == "/nɑːˈiːv/"


class TestParseAddInput:
    def test_bulk_with_wrap_and_dedup(self):
        text = (
            "apple|/ˈæp.əl/|quả táo|An apple a day|fruit\n"
            "apple|dup|dup\n"
            "serendipity|/serənˈdɪpəti/|sự tình cờ gặp may — this is a very long\n"
            "meaning that got wrapped by telegram"
        )
        entries = parse_add_input(text)
        assert len(entries) == 2
        assert entries[1]["meaning"].startswith("sự tình cờ gặp may")
        assert "wrapped by telegram" in entries[1]["meaning"]


class TestFormatPreview:
    def test_shows_count_and_words(self):
        entries = parse_add_input("hello|/həˈloʊ/|xin chào")
        out = format_preview(entries)
        assert "1 từ" in out and "hello" in out and "/həˈloʊ/" in out

    def test_missing_meaning_placeholder(self):
        out = format_preview(parse_add_input("solo"))
        assert "(chưa có nghĩa)" in out
