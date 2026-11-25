# Vocabking — user guide (shortcuts & menus)

English UI. Leading icons on buttons; Telegram does not support left-align flags for inline keyboards.

## Main menu

| Button | Action |
|--------|--------|
| Review | Start `/study` (due cards) |
| Add words | Ask for word → offer EN definition → fill pipe format |
| Vocabulary | Browse table (10 rows/page) |
| Games | Story challenge |
| Settings | Daily target, quiet hours |
| Help | This shortcut summary |
| Import / Export | File or paste CSV/JSON |

## Vocabulary

- Opens the table directly (no separate View hub). **Add** is only on the main menu.
- Footer: Previous / Next, Search, **Edit**, **Delete**, Menu.
- Type a **row number** or exact **word** to open details / act. Wrong input keeps the page.
- Delete mode can **Delete all** (with confirmation).

## Review shortcuts

| Input | Effect |
|-------|--------|
| English word | Check correct / incorrect, then rate |
| `?` | Reveal more letters (first letter always shown) |
| `???` | Full answer + auto **Again** once |
| `1` / `2` / `3` / `4` | Again / Hard / Good / Easy |

Rating buttons show the next interval, e.g. `Again (1m)`.

## Dialogs

- Waiting for input times out after **15 seconds** of inactivity (`Timed out`), except **add** (no idle timeout so the format prompt stays visible).
- Automatic review reminders do **not** share that timeout — they wait until you answer.
- Reminders are deferred while any menu/dialog FSM is open; finish or return to Menu first.
- While adding, other commands are ignored (`/cancel` or finish to leave).

## Add shortcuts

| Input | Effect |
|-------|--------|
| `/add` or Menu → Add | Ask for the English word |
| `/add word` | Look up EN definition → Use (1) / Manual (2) → pipe template |
| `/add word\|IPA\|EN\|VI\|…` | Bulk preview (skip dictionary) |
| `1` / `2` on EN prompt | Accept EN definition / fill manually |

## Add / import rules (for operators)

Required: word, English definition, Vietnamese meaning. Optional: IPA, example, note, POS. New cards are seeded at FSRS **Hard** before the first recall.
