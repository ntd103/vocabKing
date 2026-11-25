from src.services.word_parser import (
    format_preview,
    join_wrapped_lines,
    parse_add_input,
    parse_line,
)


class TestJoinWrappedLines:
    def test_simple_lines(self):
        text = "a|b|c|d|e|f\ng|h|i|j|k|l"
        assert join_wrapped_lines(text) == ["a|b|c|d|e|f", "g|h|i|j|k|l"]

    def test_wrapped_line_joins_previous(self):
        # A line without pipes continues the preceding record.
        text = "serendipity|/serənˈdɪpəti/|good luck|sự tình cờ gặp may\nmắn bất ngờ\nbye|||tạm biệt"
        assert join_wrapped_lines(text) == [
            "serendipity|/serənˈdɪpəti/|good luck|sự tình cờ gặp may mắn bất ngờ",
            "bye|||tạm biệt",
        ]

    def test_blank_lines_ignored(self):
        assert join_wrapped_lines("a|b\n\n\nc|d") == ["a|b", "c|d"]

    def test_first_line_without_pipe_is_own_record(self):
        assert join_wrapped_lines("just a word\na|b") == ["just a word", "a|b"]


class TestParseLine:
    def test_full(self):
        e = parse_line("hello|/həˈloʊ/|a greeting|xin chào|Hi Paul|informal")
        assert e == {
            "word": "hello",
            "phonetic": "/həˈloʊ/",
            "define_en": "a greeting",
            "meaning": "xin chào",
            "example": "Hi Paul",
            "note": "informal",
        }

    def test_missing_fields_none(self):
        assert parse_line("hello") == {
            "word": "hello", "phonetic": None, "define_en": None,
            "meaning": None, "example": None, "note": None,
        }

    def test_partial(self):
        e = parse_line("hello|/həˈloʊ/||xin chào")
        assert e["phonetic"] == "/həˈloʊ/"
        assert e["define_en"] is None
        assert e["meaning"] == "xin chào"
        assert e["example"] is None
        assert e["note"] is None

    def test_no_word_returns_none(self):
        assert parse_line("|a|b") is None

    def test_extra_pipes_stay_in_note(self):
        e = parse_line("w|p|de|m|e|note|with|pipes")
        assert e["note"] == "note|with|pipes"

    def test_delimiter_only_tail_is_none(self):
        assert parse_line("hello||greeting|xin chào|hello its me||") == {
            "word": "hello", "phonetic": None, "define_en": "greeting",
            "meaning": "xin chào", "example": "hello its me", "note": None,
        }
        assert parse_line("hello||||| | | ")["note"] is None

    def test_substantive_note_preserves_leading_and_trailing_pipes(self):
        assert parse_line("w|p|de|m|e||note||")["note"] == "|note||"

    def test_fields_trimmed_and_empty_fields_none(self):
        assert parse_line(" hello | | greeting | xin chào | | ") == {
            "word": "hello", "phonetic": None, "define_en": "greeting",
            "meaning": "xin chào", "example": None, "note": None,
        }

    def test_en_only_does_not_become_vi(self):
        e = parse_line("hello||a greeting")
        assert e["define_en"] == "a greeting"
        assert e["meaning"] is None

    def test_special_chars_preserved(self):
        e = parse_line("naïve|/nɑːˈiːv/|innocent|ngây thơ — hồn nhiên|It's naïve!|x")
        assert e["word"] == "naïve"
        assert e["phonetic"] == "/nɑːˈiːv/"
        assert e["meaning"] == "ngây thơ — hồn nhiên"
        assert e["example"] == "It's naïve!"


class TestParseAddInput:
    def test_bulk_with_wrap_and_dedup(self):
        text = (
            "apple|/ˈæp.əl/|a fruit|quả táo|An apple a day|fruit\n"
            "APPLE||dup|dup\n"
            "serendipity|/serənˈdɪpəti/|good luck|sự tình cờ gặp may — this is a very long\n"
            "meaning that got wrapped by telegram"
        )
        entries = parse_add_input(text)
        assert len(entries) == 2
        assert entries[0]["define_en"] == "a fruit"
        assert entries[0]["meaning"] == "quả táo"
        assert entries[0]["example"] == "An apple a day"
        assert entries[0]["note"] == "fruit"
        assert entries[1]["define_en"] == "good luck"
        assert entries[1]["meaning"].startswith("sự tình cờ gặp may")
        assert "wrapped by telegram" in entries[1]["meaning"]


class TestFormatPreview:
    def test_shows_count_and_words(self):
        entries = parse_add_input("hello|/həˈloʊ/|a greeting|xin chào")
        out = format_preview(entries)
        assert "Preview (1)" in out and "hello" in out and "/həˈloʊ/" in out
        assert "🇬🇧 a greeting" in out and "🇻🇳 xin chào" in out

    def test_manual_preview_puts_each_attribute_on_its_own_icon_line(self):
        out = format_preview(parse_add_input("hello|/həˈloʊ/|a greeting|xin chào|Hi!|informal"))

        assert " • 📖 hello\n   🔊 /həˈloʊ/\n   🇬🇧 a greeting\n   🇻🇳 xin chào\n   📝 Hi!\n   ℹ️ informal" in out

    def test_rejects_entire_batch_if_a_required_field_is_missing(self):
        for invalid in ("solo", "solo|||VI", "solo||English|", "||English|VI"):
            assert parse_add_input("hello||greeting|xin chào\n" + invalid if "|" in invalid else invalid) == []

    def test_escapes_html_without_mutating_entries(self):
        entries = parse_add_input('<b>word</b>|/<ipa>/|EN & <def>|VI <meaning>|<example>|<note>')
        out = format_preview(entries)
        assert "&lt;b&gt;word&lt;/b&gt;" in out
        assert "/&lt;ipa&gt;/" in out
        assert "EN &amp; &lt;def&gt;" in out
        assert "VI &lt;meaning&gt;" in out
        assert "&lt;example&gt;" in out
        assert "&lt;note&gt;" in out
        assert entries[0]["word"] == "<b>word</b>"
        assert entries[0]["define_en"] == "EN & <def>"
