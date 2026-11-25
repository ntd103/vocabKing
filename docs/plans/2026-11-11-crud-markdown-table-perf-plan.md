# Chuẩn hoá CRUD, Markdown Table & Tối ưu phản hồi Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Chuẩn hoá toàn bộ CRUD từ vựng theo Phương án B (chọn hành động trước → chọn bản ghi bằng STT/từ), chuyển mọi bảng sang GFM Markdown Table native của Telegram Bot API 10.1+, tối ưu tốc độ phản hồi (song song callback, SQL `ROW_NUMBER()`, cache RAM/LRU) và đồng bộ 100% icon + tiếng Việt trên mọi nút/màn hình.

**Architecture:** Mở rộng `src/telegram.py` hỗ trợ Rich Messages (`sendRichMessage` & `editMessageText(rich_message)`) kèm bộ tạo bảng GFM Markdown an toàn. Tái cấu trúc `vocab_list.py`, `edit.py`, `delete.py` dùng chung bảng Markdown 1-query `O(N)` giữ nguyên ngữ cảnh (`action`, `return_action`, `page`, `query`, `message_id`), kết hợp song song hoá `answerCallbackQuery` ở `vocab_do.py` và cache LRU ở `dict_service.py`.

**Tech Stack:** Python 3.12 (Cloudflare Workers Pyodide), Durable Objects SQLite (Window Functions SQLite 3.25+), Telegram Bot API 10.1+ (`sendRichMessage` / `editMessageText`), `pytest` chạy qua `uv run pytest`.

**Spec:** `docs/plans/2026-11-11-crud-markdown-table-perf-design.md`

## Global Constraints

- Luôn chạy Python/pytest qua `uv run ...` (tuyệt đối không gọi `pip` hoặc `pytest` trần).
- Không tự động chạy `git commit` / `git push` trừ khi người dùng yêu cầu trực tiếp; không đụng vào secrets/tokens.
- Không sinh inline button riêng cho từng từ vựng (`view1`, `editw:1`, `delw:1`...); mọi thao tác chọn bản ghi đi qua gõ STT hiển thị hoặc tên từ.
- Không dùng bảng ASCII/box-drawing (`<pre>`, `─`, `│`, `┼`, `_pad`) cho các bảng dữ liệu; dùng GFM Markdown Table qua `rich_message={"markdown": ..., "skip_entity_detection": True}`.
- Mọi bước trung gian trong cùng một luồng phải tái sử dụng `message_id` (edit tại chỗ, không xả tin nhắn rác).
- Ngôn ngữ hiển thị thống nhất tiếng Việt; mọi nút và mọi dòng thuộc tính preview/chi tiết đều có icon theo chuẩn (`🔤`, `🔊`, `🏷`, `🇬🇧`, `🇻🇳`, `📝`, `ℹ️`, `⏰`, `◀️`, `🏠`, `✅`, `❌`, `↩️`).
- Cập nhật đầy đủ `docs/exp.md` và `docs/usecase.md` sau khi hoàn thành code và test.

## Review Focus

1. **Ký tự đặc biệt & dấu `|` trong dữ liệu người dùng khi render Markdown Table**: Từ/nghĩa chứa `a|b`, `<script>`, `*bold*`, `$10`, `\n` không được làm vỡ cột bảng hoặc tiêm định dạng ngoài ý muốn (`Task 1`).
2. **Chọn bằng chữ khi kho có nhiều từ trùng tên (`> 1` dòng khớp `COLLATE NOCASE`)**: Không tự ý sửa/xoá dòng đầu tiên; phải hiện bảng lọc các dòng trùng tên kèm cảnh báo yêu cầu gõ STT, giữ nguyên `action` (`Task 3`).
3. **Gõ STT ngoài phạm vi hoặc từ không tồn tại khi đang ở trang `> 0` / đang có filter**: Không được xoá mất bảng đang xem hoặc làm rơi `page`/`query`; phải render lại đúng trang bảng hiện tại kèm cảnh báo ở đầu tin nhắn (`Task 3`).
4. **Xoá bản ghi duy nhất còn lại ở trang cuối (`page > 0`)**: Sau khi xác nhận xoá dòng #31 ở trang 2/2, phải tự động kẹp về trang 1/1 hợp lệ thay vì hiện trang rỗng (`Task 4`).
5. **Sửa dict kết quả `dict_service.lookup()` trong luồng thêm từ làm bẩn cache LRU**: Caller gán `info["meaning_vi"]` / `info["note"]` không được rò rỉ sang lần gọi `lookup()` hoặc `edit.fill_missing()` kế tiếp (`Task 2`).

---

### File Structure Map

- Modify: `src/telegram.py` — thêm `send_rich_message`, nhánh `markdown` cho `edit_message`, `md_escape`, `md_cell`, `md_table`.
- Modify: `tests/conftest.py` — `fake_fetch` hỗ trợ `sendRichMessage`, `sent_texts` đọc cả `text` và `rich_message.markdown`.
- Modify: `src/services/dict_service.py` — thêm cache LRU in-memory (128 mục, trả bản sao `dict`).
- Modify: `src/vocab_do.py` — cờ `schema:v2` giảm I/O cold-start, đọc `fsm` 1 lần trong `on_message`, chạy song song `answer_callback` + `_dispatch_callback`, nối callback mới (`vclr`, `vedit`, `vdel`), xoá dead code không dùng (`EDIT_FIELD_LABELS`, `search_words`, `log_review`, `_pick_due`).
- Modify: `src/keyboards.py` & `src/texts.py` — đồng bộ 100% icon + tiếng Việt cho mọi nút bấm và mẫu câu thông báo.
- Modify: `src/handlers/vocab_list.py` — menu CRUD Từ vựng (Phương án B), bảng GFM Markdown 1-query `ROW_NUMBER() OVER (ORDER BY w.id)`, chọn theo STT/từ giữ nguyên bảng khi sai/trùng, chi tiết từ có `✏️ Sửa` / `🗑 Xoá` / `◀️ Danh sách`.
- Modify: `src/handlers/edit.py` & `src/handlers/delete.py` — hiển thị đủ thuộc tính có icon, nút có icon tiếng Việt, bảo toàn `return_action` + `page` + `query` khi hoàn tất/huỷ.
- Modify: `src/handlers/games.py`, `src/handlers/add.py`, `src/handlers/lookup.py`, `src/handlers/import_export.py`, `src/handlers/review.py` — bảng GFM Markdown cho game chuyện chêm (tái sử dụng `message_id`, `ORDER BY RANDOM() LIMIT ?`), bổ sung icon preview `lookup.py` và nút `◀️ Quay lại` / `❌ Huỷ` cho các bước chờ gõ text.
- Modify/Create Tests: `tests/test_crud_tables.py`, `tests/test_games.py`, `tests/test_vocab_do.py`, `tests/test_delete_all.py`, `tests/test_review_queue.py`, `tests/test_lookup_optional.py`, `tests/test_dictionary_us.py`.
- Modify Docs: `docs/exp.md`, `docs/usecase.md`.

---

### Task 1: Rich Messages & GFM Markdown Table Engine

**Files:**
- Modify: `src/telegram.py`
- Modify: `tests/conftest.py`
- Test: `tests/test_crud_tables.py`

**Interfaces:**
- Produces in `src/telegram.py`:
  - `md_escape(text: str) -> str`
  - `md_cell(text: str | None, limit: int = 36) -> str`
  - `md_table(headers: list[str], rows: list[list[str]], aligns: list[str] | None = None) -> str`
  - `send_rich_message(env, chat_id, markdown: str, reply_markup=None) -> dict`
  - `edit_message(env, chat_id, message_id, text: str | None = None, reply_markup=None, *, markdown: str | None = None) -> dict`
- Produces in `tests/conftest.py`:
  - `fake_fetch` cấp `message_id` cho cả `"sendMessage"` và `"sendRichMessage"`.
  - `sent_texts(env)` trả `s["payload"].get("text") or s["payload"].get("rich_message", {}).get("markdown", "")`.

- [ ] **Step 1: Viết unit test kiểm tra `md_table`, `send_rich_message`, `edit_message(..., markdown=...)` và escape ký tự đặc biệt (RF1)**

Thêm vào đầu `tests/test_crud_tables.py`:

```python
def test_md_table_escapes_pipes_newlines_and_markup():
    import telegram as tg

    table = tg.md_table(
        ["#", "Từ", "Nghĩa"],
        [["1", "a|b\nc", "<tag> *bold* $10"]],
        aligns=["right", "left", "left"],
    )
    lines = table.splitlines()
    assert lines[0] == "| # | Từ | Nghĩa |"
    assert lines[1] == "|---:|:---|:---|"
    assert lines[2].startswith("| 1 | ") and lines[2].endswith(" |")
    # Mỗi dòng dữ liệu chỉ có đúng 4 dấu | làm vách ngăn cột (không tính \| đã escape)
    import re
    assert len(re.findall(r"(?<!\\)\|", lines[2])) == 4
    assert "\\|" in lines[2] and "\\<tag\\>" in lines[2] and "\\*bold\\*" in lines[2]


def test_rich_message_send_and_edit_payloads(do):
    import telegram as tg

    res = run(tg.send_rich_message(do.env, 111, "| A | B |\n|:---|:---|\n| 1 | 2 |"))
    mid = res["result"]["message_id"]
    sent = do.env.sent[-1]
    assert sent["method"] == "sendRichMessage"
    assert sent["payload"]["rich_message"] == {
        "markdown": "| A | B |\n|:---|:---|\n| 1 | 2 |",
        "skip_entity_detection": True,
    }
    run(tg.edit_message(do.env, 111, mid, markdown="**Cập nhật**"))
    edited = do.env.sent[-1]
    assert edited["method"] == "editMessageText"
    assert "text" not in edited["payload"]
    assert edited["payload"]["rich_message"] == {
        "markdown": "**Cập nhật**",
        "skip_entity_detection": True,
    }
```

- [ ] **Step 2: Chạy test để xác nhận FAIL**

Run: `uv run pytest tests/test_crud_tables.py -k "md_table or rich_message" -v`
Expected: FAIL với `AttributeError: module 'telegram' has no attribute 'md_table'`.

- [ ] **Step 3: Cài đặt Rich Message helpers trong `src/telegram.py` và cập nhật `tests/conftest.py`**

Trong `src/telegram.py`:
- Escape tập ký tự điều khiển Rich Markdown `\_*|~`[]()<>&=$#!` bằng `\` trong `md_escape(text: str) -> str`.
- `md_cell(text, limit=36)`: thay `\r`, `\n`, `\t` bằng space, gộp khoảng trắng thừa ở hai đầu, cắt `limit - 1 + "…"` nếu vượt `limit`, trả `"—"` nếu rỗng, rồi gọi `md_escape`.
- `md_table(headers, rows, aligns=None)`: sinh dòng header `| ... |`, dòng căn lề (`---:` cho `"right"`, `:---:` cho `"center"`, `:---` mặc định `"left"`), và các dòng dữ liệu.
- `send_rich_message` gửi tới endpoint `"sendRichMessage"` với `rich_message={"markdown": markdown, "skip_entity_detection": True}`.
- `edit_message` khi `markdown is not None` đặt `payload["rich_message"] = {"markdown": markdown, "skip_entity_detection": True}` (không gửi `text`/`parse_mode`/`disable_web_page_preview`); ngược lại giữ nguyên hành vi HTML.

Trong `tests/conftest.py`:
- `fake_fetch`: `if m in ("sendMessage", "sendRichMessage"):` sinh `message_id`.
- `sent_texts`: trả `s["payload"].get("text") or s["payload"].get("rich_message", {}).get("markdown", "")`.

- [ ] **Step 4: Chạy test xác nhận PASS**

Run: `uv run pytest tests/test_crud_tables.py -k "md_table or rich_message" -v`
Expected: PASS.

---

### Task 2: Tối ưu tốc độ DO, Song song Callback & Cache LRU Từ điển

**Files:**
- Modify: `src/services/dict_service.py`
- Modify: `src/vocab_do.py`
- Test: `tests/test_dictionary_us.py`
- Test: `tests/test_vocab_do.py`

**Interfaces:**
- Produces in `src/services/dict_service.py`:
  - `lookup(word: str) -> dict | None` — có cache LRU tối đa `CACHE_MAX = 128` theo key `word.strip().casefold()`, luôn trả `dict(cached)` (bản sao nông) để caller sửa không làm bẩn cache; hàm `clear_cache() -> None` hỗ trợ test khi cần.
- Produces in `src/vocab_do.py`:
  - `VocabularyDO.__init__`: bỏ qua DDL + `PRAGMA table_info` + seed defaults nếu `self.storage.kv.get("schema:v2")` đã tồn tại; lần đầu migrate xong ghi `self.storage.kv.put("schema:v2", "1")`.
  - `VocabularyDO.on_callback`: chạy `await asyncio.gather(answer_callback(self.env, cb["id"]), self._dispatch_callback(cb))` để song song hoá HTTP ack và xử lý nghiệp vụ.
  - `VocabularyDO.on_message`: chỉ đọc `fsm = self.storage.kv.get(f"fsm:{chat_id}")` đúng 1 lần duy nhất.

- [ ] **Step 1: Viết failing tests cho cache LRU từ điển (RF5), cold-start `schema:v2` và song song callback**

Thêm vào `tests/test_dictionary_us.py`:

```python
def test_lookup_caches_hits_and_returns_isolated_copy(monkeypatch):
    import asyncio
    from src.services import dict_service

    dict_service.clear_cache()
    calls = 0

    async def fake_fetch(url):
        nonlocal calls
        calls += 1
        class Res:
            status = 200
            async def json(self):
                return {"entries": [{"language": {"code": "en"}, "partOfSpeech": "noun",
                        "pronunciations": [{"type": "ipa", "text": "/həˈloʊ/", "tags": ["US"]}],
                        "senses": [{"definition": "greeting", "examples": ["Hello!"]}]}]}
        return Res()

    monkeypatch.setattr(dict_service, "fetch", fake_fetch)
    first = asyncio.run(dict_service.lookup("Hello"))
    first["meaning_vi"] = "bẩn cache"
    second = asyncio.run(dict_service.lookup("hello"))
    assert calls == 1
    assert "meaning_vi" not in second
    dict_service.clear_cache()
```

Thêm vào `tests/test_vocab_do.py`:

```python
def test_second_do_wakeup_skips_schema_ddl():
    from src.vocab_do import VocabularyDO
    do = _fresh()
    sql_calls = []
    orig = do.ctx.storage.sql.exec
    do.ctx.storage.sql.exec = lambda sql, *a: (sql_calls.append(sql), orig(sql, *a))[1]
    VocabularyDO(do.ctx, do.env)
    assert sql_calls == []


def test_callback_runs_ack_and_edit_concurrently(monkeypatch):
    import telegram as tg
    do = _fresh()
    in_flight = 0
    max_in_flight = 0

    async def tracked_fetch(url, method=None, headers=None, body=None):
        nonlocal in_flight, max_in_flight
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1
        import json, types
        payload = json.loads(body)
        async def _json():
            return {"ok": True, "result": {"message_id": 500}}
        return types.SimpleNamespace(status=200, json=_json)

    monkeypatch.setattr(tg, "fetch", tracked_fetch)
    feed_cb(do, "menu:help", message_id=500)
    assert max_in_flight >= 2
```

- [ ] **Step 2: Chạy test để xác nhận FAIL**

Run: `uv run pytest tests/test_dictionary_us.py::test_lookup_caches_hits_and_returns_isolated_copy tests/test_vocab_do.py -k "skips_schema_ddl or ack_and_edit_concurrently" -v`
Expected: FAIL.

- [ ] **Step 3: Triển khai LRU cache trong `src/services/dict_service.py` và tối ưu `src/vocab_do.py`**

- Trong `src/services/dict_service.py`: dùng `collections.OrderedDict` (`_CACHE`, `CACHE_MAX = 128`), chuẩn hoá key `key = word.strip().casefold()`. Hit thì `move_to_end(key)` và `return dict(_CACHE[key])`. Miss và API trả hợp lệ thì lưu bản ghi chuẩn hoá vào `_CACHE` (nếu vượt `CACHE_MAX` thì `popitem(last=False)`) rồi `return dict(result)`. Không cache kết quả `None` (tránh kẹt lỗi mạng tạm thời). Thêm `clear_cache()`.
- Trong `src/vocab_do.py`:
  - `__init__`: kiểm tra `if not self.storage.kv.get("schema:v2"):` trước khi chạy `SCHEMA`, `PRAGMA table_info(words)`, seed `DEFAULTS`, rồi `self.storage.kv.put("schema:v2", "1")`.
  - Tách phần thân xử lý `parts` của `on_callback` sang `async def _dispatch_callback(self, cb: dict, chat_id, message_id, data: str)` và trong `on_callback` gọi `await asyncio.gather(answer_callback(self.env, cb["id"]), self._dispatch_callback(cb, chat_id, message_id, data))`.
  - Trong `on_message`: lấy `fsm = self.storage.kv.get(f"fsm:{chat_id}")` đúng 1 lần trước nhánh `pending` và tái sử dụng biến `fsm`.
  - Xoá dead code không còn nơi nào gọi trong `src/vocab_do.py`: `EDIT_FIELD_LABELS`, `search_words`, `log_review`, `_pick_due`.

- [ ] **Step 4: Chạy test xác nhận PASS**

Run: `uv run pytest tests/test_dictionary_us.py tests/test_vocab_do.py tests/test_correctness.py -q`
Expected: PASS (kể cả `test_old_schema_migration_preserves_data`).

---

### Task 3: Chuẩn hoá Bảng Từ vựng & Chọn Bản ghi theo Phương án B (`vocab_list.py`)

**Files:**
- Modify: `src/handlers/vocab_list.py`
- Modify: `src/texts.py`
- Modify: `src/vocab_do.py`
- Test: `tests/test_crud_tables.py`

**Interfaces:**
- Produces in `src/handlers/vocab_list.py`:
  - `display(do, chat_id, body: str, markup, message_id=None, *, rich: bool = False)` — khi `rich=True`, gọi `edit_message(..., markdown=body)` hoặc `send_rich_message(...)`; khi `rich=False`, gọi `edit_message(..., text=body)` hoặc `send_message(...)`; luôn lưu lại `message_id` vào FSM nếu FSM đang mở.
  - `finish(do, chat_id, body: str, message_id=None)` — đọc `state = fsm`: nếu `return_action` (hoặc `action`) thuộc `("edit", "delete")` hoặc `(return_action == "vocab" and state.get("from_table"))`, gọi `show_page(do, chat_id, state.get("page", 0), message_id, action=target_action, query=state.get("query", ""), notice=body, table=True)`; ngược lại mở menu `📚 Kho từ vựng` kèm thông báo `body`.
  - `show_menu(do, chat_id, message_id=None, *, notice: str | None = None)` — hiển thị menu CRUD Phương án B:
    - Hàng 1: `[("➕ Thêm từ", "menu:add"), ("👁 Xem", "vact:view")]`
    - Hàng 2: `[("✏️ Sửa", "vact:edit"), ("🗑 Xoá", "vact:delete")]`
    - Hàng 3: `[("🔎 Tìm kiếm", "vsrch")]`
    - Hàng 4: `[("🏠 Menu", "menu:home")]`
  - `show_page(do, chat_id, page: int = 0, message_id=None, *, action=None, query=None, notice=None, table=None)` — truy vấn 1 câu SQL CTE `ROW_NUMBER() OVER (ORDER BY w.id) AS stt` + `COUNT(*) OVER () AS total` (chỉ chạy câu SQL thứ 2 khi `page > 0` và trang đó rỗng do vừa xoá hết dòng trang cuối). Render bằng `md_table(["#", "Từ", "IPA", "Nghĩa", "Hạn"], rows, aligns=["right", "left", "left", "left", "left"])` qua `display(..., rich=True)`. Lưu `page` và `query` trong FSM. Nút điều hướng gồm `⬅️ Trước`, `➡️ Sau`, `🔎 Tìm kiếm`, `✖️ Bỏ lọc` (`vclr`, khi có `query`), `🗑 Xoá tất cả` (`del:all`, khi `action == "delete"` và `total > 0`), và hàng cuối `[("◀️ Từ vựng", "menu:vocab"), ("🏠 Menu", "menu:home")]`.
  - `clear_filter(do, chat_id, message_id=None)` — xử lý callback `vclr`: gọi `show_page(..., page=0, query="", table=True)` giữ nguyên `action`.
  - `select_word(do, chat_id, selection: str, message_id=None)` — chọn theo STT toàn cục hoặc `word = ? COLLATE NOCASE` trong phạm vi `query`:
    - Không khớp dòng nào → gọi lại `show_page` ở đúng `page` và `query` hiện tại với `notice="⚠️ Không tìm thấy từ khớp. Gõ STT hiển thị hoặc tên từ chính xác."` (RF3).
    - Khớp `> 1` dòng trùng tên từ → gọi `show_page` lọc theo từ đó với `notice="⚠️ Có nhiều từ trùng tên. Gõ STT hiển thị để chọn đúng dòng."` (RF2).
    - Khớp đúng 1 dòng → chuyển sang `edit.pick_word`, `delete.pick_word`, hoặc `vocab_list.pick_word` (truyền/giữ `page`, `query`, `return_action`).
  - `pick_word(do, chat_id, word_id: int, message_id=None)` — hiển thị `VOCAB_DETAIL` có đủ icon đầu dòng và bàn phím `[("✏️ Sửa", f"vedit:{word_id}"), ("🗑 Xoá", f"vdel:{word_id}")]` + `[("◀️ Danh sách", f"vpg:{page}"), ("🏠 Menu", "menu:home")]`; giữ FSM `flow="vocab_select"` (`table=True`) để người dùng có thể gõ tiếp STT/từ khác xem liền mạch.

- [ ] **Step 1: Viết tests cho bảng Markdown CRUD, chọn STT/từ, giữ bảng khi sai (RF3) và xử lý từ trùng tên (RF2)**

Cập nhật/bổ sung trong `tests/test_crud_tables.py`:

```python
def rich_text(do):
    p = do.env.sent[-1]["payload"]
    return p.get("text") or p.get("rich_message", {}).get("markdown", "")


def test_vocab_menu_has_full_crud_actions_and_renders_markdown_table(do):
    seed(do, 2)
    run(vocab_list.show_menu(do, 111, 500))
    assert {"menu:add", "vact:view", "vact:edit", "vact:delete", "vsrch", "menu:home"}.issubset(set(callbacks(do)))
    run(vocab_list.select_action(do, 111, "vocab", 500))
    md = payload(do)["rich_message"]["markdown"]
    assert "| # | Từ | IPA | Nghĩa | Hạn |" in md
    assert "<pre>" not in md
    assert not any(d.startswith(("editw:", "delw:", "vword:")) for d in callbacks(do))


def test_invalid_selection_preserves_markdown_table_page_and_filter(do):
    seed(do, 35)
    run(vocab_list.show_page(do, 111, 1, 500, action="delete", query="word", table=True))
    run(vocab_list.select_word(do, 111, "999", 500))
    md = payload(do)["rich_message"]["markdown"]
    assert "Không tìm thấy" in md
    assert "| # | Từ |" in md and "word30" in md and "Trang 2/2" in md
    assert do.storage.kv.get("fsm:111")["action"] == "delete"
    assert do.storage.kv.get("fsm:111")["page"] == 1


def test_duplicate_word_selection_requires_stt_instead_of_guessing(do):
    do.insert_words_bulk(111, [
        {"word": "bank", "phonetic": None, "define_en": "river side", "meaning": "bờ sông", "example": None, "note": None},
        {"word": "bank", "phonetic": None, "define_en": "money place", "meaning": "ngân hàng", "example": None, "note": None},
    ])
    run(vocab_list.show_page(do, 111, 0, 500, action="delete", table=True))
    run(vocab_list.select_word(do, 111, "bank", 500))
    assert do.count_words() == 2
    assert do.storage.kv.get("fsm:111")["flow"] == "delete_select"
    md = payload(do)["rich_message"]["markdown"]
    assert "trùng tên" in md and "bờ sông" in md and "ngân hàng" in md
```

- [ ] **Step 2: Chạy test để xác nhận FAIL**

Run: `uv run pytest tests/test_crud_tables.py -k "full_crud_actions or preserves_markdown_table or duplicate_word" -v`
Expected: FAIL.

- [ ] **Step 3: Cập nhật `src/texts.py`, `src/handlers/vocab_list.py` và callback routing trong `src/vocab_do.py`**

- Chuẩn hoá các chuỗi `VOCAB_*` trong `src/texts.py` sang tiếng Việt có đầy đủ icon (`📚 <b>Kho từ vựng</b> ({total} từ)`, `VOCAB_DETAIL` có `📖`, `🔊`, `🇬🇧`, `🇻🇳`, `📝`, `ℹ️`, `⏰`).
- Viết lại `src/handlers/vocab_list.py` dùng CTE `ROW_NUMBER() OVER (ORDER BY w.id) AS stt` và `md_table` từ `telegram.py`.
- Nối `vclr`, `vedit:{id}`, `vdel:{id}` trong `src/vocab_do.py`:
  - `vedit:{id}` đặt `return_action="vocab"`, `from_table=True` trong FSM rồi gọi `edit.pick_word(self, chat_id, int(parts[1]), message_id)`.
  - `vdel:{id}` đặt `return_action="vocab"`, `from_table=True` trong FSM rồi gọi `delete.pick_word(self, chat_id, int(parts[1]), message_id)`.

- [ ] **Step 4: Chạy test xác nhận PASS**

Run: `uv run pytest tests/test_crud_tables.py -k "full_crud_actions or preserves_markdown_table or duplicate_word" -v`
Expected: PASS.

---

### Task 4: Chuẩn hoá Sửa / Xoá (`edit.py`, `delete.py`), Kẹp Trang Cuối & Đồng bộ Toàn bộ Icon UI

**Files:**
- Modify: `src/handlers/edit.py`
- Modify: `src/handlers/delete.py`
- Modify: `src/handlers/games.py`
- Modify: `src/handlers/lookup.py`
- Modify: `src/handlers/add.py`
- Modify: `src/handlers/import_export.py`
- Modify: `src/handlers/review.py`
- Modify: `src/keyboards.py`
- Modify: `src/texts.py`
- Test: `tests/test_crud_tables.py`, `tests/test_games.py`, `tests/test_delete_all.py`, `tests/test_vocab_do.py`, `tests/test_review_queue.py`, `tests/test_lookup_optional.py`

**Interfaces:**
- `src/handlers/edit.py`:
  - `FIELD_LABELS = {"word": "🔤 Từ", "phonetic": "🔊 Phiên âm", "define_en": "🇬🇧 Nghĩa EN", "meaning": "🇻🇳 Nghĩa VI", "example": "📝 Ví dụ", "note": "ℹ️ Ghi chú"}`
  - `pick_word(do, chat_id, word_id: int, message_id=None)` hiển thị đủ 6 trường hiện tại kèm icon + nút chọn trường + `[("✨ Điền thông tin thiếu", f"editfill:{word_id}")]` + `[("◀️ Quay lại", "edit:cancel")]`, bảo toàn `page`, `query`, `return_action`, `from_table` trong FSM.
- `src/handlers/delete.py`:
  - `pick_word(do, chat_id, word_id: int, message_id=None)` hiển thị chi tiết từ kèm icon + `[("🗑 Xoá vĩnh viễn", f"del:confirm:{word_id}"), ("↩️ Giữ lại", "del:cancel")]`, bảo toàn `page`, `query`, `return_action`, `from_table`.
  - `delete_all_confirm_kb()` trong `keyboards.py`: `[("🗑 Xoá vĩnh viễn", "delall:confirm"), ("↩️ Giữ lại", "delall:cancel")]`.
- `src/handlers/games.py`:
  - `story_on_count(do, chat_id, text: str)`: dùng `SELECT word, meaning FROM words ORDER BY RANDOM() LIMIT ?` và render bảng `md_table(["STT", "Từ", "Nghĩa"], ...)` qua Rich Message trên cùng `message_id` trong FSM (edit tại chỗ cả khi nhập số không hợp lệ lẫn khi hiện bảng từ).
- `src/handlers/lookup.py`, `add.py`, `import_export.py`, `keyboards.py`, `review.py`:
  - `lookup.py`: mọi dòng thông tin ở `start()` và `_preview_body()` có icon đầu dòng (`🔊 IPA...`, `🏷 POS: ...`, `🇬🇧 EN: ...`, `🇻🇳 VI: ...`, `📝 Ví dụ: ...`, `ℹ️ Note: ...`).
  - `add.py` & `import_export.py`: các bước chờ nhập text (`add_input`, `lookup_word`, `import_input`) đều có nút `[("◀️ Quay lại", ...), ("🏠 Menu", "menu:home")]` thay vì `None`.
  - Thống nhất `🏠 Menu` cho mọi nút nhảy thẳng về Menu chính (`BACK_MENU = ("🏠 Menu", "menu:home")`) và `◀️ ...` cho mọi nút lùi 1 cấp về menu con/bảng trước đó; xoá `EDIT_FIELDS_KB` và `SHOW_ANSWER_KB` không dùng trong `keyboards.py`.

- [ ] **Step 1: Viết tests cho xoá dòng cuối trang 2 kẹp về trang 1 (RF4), luồng `vedit`/`vdel` quay lại bảng Xem, bảng Markdown trong `games.py` và kiểm tra toàn bộ nút có icon**

Thêm vào `tests/test_crud_tables.py` và cập nhật `tests/test_games.py`:

```python
def test_deleting_last_item_on_page_2_clamps_to_page_1(do):
    seed(do, 31)
    run(vocab_list.show_page(do, 111, 1, 500, action="delete", table=True))
    assert "Trang 2/2" in rich_text(do)
    run(vocab_list.select_word(do, 111, "31", 500))
    run(delete.confirm(do, 111, 31, message_id=500))
    text = rich_text(do)
    assert "Trang 1/1" in text and "word29" in text


def test_detail_view_edit_and_delete_return_to_view_table(do):
    seed(do, 2)
    from tests.test_vocab_do import feed_cb, feed_msg
    feed_msg(do, "/vocab")
    mid = do.env.sent[-1]["result"]["message_id"]
    feed_cb(do, "vact:view", message_id=mid)
    feed_msg(do, "1")
    assert {"vedit:1", "vdel:1"}.issubset(set(callbacks(do)))
    feed_cb(do, "vedit:1", message_id=mid)
    feed_cb(do, "edit:cancel", message_id=mid)
    assert do.storage.kv.get("fsm:111")["action"] == "vocab"
    assert "| # | Từ |" in rich_text(do)


def test_every_keyboard_button_has_leading_icon():
    import keyboards as kbs
    boards = [
        kbs.MENU_KB, kbs.ADD_MENU_KB, kbs.GAMES_MENU_KB, kbs.SETTINGS_MENU_KB,
        kbs.MODE_KB, kbs.QUIET_KB, kbs.REMINDER_KB, kbs.CONFIRM_ADD_KB,
        kbs.delete_all_confirm_kb(), kbs.LOOKUP_EXAMPLE_KB, kbs.LOOKUP_NOTE_KB,
        kbs.CONFIRM_LOOKUP_KB, kbs.kb_back_menu(), kbs.fmt_rate_kb(1),
        edit._edit_picker_kb(1),
    ]
    for board in boards:
        for row in board:
            for btn in row:
                assert not btn["text"][0].isascii(), f"Button missing icon: {btn['text']}"
```

Trong `tests/test_games.py`: cập nhật test kiểm tra `rich_message["markdown"]` chứa `| STT | Từ | Nghĩa |`, không chứa `<pre>`, escape an toàn `<漢字😀>` & `a|b`, tổng độ dài `<= 32768`, và tái sử dụng `message_id` khi có sẵn trong FSM.

- [ ] **Step 2: Chạy test để xác nhận FAIL**

Run: `uv run pytest tests/test_crud_tables.py tests/test_games.py -v`
Expected: FAIL.

- [ ] **Step 3: Cài đặt thay đổi trên `edit.py`, `delete.py`, `games.py`, `lookup.py`, `add.py`, `import_export.py`, `review.py`, `keyboards.py`, `texts.py` và cập nhật các assertion chuỗi tiếng Việt trong bộ test hồi quy**

- Triển khai đầy đủ theo Interfaces trên.
- Cập nhật các chuỗi tiếng Anh cũ trong `tests/test_crud_tables.py`, `tests/test_vocab_do.py`, `tests/test_delete_all.py`, `tests/test_review_queue.py` khớp với giao diện tiếng Việt + Rich Markdown mới (giữ nguyên toàn bộ kiểm chứng logic: 1 message xuyên suốt, rollback transaction, idempotency, FSRS, security owner check).

- [ ] **Step 4: Chạy toàn bộ test suite để xác nhận xanh 100%**

Run: `uv run pytest -q`
Expected: 100% PASS, 0 warnings/errors.

---

### Task 5: Kiểm tra Vệ sinh Codebase & Cập nhật Tài liệu (`exp.md` + `usecase.md`)

**Files:**
- Modify: `docs/exp.md`
- Modify: `docs/usecase.md`

**Interfaces:**
- Consumes: toàn bộ thay đổi từ Task 1–4.
- Produces: tài liệu `docs/exp.md` và `docs/usecase.md` phản ánh đúng luồng CRUD Phương án B, Rich Markdown Table Bot API 10.1+, các tối ưu hiệu năng và quy ước icon.

- [ ] **Step 1: Chạy các kiểm tra tĩnh bắt buộc từ `docs/exp.md`**

Run:
```bash
grep -rn "storage\.\(get\|put\|delete\)(" src/ | grep -v kv || true
git diff --check
```
Expected: Không có lệnh gọi `storage.get/put/delete` thiếu `.kv`, `git diff --check` sạch hoàn toàn.

- [ ] **Step 2: Cập nhật `docs/exp.md` và `docs/usecase.md`**

- Ghi nhận mục mới ngày `11/11/2026` vào `docs/exp.md` (Rich Messages `sendRichMessage`/`editMessageText(rich_message)` cho GFM Markdown table, `ROW_NUMBER() OVER` giảm `O(N²)` → `O(N)`, song song `answerCallbackQuery` qua `asyncio.gather`, `schema:v2` cold-start guard, LRU cache `dict_service`).
- Cập nhật `UC7` và `UC8` trong `docs/usecase.md` khớp với giao diện tiếng Việt, luồng CRUD Phương án B và bảng Markdown native.

- [ ] **Step 3: Chạy lại toàn bộ test xác nhận lần cuối**

Run: `uv run pytest -q`
Expected: Toàn bộ test PASS.
