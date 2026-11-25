# Thiết kế chuẩn hoá CRUD, Markdown Table & Tối ưu phản hồi — Vocabking

Ngày: 2026-11-11

## 1. Mục tiêu & Lý do (Intent & Why)
- **Chuẩn hoá CRUD từ vựng**: Thay toàn bộ cơ chế sinh nút theo từng bản ghi (`view1`, `editw:1`, `delw:1`...) bằng luồng chuẩn CRUD theo **Phương án B (Chọn hành động trước → Mở bảng → Gõ STT hoặc tên từ)**. Tránh giới hạn nút của Telegram, thao tác nhanh khi kho từ lớn, giữ nguyên ngữ cảnh (action/trang/bộ lọc) khi hoàn tất hoặc huỷ.
- **Markdown Table native**: Thay toàn bộ bảng ASCII/box-drawing trong `<pre>` bằng GFM Markdown Table hiển thị trực tiếp trên Telegram qua Rich Messages (`sendRichMessage` / `editMessageText(rich_message)` của Telegram Bot API 10.1+).
- **Tối ưu tốc độ phản hồi**: Cắt round-trip mạng tuần tự khi bấm nút, loại bỏ truy vấn SQL `O(N²)` khi phân trang/chọn STT, giảm đọc KV/SQL lặp trên Durable Object, cache tra cứu từ điển.
- **Đồng bộ icon & giao diện**: Rà soát toàn bộ nút bấm và mẫu tin nhắn để đảm bảo 100% nút có icon nhất quán, các màn preview/chi tiết có icon đầu dòng đồng bộ, ngôn ngữ hiển thị thống nhất tiếng Việt.

## 2. Goals, Non-goals & Anti-goals
- **Goals**:
  - Đủ 4 thao tác **Thêm / Xem / Sửa / Xoá** quy hoạch rõ trong menu `📚 Từ vựng` (vẫn giữ nút tắt `➕ Thêm từ` ở Menu chính).
  - Mọi thao tác chọn đối tượng để Xem, Sửa, Xoá đều thực hiện bằng cách **gõ STT hiển thị hoặc tên từ** trên bảng phân trang/lọc.
  - Mọi bảng dữ liệu (bảng Từ vựng/Sửa/Xoá và bảng từ game Viết chuyện chêm) render bằng GFM Markdown table qua `rich_message`.
  - Mọi bước trong cùng luồng tái sử dụng `message_id` (edit tại chỗ, không xả tin nhắn rác).
  - Giảm latency mỗi callback ~1 RTT mạng và giảm độ phức tạp SQL phân trang từ `2 queries O(N²)` xuống `1 query O(N)`.
- **Non-goals**:
  - Không thay đổi thuật toán FSRS, công thức tính quota hàng ngày hay cơ chế `review:pending` chống spam nhắc từ.
  - Không thay đổi định dạng nhập bulk 6 trường `từ|phiên âm|defineEN|nghĩaVI|ví dụ|note` hoặc JSONL import/export.
- **Anti-goals**:
  - Không bao giờ sinh inline button riêng cho từng dòng từ vựng trong danh sách.
  - Không dùng bảng ký tự ASCII/Unicode (`─`, `│`, `┼`, `ljust`) bọc trong `<pre>`.
  - Không làm mất bảng đang xem khi người dùng gõ sai STT/từ (phải giữ nguyên trang bảng kèm thông báo lỗi).

## 3. Các phương án đã cân nhắc (Approaches)
1. **Phương án A — Master–Detail 1 bảng duy nhất**: Vào `📚 Từ vựng` hiện thẳng bảng; gõ STT/từ mở chi tiết rồi mới chọn Sửa/Xoá. Ít hơn 1 bước khi chỉ xem, nhưng chậm hơn khi cần sửa/xoá liên tiếp nhiều từ.
2. **Phương án B — Chọn hành động trước (Đã chọn)**: Vào `📚 Từ vựng` chọn rõ hành động CRUD (`➕ Thêm từ`, `👁 Xem`, `✏️ Sửa`, `🗑 Xoá`, `🔎 Tìm kiếm`), mở bảng Markdown tương ứng với hành động đó và gõ `STT` hoặc `từ` để thực thi ngay; xong hoặc huỷ đều quay lại đúng bảng hành động (giữ nguyên trang & bộ lọc). Lệnh tắt `/vocab`, `/add`, `/edit [kw]`, `/delete [kw]` nhảy thẳng vào đúng chế độ.

## 4. Chi tiết thiết kế kỹ thuật

### 4.1 Luồng CRUD chuẩn (Phương án B)
- **Menu `📚 Từ vựng` (`menu:vocab` hoặc `/vocab`)**:
  - Nội dung: `📚 <b>Kho từ vựng</b> ({total} từ)\n\nChọn thao tác:`
  - Bàn phím:
    - `[➕ Thêm từ ("menu:add")]` `[👁 Xem ("vact:view")]`
    - `[✏️ Sửa ("vact:edit")]` `[🗑 Xoá ("vact:delete")]`
    - `[🔎 Tìm kiếm ("vsrch")]`
    - `[🏠 Menu ("menu:home")]`
- **Bảng danh sách dùng chung (`vocab_list.show_page`) cho 3 action `vocab` (Xem), `edit` (Sửa), `delete` (Xoá)**:
  - Tiêu đề theo mode:
    - `vocab`: `👁 **Xem từ vựng** ({total} từ)`
    - `edit`: `✏️ **Sửa từ vựng** ({total} từ)`
    - `delete`: `🗑 **Xoá từ vựng** ({total} từ)`
  - Nếu có bộ lọc `query`: hiển thị dòng phụ `🔎 Lọc theo: \`{query}\` ({matched} kết quả)`.
  - Nếu có `notice` (VD vừa sửa/xoá xong hoặc gõ STT không tồn tại): hiển thị ngay phía trên bảng.
  - Bảng GFM Markdown 5 cột (`PAGE_SIZE = 30`):
    `| # | Từ | IPA | Nghĩa | Hạn |`
    `|---:|:---|:---|:---|:---|`
  - Chân trang: `Trang {page}/{pages} · Gõ STT hoặc tên từ để {xem/sửa/xoá}.`
  - Bàn phím điều hướng dưới bảng:
    - Hàng điều hướng: `[⬅️ Trước ("vpg:{p-1}")]` (nếu `page > 0`), `[➡️ Sau ("vpg:{p+1}")]` (nếu `page < max_page`), `[🔎 Tìm kiếm ("vsrch")]`, và `[✖️ Bỏ lọc ("vclr")]` (chỉ hiện khi `query` khác rỗng).
    - Hàng riêng khi `action == "delete"` và kho có từ: `[🗑 Xoá tất cả ("del:all")]`.
    - Hàng quay lại: `[◀️ Từ vựng ("menu:vocab")]` `[🏠 Menu ("menu:home")]`.
- **Cơ chế chọn đối tượng (`vocab_list.select_word`)**:
  - Nhận input text khi FSM đang ở `{action}_select` (`vocab_select` với `table=True`, `edit_select`, `delete_select`), hoặc đang ở màn `vocab_detail` (cho phép gõ tiếp STT/từ khác để xem nhanh).
  - Nếu đang ở menu `📚 Từ vựng` (`table=False`) mà người dùng gõ STT hoặc từ: tự động chuyển sang chọn từ ở chế độ `vocab` (Xem) để phản hồi tự nhiên không báo lỗi vô lý.
  - Tra cứu trong tập đang lọc (`query`):
    - Input toàn chữ số ASCII → khớp chính xác cột `stt` toàn cục (`ROW_NUMBER() OVER (ORDER BY id)`).
    - Input chữ → khớp không phân biệt hoa thường `word = ? COLLATE NOCASE`. **Quyết định thiết kế (builder's call)**: nếu có `> 1` bản ghi trùng tên từ, không tự đoán dòng đầu tiên mà hiển thị bảng lọc đúng các bản ghi trùng đó kèm thông báo `⚠️ Có nhiều từ trùng tên. Gõ STT hiển thị để chọn đúng dòng.` để tránh sửa/xoá nhầm.
  - Nếu không khớp bản ghi nào: gọi lại `show_page` ở đúng `page` và `query` hiện tại kèm `notice="⚠️ Không tìm thấy từ khớp. Gõ STT hiển thị hoặc tên từ chính xác."` — **không làm mất bảng**.
- **Chi tiết từng hành động sau khi chọn bản ghi**:
  - **Xem (`vocab_list.pick_word`)**:
    - Hiển thị chi tiết từ với đầy đủ icon từng dòng:
      `📖 <b>#{stt} — {word}</b>`
      `🔊 IPA: {phonetic}`
      `🇬🇧 EN: {define_en}`
      `🇻🇳 VI: {meaning}`
      `📝 Ví dụ: {example}`
      `ℹ️ Ghi chú: {note}`
      `⏰ Hạn ôn: {due}`
    - Nút dưới màn chi tiết:
      - Hàng 1 (thao tác trên bản ghi hiện hành): `[✏️ Sửa ("vedit:{word_id}")]` `[🗑 Xoá ("vdel:{word_id}")]`
      - Hàng 2: `[◀️ Danh sách ("vpg:{page}")]` `[🏠 Menu ("menu:home")]`
  - **Sửa (`handlers/edit.py`)**:
    - `pick_word`: hiển thị toàn bộ 6 thuộc tính hiện tại của từ kèm icon (`🔤 Từ`, `🔊 Phiên âm`, `🇬🇧 Nghĩa EN`, `🇻🇳 Nghĩa VI`, `📝 Ví dụ`, `ℹ️ Ghi chú`) để đối chiếu trước khi sửa.
    - Bàn phím chọn trường sửa:
      - `[🔤 Từ ("editf:{id}:word")]` `[🔊 Phiên âm ("editf:{id}:phonetic")]`
      - `[🇬🇧 Nghĩa EN ("editf:{id}:define_en")]` `[🇻🇳 Nghĩa VI ("editf:{id}:meaning")]`
      - `[📝 Ví dụ ("editf:{id}:example")]` `[ℹ️ Ghi chú ("editf:{id}:note")]`
      - `[✨ Điền thông tin thiếu ("editfill:{id}")]`
      - `[◀️ Quay lại ("edit:cancel")]`
    - Bước nhập giá trị mới (`edit_value`): có nút `[❌ Huỷ ("edit:cancel")]`. Nhập `-` / `null` / `none` để xoá trống trường (trừ `word` bắt buộc khác rỗng).
    - Sửa xong hoặc bấm Huỷ: quay về đúng `page` + `query` của bảng `edit` (hoặc bảng `vocab` nếu nhảy sang từ `vedit:{id}`) kèm thông báo `✅ Đã cập nhật ...` / `↩️ Đã huỷ sửa.`
  - **Xoá (`handlers/delete.py`)**:
    - `pick_word`: hiển thị chi tiết từ + cảnh báo xoá kèm lịch sử ôn.
    - Bàn phím xác nhận xoá 1 từ: `[🗑 Xoá vĩnh viễn ("del:confirm:{id}")]` `[↩️ Giữ lại ("del:cancel")]`.
    - Bàn phím xác nhận xoá tất cả (`del:all`): `[🗑 Xoá vĩnh viễn ("delall:confirm")]` `[↩️ Giữ lại ("delall:cancel")]`.
    - Xoá xong hoặc Huỷ: **Quyết định thiết kế (builder's call)** — giống `vedit:{id}`, cả `vedit:{id}` và `vdel:{id}` khi gọi từ màn chi tiết Xem đều lưu `return_action="vocab"`, nên hoàn tất hoặc huỷ sẽ quay về đúng bảng Xem (giữ `page` & `query`); nếu vào từ bảng Xoá thì quay về đúng bảng Xoá (tự kẹp về `max_page` mới nếu trang cuối cạn dòng) kèm thông báo `✅ Đã xoá ...` / `↩️ Đã huỷ xoá.`
  - **Thêm (`handlers/add.py`, `handlers/lookup.py`)**:
    - Giữ nguyên hai chế độ `🔍 Tra từ điển` và `✍️ Nhập thủ công`, bổ sung nút `[◀️ Quay lại ("menu:add")]` / `[❌ Huỷ ("add:cancel")]` ở các bước chờ nhập text đang thiếu nút (`add_input`, `lookup_word`, `import_input`).
    - Hoàn tất hoặc huỷ trả về menu `📚 Từ vựng` trên cùng `message_id` kèm thông báo kết quả.

### 4.2 Markdown Table Native qua Telegram Rich Messages
- **Mở rộng `src/telegram.py`**:
  - `send_rich_message(env, chat_id, markdown, reply_markup=None) -> dict`: gọi endpoint `sendRichMessage` với payload:
    ```python
    {
        "chat_id": chat_id,
        "rich_message": {"markdown": markdown, "skip_entity_detection": True},
        ...
    }
    ```
  - `edit_message(env, chat_id, message_id, text=None, reply_markup=None, *, markdown=None) -> dict`:
    - Khi truyền `markdown`: gửi `{"chat_id": chat_id, "message_id": message_id, "rich_message": {"markdown": markdown, "skip_entity_detection": True}, ...}` tới `editMessageText`.
    - Khi truyền `text`: giữ nguyên `parse_mode="HTML"` như hiện tại (không phá vỡ các màn hình HTML sẵn có).
  - Helper `md_escape(s)` & `md_table(headers, rows, aligns)`:
    - Chuẩn hoá khoảng trắng (thay `\r`, `\n`, `\t` bằng space), cắt độ dài ô hợp lý (`word` ≤ 24, `ipa` ≤ 18, `meaning` ≤ 36, game `meaning` ≤ 48), escape các ký tự điều khiển Rich Markdown (`\`, `|`, `*`, `_`, `~`, `` ` ``, `[`, `]`, `<`, `>`, `&`, `=`, `$`, `#`, `!`) để dữ liệu người dùng có chứa `<tag>`, `a|b`, `*bold*`, `$10` đều hiển thị nguyên văn an toàn, không làm vỡ cấu trúc cột bảng.
    - Giới hạn tổng độ dài Rich Message ≤ 32.768 UTF-8 bytes và ≤ 500 blocks theo chuẩn Bot API 10.1+ (với `PAGE_SIZE = 30` dòng chỉ ~2.000 bytes và ~35 blocks, dư sức chứa trọn không bị cắt cột như `<pre>` 4.096 ký tự).
- **Nơi áp dụng Markdown Table**:
  1. `vocab_list.show_page` (bảng Xem / Sửa / Xoá từ vựng): dùng `display(..., markdown=body)`.
  2. `games.story_on_count` (bảng từ ngẫu nhiên của game Viết chuyện chêm): dùng `display` / `edit_message(..., markdown=...)` trên chính `message_id` của luồng game (sửa luôn lỗi gửi tin mới rời rạc khi gõ sai số lượng hoặc khi hiện bảng từ).

### 4.3 Tối ưu tốc độ phản hồi (Performance)
1. **Chạy song song `answerCallbackQuery` và xử lý callback (`src/vocab_do.py`)**:
   - Đổi `await answer_callback(...)` tuần tự sang `await asyncio.gather(answer_callback(self.env, cb["id"]), self._dispatch_callback(cb))`. Tiết kiệm trọn 1 chuyến mạng HTTPS tới Telegram (~100–250ms) trên mọi thao tác bấm nút.
2. **Truy vấn bảng phân trang 1-pass `O(N)` bằng Window Function (`src/handlers/vocab_list.py`)**:
   - Thay thế 2 truy vấn chứa correlated subquery `(SELECT COUNT(*) FROM words n WHERE n.id <= w.id)` (`O(N²)`) bằng 1 CTE duy nhất:
     ```sql
     WITH numbered AS (
       SELECT w.id, w.word, w.phonetic, w.meaning, c.due,
              ROW_NUMBER() OVER (ORDER BY w.id) AS stt
       FROM words w LEFT JOIN cards c ON c.word_id = w.id
     ),
     filtered AS (
       SELECT *, COUNT(*) OVER () AS total FROM numbered
       WHERE ...
     )
     SELECT * FROM filtered ORDER BY id LIMIT ? OFFSET ?
     ```
   - Lưu ý khi `page * PAGE_SIZE >= total` (ví dụ vừa xoá dòng cuối của trang cuối): chỉ khi kết quả rỗng mà `page > 0` mới truy vấn lại trang cuối hợp lệ, nên 99% trường hợp chỉ tốn **đúng 1 câu SQL**.
   - Tương tự ở `select_word` và `pick_word`: dùng CTE `ROW_NUMBER() OVER (ORDER BY id)` thay cho correlated `COUNT(*)`.
3. **Lấy từ ngẫu nhiên `O(K)` cho Game (`src/handlers/games.py`)**:
   - Đổi `SELECT word, meaning FROM words` + `random.sample` sang `SELECT word, meaning FROM words ORDER BY RANDOM() LIMIT ?` (không kéo cả nghìn dòng lên RAM Python).
4. **Giảm I/O khởi tạo & cache trạng thái nóng trong `VocabularyDO` (`src/vocab_do.py`)**:
   - Dùng cờ RAM + KV `schema:v2` để bỏ chạy lại DDL + `PRAGMA table_info` + 5 lần `kv.get("set:*")` mỗi lần khởi tạo khi DB đã migrate xong (vẫn kiểm tra an toàn nếu bảng `words` chưa có cột `define_en` khi mở DB cũ chưa có cờ `schema:v2`).
   - Cache in-memory cho `fsm` (`self._fsm: dict[int, dict | None]`) đi qua `get_fsm(chat_id)` / `set_fsm(chat_id, state)` (đồng bộ với `transactionSync` rollback khi cần) và đọc `fsm` đúng 1 lần trong `on_message`.
5. **Cache LRU kết quả tra từ điển (`src/services/dict_service.py`)**:
   - Lưu tối đa 128 kết quả `lookup(word)` thành công gần nhất trong `OrderedDict` (trả bản sao `dict` để caller sửa `meaning_vi`/`note` không làm bẩn cache). Tránh gọi lặp API ngoài khi tra lại hoặc bấm `✨ Điền thông tin thiếu`.

### 4.4 Rà soát & đồng bộ Icon + Ngôn ngữ hiển thị
Quy ước chung toàn bot:
- Điều hướng: `◀️ ...` = quay lại cấp ngay trước đó; `🏠 Menu` = về thẳng Menu chính; `❌ Huỷ` = huỷ thao tác nhập/xác nhận; `✅ ...` = xác nhận lưu/thực thi; `↩️ Giữ lại` = không xoá.
- Thuộc tính từ vựng (mọi màn preview / chi tiết / nút sửa đều thống nhất 1 bộ icon):
  - `🔤` Từ vựng (`word`)
  - `🔊` Phiên âm IPA (`phonetic`)
  - `🏷` Từ loại (`pos`)
  - `🇬🇧` Định nghĩa tiếng Anh (`define_en`)
  - `🇻🇳` Nghĩa tiếng Việt (`meaning`)
  - `📝` Ví dụ (`example`)
  - `ℹ️` Ghi chú (`note`)
  - `⏰` Hạn ôn (`due`)
- Các vị trí được bổ sung/chuẩn hoá:
  - `keyboards.py`: `delete_all_confirm_kb` → `🗑 Xoá vĩnh viễn` / `↩️ Giữ lại`; xoá các keyboard chết không còn dùng nếu test không import.
  - `handlers/edit.py`: nút chọn trường có đủ icon (`🔤 Từ`, `🔊 Phiên âm`, `🇬🇧 Nghĩa EN`, `🇻🇳 Nghĩa VI`, `📝 Ví dụ`, `ℹ️ Ghi chú`, `✨ Điền thông tin thiếu`, `◀️ Quay lại`); màn `pick_word` hiện đủ 6 thuộc tính kèm icon.
  - `handlers/delete.py`, `handlers/vocab_list.py`, `texts.py`: chuyển toàn bộ thông báo và nhãn nút còn sót tiếng Anh sang tiếng Việt có icon đồng bộ.
  - `handlers/lookup.py`: thêm icon đầu dòng (`🔊`, `🏷`, `🇬🇧`, `🇻🇳`, `📝`, `ℹ️`) ở cả bước hiển thị kết quả tra từ và bước preview lưu từ.
  - `handlers/add.py`, `handlers/import_export.py`: thêm nút `◀️ Quay lại` / `❌ Huỷ` ở bước chờ gõ dữ liệu; thêm icon `📥`/`📤` và `🏠 Menu` nhất quán.

## 5. Phần để dành cho bước lập trình (Builder's Discretion)
- Cấu trúc chi tiết hàm helper `md_table` / `md_escape` trong `src/telegram.py`.
- Cập nhật `tests/conftest.py` (`fake_fetch` nhận `sendRichMessage`, `sent_texts` trích xuất cả `text` lẫn `rich_message.markdown`) và cập nhật các assertion chuỗi giao diện trong bộ test hiện có + bổ sung test mới cho Markdown table, chọn STT/từ không mất bảng, song song callback và cache lookup.
- Cập nhật `docs/exp.md` và `docs/usecase.md` sau khi hoàn tất và chạy xanh toàn bộ test.
