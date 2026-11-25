"""Dictionary lookup via freedictionaryapi.com (free, no key).

Returns a normalized dict or None on miss. Network errors are swallowed into
None so the caller can show a friendly "not found" instead of a crash.
"""

from collections import OrderedDict
from urllib.parse import quote

from workers import fetch

API = "https://freedictionaryapi.com/api/v1/entries/en/{word}"
CACHE_MAX = 128
_CACHE: OrderedDict[str, dict] = OrderedDict()
_CACHE_FETCH = None


def clear_cache() -> None:
    _CACHE.clear()


async def lookup(word: str) -> dict | None:
    """Fetch word info. Returns {word, phonetic, pos, definition, example}."""
    global _CACHE_FETCH
    if _CACHE_FETCH is not fetch:
        _CACHE.clear()
        _CACHE_FETCH = fetch
    key = (word or "").strip().casefold()
    if key in _CACHE:
        _CACHE.move_to_end(key)
        return {**_CACHE[key], "word": word}
    try:
        res = await fetch(API.format(word=quote((word or "").strip(), safe="")))
        if res.status != 200:
            return None
        data = await res.json()
    except Exception:
        return None

    if not isinstance(data, dict):
        return None

    # Only explicitly US-tagged IPA; never substitute UK/unknown dialects.
    phonetic = ""

    pos = ""
    definition = ""
    example = ""
    entries = data.get("entries") or data.get("meanings") or []
    for e in entries:
        if not isinstance(e, dict):
            continue
        if e.get("language", {}).get("code", "en") != "en":
            continue
        pos = pos or e.get("partOfSpeech", "")
        for p in e.get("pronunciations") or []:
            if not isinstance(p, dict):
                continue
            tags = {str(tag).casefold() for tag in p.get("tags", [])}
            text = p.get("text", "").strip()
            if (p.get("type") == "ipa" and text
                    and tags & {"general american", "us", "united states", "american english"}
                    and not text.strip('/[]').startswith('-')
                    and not text.strip('/[]').endswith('-')):
                phonetic = text
                break
        senses = e.get("senses") or []
        for s in senses:
            if isinstance(s, dict):
                definition = definition or s.get("definition", "") or s.get("gloss", "")
                exs = s.get("examples") or []
                if exs and not example:
                    example = exs[0] if isinstance(exs[0], str) else exs[0].get("text", "")
        if definition:
            break

    if not definition:
        return None
    result = {
        "word": word,
        "phonetic": phonetic,
        "pos": pos,
        "definition": definition,
        "example": example,
    }
    if key:
        _CACHE[key] = dict(result)
        if len(_CACHE) > CACHE_MAX:
            _CACHE.popitem(last=False)
    return dict(result)
