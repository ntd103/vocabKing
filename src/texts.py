"""English copy for Telegram screens."""

MENU = "👋 <b>Vocabking</b>"
HINT_ROOT = "Open /menu to choose an action."
HELP = (
    "❓ <b>Help</b>\n\n"
    "<b>Review shortcuts</b>\n"
    "Type the missing English word or reply to the quiz.\n"
    "<code>?</code> — reveal more letters\n"
    "<code>???</code> — show the answer and rate it Again\n"
    "After answering: <code>1</code> Again · <code>2</code> Hard · "
    "<code>3</code> Good · <code>4</code> Easy\n\n"
    "<b>Commands</b>\n/menu — main menu\n/study — review due words\n"
    "/add — add a word (auto EN definition) · "
    "<code>/add word|IPA|EN|VI|example|note</code> bulk\n"
    "/vocab — browse vocabulary\n/edit — edit a word\n"
    "/delete — delete a word\n/import — import vocabulary\n/export — export vocabulary\n"
    "/games — games\n/settings — settings\n/cancel — cancel the current action"
)

ADD_ASK_WORD = "➕ Enter the English word to add:"
ADD_ASK_EN = "Use this English definition?\n<code>1</code> = yes · <code>2</code> = manual"
ADD_ASK_INPUT = (
    "Enter one word per line:\n"
    "<code>word|IPA|English definition|Vietnamese meaning|example|note</code>"
)
ADD_DICT_MISS = (
    'No dictionary entry for “{word}”. Fill the format manually.'
)
ADD_BUSY = "Still adding a word — finish the format or /cancel."
ADD_CONFIRMED = "✅ Added: {n} · Today: {today}/{target}"
ADD_CANCELLED = "Cancelled. No words added."
ADD_EMPTY = "Check the word, English definition and Vietnamese meaning, then try again."
EDIT_PICKED = "✏️ **Edit vocabulary** ({total})"
EDIT_FIELD_ASK = "✏️ Enter a new {field} for <b>{word}</b>:"
EDIT_SAVED = "✅ Updated {field}: {value}"
DELETE_PICKED = "🗑 **Delete vocabulary** ({total})"
DELETE_DONE = '✅ Deleted “{}” and its review history.'

SETTINGS_MENU = "⚙️ <b>Settings</b>"
SETTINGS_MODE = "🔀 <b>Review mode</b>: {current}"
SETTINGS_QUIET = "🌙 <b>Quiet hours</b>: {current}"
SETTINGS_REMINDER = "🔔 <b>Reminder mode</b>: {current}"
SETTINGS_TARGET = "🎯 <b>Daily target</b>: {current}\nEnter a new target (words added + reviews):"
QUIET_START_ASK = "🌙 <b>Quiet hours</b>: {current}\nEnter the start hour (0–23):"
QUIET_END_ASK = "Enter the end hour (0–23):"
QUIET_START_INVALID = "Enter a start hour from 0 to 23:"
QUIET_END_INVALID = "Enter an end hour from 0 to 23:"
TARGET_INVALID = "Enter a positive whole number:"

STUDY_NONE_DUE = "No words due. Reviews today: {done}/{target}."
STUDY_QUOTA_DONE = "Daily target reached ({target})."
RATED_FEEDBACK = "🔖 <b>{word}</b> · {rating}\n⏰ Next review: {interval}\n📊 Today: {done}/{target}"
RATE_NAMES = {"again": "Again", "hard": "Hard", "good": "Good", "easy": "Easy"}

VOCAB_HEADER = "📚 <b>Vocabulary</b> ({total})"
VOCAB_VIEW_TITLE = "📚 **Vocabulary** ({total})"
VOCAB_FOOTER = "\n\nPage {page}/{pages} · Enter a row number or word to {verb}."
VOCAB_EMPTY = "No vocabulary yet. Use /add to add a word."
VOCAB_SEARCH_ASK = "🔎 Enter a word, Vietnamese meaning or row number:"
VOCAB_NOT_FOUND = 'No match for “{}”. Try another word or row number.'
VOCAB_DETAIL = ("📖 <b>#{stt} · {word}</b>\n{phonetic}\n🏷 {pos}\n"
                "🇬🇧 {define_en}\n🇻🇳 {meaning}\n📝 {example}\nℹ️ {note}\n⏰ {due}")
IDLE_TIMEOUT = "⏱ Timed out. Open /menu to continue."

IMPORT_EXPORT_MENU = "📤 <b>Import / Export</b>"
IMPORT_ASK = "Reply to this message with a CSV or JSON file, or paste the contents."
IMPORT_INVALID = "Invalid import. No words saved."
IMPORT_CONFIRM = "Import {count} words?"
IMPORT_CANCELLED = "Import cancelled. No words saved."
IMPORT_DONE = "✅ Imported: {count}"
EXPORT_EMPTY = "No words to export."
EXPORT_DONE = "Exported: {count}"
EXPORT_RECORD_TOO_LARGE = "The export is too large. No data was truncated."

GAMES_MENU = "🎮 <b>Games</b>"
STORY_ASK_COUNT = "Enter the number of random words:"
STORY_INVALID_COUNT = "Enter a whole number from 1 to 20:"
STORY_EMPTY = "No words yet. Add some with /add."
STORY_WORDS = "✍️ **Story challenge ({n})**\n\n{words}\n\nWrite a short story using every word."
