"""Dictionary IPA must be explicitly US-tagged, never guessed from order."""
import asyncio
from types import SimpleNamespace

import pytest

from tests.conftest import _install_workers_stub
_install_workers_stub()
from services import dict_service


@pytest.mark.parametrize('pronunciations,expected', [
    ([{'type':'ipa','text':'/UK/','tags':['UK']},
      {'type':'ipa','text':'/US/','tags':['General American']}], '/US/'),
    ([{'type':'ipa','text':'/US/','tags':['US']}], '/US/'),
    ([{'type':'ipa','text':'/US/','tags':['United States']}], '/US/'),
    ([{'type':'ipa','text':'/unknown/','tags':[]}], ''),
    ([{'type':'ipa','text':'/UK/','tags':['Received Pronunciation']}], ''),
    ([{'type':'enpr','text':'not IPA','tags':['General American']}], ''),
    ([{'type':'ipa','text':'/hə-/','tags':['General American']},
      {'type':'ipa','text':'/hɛˈloʊ/','tags':['General American']}], '/hɛˈloʊ/'),
])
def test_lookup_selects_explicit_complete_us_ipa(monkeypatch, pronunciations, expected):
    async def json_body():
        return {'entries':[{'language':{'code':'en'},'partOfSpeech':'noun',
                'pronunciations':pronunciations,
                'senses':[{'definition':'greeting','examples':['hello Bob']}]}]}
    async def fetch(url):
        return SimpleNamespace(status=200,json=json_body)
    monkeypatch.setattr(dict_service, 'fetch', fetch)
    info = asyncio.run(dict_service.lookup('hello'))
    assert info['phonetic'] == expected
    assert info['definition'] == 'greeting'


def test_lookup_caches_hits_and_returns_isolated_copy(monkeypatch):
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


def test_lookup_url_encodes_spaces_and_hash(monkeypatch):
    dict_service.clear_cache()
    urls = []

    async def fake_fetch(url):
        urls.append(url)
        return SimpleNamespace(status=404, json=lambda: None)

    monkeypatch.setattr(dict_service, "fetch", fake_fetch)
    asyncio.run(dict_service.lookup("make up"))
    asyncio.run(dict_service.lookup("c#"))
    assert urls[0].endswith("/make%20up")
    assert urls[1].endswith("/c%23")


