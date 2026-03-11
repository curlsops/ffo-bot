"""Anonymization for anonymous posts using spaCy NER for person detection."""

import logging
import random
import re

logger = logging.getLogger(__name__)

RANDOM_NAMES = (
    "Alex",
    "Blake",
    "Casey",
    "Drew",
    "Emery",
    "Finley",
    "Jordan",
    "Morgan",
    "Quinn",
    "Riley",
    "Sam",
    "Taylor",
    "Avery",
    "Cameron",
    "Jamie",
    "Parker",
)

_nlp = None


def _get_nlp():
    global _nlp
    if _nlp is None:
        try:
            import spacy

            _nlp = spacy.load("en_core_web_sm")
        except OSError as e:
            logger.warning(
                "spaCy model en_core_web_sm not found: %s. Run: python -m spacy download en_core_web_sm",
                e,
            )
            _nlp = False
        except Exception as e:
            logger.warning("spaCy unavailable (%s), using regex fallback", e)
            _nlp = False
    return _nlp if _nlp else None


def anonymize_text(text: str) -> str:
    """Replace Discord mentions and NER-detected person names with random names."""
    if not text or not text.strip():
        return text

    used_names: set[str] = set()
    name_map: dict[str, str] = {}

    def _random_name() -> str:
        candidates = [n for n in RANDOM_NAMES if n not in used_names]
        if not candidates:
            candidates = list(RANDOM_NAMES)
        name = random.choice(candidates)
        used_names.add(name)
        return name

    def _replace_mention(m: re.Match[str]) -> str:
        original = m.group(0)
        if original not in name_map:
            name_map[original] = _random_name()
        return name_map[original]

    SKIP_WORDS = {"i", "a", "the", "is", "it", "my", "me", "you", "we", "they", "called", "named"}

    def _replace_named(m: re.Match[str]) -> str:
        prefix, name = m.group(1), m.group(2)
        if len(name) < 2 or name.lower() in SKIP_WORDS:
            return m.group(0)
        key = name.lower()
        if key not in name_map:
            name_map[key] = _random_name()
        return f"{prefix}{name_map[key]}"

    result = re.sub(r"<@!?\d+>", _replace_mention, text)

    our_names = {n.lower() for n in RANDOM_NAMES}
    nlp = _get_nlp()
    if nlp:
        doc = nlp(result)
        replacements = []
        for ent in doc.ents:
            if ent.label_ == "PERSON":
                original = ent.text.strip()
                if len(original) >= 2 and original.lower() not in our_names:
                    key = original.lower()
                    if key not in name_map:
                        name_map[key] = _random_name()
                    replacements.append((ent.start_char, ent.end_char, name_map[key]))

        for start, end, replacement in sorted(replacements, key=lambda r: r[0], reverse=True):
            result = result[:start] + replacement + result[end:]
    else:
        result = re.sub(
            r"(\b(?:called|named)\s+)(\w+)\b",
            _replace_named,
            result,
            flags=re.IGNORECASE,
        )
        result = re.sub(
            r"(\b(?:my name is|i'm|i am|that's|that is)\s+)(\w+)\b",
            _replace_named,
            result,
            flags=re.IGNORECASE,
        )

    return result
