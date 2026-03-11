import sys
from unittest.mock import MagicMock, patch

import pytest

from bot.utils.anonymize import anonymize_text


def test_anonymize_empty():
    assert anonymize_text("") == ""
    assert anonymize_text("   ") == "   "


def test_anonymize_mention():
    result = anonymize_text("Hey <@123456> what's up")
    assert "<@123456>" not in result
    assert "Hey" in result
    assert "what's" in result


def test_anonymize_my_name_is():
    result = anonymize_text("My name is John and I like it")
    assert "John" not in result
    assert "My name is" in result
    assert "and I like it" in result


def test_anonymize_called():
    result = anonymize_text("I'm called Alice")
    assert "Alice" not in result
    assert "called" in result


def test_anonymize_skip_words():
    result = anonymize_text("my name is a")
    assert "my name is a" in result


def test_anonymize_short_name_skipped():
    with patch("bot.utils.anonymize._get_nlp", return_value=None):
        result = anonymize_text("my name is x")
    assert "my name is x" in result


def test_anonymize_regex_named_reuses_map():
    with patch("bot.utils.anonymize._get_nlp", return_value=None):
        result = anonymize_text("my name is Bob and I'm called Bob")
    assert "Bob" not in result
    parts = result.split()
    assert parts[3] == parts[7]


def test_anonymize_mention_reused_same_map():
    with patch("bot.utils.anonymize._get_nlp", return_value=None):
        result = anonymize_text("<@123> said hi to <@123>")
    assert "<@123>" not in result
    parts = result.split()
    assert parts[0] == parts[4]


def test_anonymize_ner_skips_non_person():
    mock_ent_org = type(
        "Ent", (), {"label_": "ORG", "text": "Acme", "start_char": 0, "end_char": 4}
    )()
    mock_ent_person = type(
        "Ent", (), {"label_": "PERSON", "text": "Bob", "start_char": 13, "end_char": 16}
    )()
    mock_doc = type("Doc", (), {"ents": [mock_ent_org, mock_ent_person]})()
    mock_nlp = lambda t: mock_doc
    with patch("bot.utils.anonymize._get_nlp", return_value=mock_nlp):
        result = anonymize_text("Acme Corp and Bob")
    assert "Acme" in result
    assert "Bob" not in result


def test_anonymize_ner_skips_short_or_our_names():
    mock_ent = type("Ent", (), {"label_": "PERSON", "text": "A", "start_char": 0, "end_char": 1})()
    mock_doc = type("Doc", (), {"ents": [mock_ent]})()
    mock_nlp = lambda t: mock_doc
    with patch("bot.utils.anonymize._get_nlp", return_value=mock_nlp):
        result = anonymize_text("A said")
    assert "A" in result


def test_anonymize_ner_reuses_name_map():
    mock_ent1 = type(
        "Ent", (), {"label_": "PERSON", "text": "Bob", "start_char": 0, "end_char": 3}
    )()
    mock_ent2 = type(
        "Ent", (), {"label_": "PERSON", "text": "Bob", "start_char": 9, "end_char": 12}
    )()
    mock_doc = type("Doc", (), {"ents": [mock_ent1, mock_ent2]})()
    mock_nlp = lambda t: mock_doc
    with patch("bot.utils.anonymize._get_nlp", return_value=mock_nlp):
        result = anonymize_text("Bob said Bob")
    assert "Bob" not in result
    replaced = result.split()
    assert len(replaced) == 3 and replaced[0] == replaced[2]


def test_anonymize_no_changes():
    result = anonymize_text("Hello world, no names here")
    assert "Hello" in result
    assert "world" in result


def test_anonymize_exhausts_random_names_reuses():
    names = " ".join(f"My name is Name{i}" for i in range(20))
    with patch("bot.utils.anonymize._get_nlp", return_value=None):
        result = anonymize_text(names)
    for i in range(20):
        assert f"Name{i}" not in result


def test_anonymize_ner_detects_person():
    mock_ent = type(
        "Ent", (), {"label_": "PERSON", "text": "Bob", "start_char": 0, "end_char": 3}
    )()
    mock_doc = type("Doc", (), {"ents": [mock_ent]})()
    mock_nlp = lambda t: mock_doc

    with patch("bot.utils.anonymize._get_nlp", return_value=mock_nlp):
        result = anonymize_text("Bob said hello")
    assert "Bob" not in result
    assert "said hello" in result


def test_anonymize_regex_fallback_when_nlp_none():
    with patch("bot.utils.anonymize._get_nlp", return_value=None):
        result = anonymize_text("My name is Bob and I'm called Alice")
    assert "Bob" not in result
    assert "Alice" not in result
    assert "My name is" in result
    assert "called" in result


def test_anonymize_get_nlp_oserror_fallback():
    import bot.utils.anonymize as mod

    mod._nlp = None
    fake_spacy = MagicMock()
    fake_spacy.load.side_effect = OSError("model not found")
    with patch.dict(sys.modules, {"spacy": fake_spacy}):
        assert mod._get_nlp() is None


def test_anonymize_get_nlp_generic_exception_fallback():
    import bot.utils.anonymize as mod

    mod._nlp = None
    fake_spacy = MagicMock()
    fake_spacy.load.side_effect = RuntimeError("other")
    with patch.dict(sys.modules, {"spacy": fake_spacy}):
        assert mod._get_nlp() is None
