"""Calls to Gemini (https://ai.google.dev/gemini-api/docs) with structured JSON answers.

Every prompt is here, so they are versioned with the code. `FakeLlm` answers the same questions
without the network, for the tests.
"""

import json
import os

DEFAULT_MODEL = "gemini-flash-latest"  # alias of the current Flash model; override with GEMINI_MODEL

LANGUAGE_NAMES = {"ro": "Romanian", "en": "English", "fr": "French"}

# How base forms are written in the packs, so the AI writes them the same way.
LEMMA_CONVENTIONS = {
    "ro": 'verbs with "a" (a merge, a fi), nouns in the singular without article (casă), adjectives masculine singular',
    "fr": "verbs in the infinitive (aller), nouns in the singular, adjectives masculine singular",
    "en": "verbs without \"to\" (go, be), nouns in the singular",
}


def _others(language: str) -> list[str]:
    return [code for code in ("en", "fr", "ro") if code != language]


class GeminiLlm:
    def __init__(self, model: str | None = None):
        from google import genai  # reads the key from GEMINI_API_KEY

        self._client = genai.Client()
        self._model = model or os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)

    def _ask(self, prompt: str) -> dict:
        response = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config={"response_mime_type": "application/json", "temperature": 0.7},
        )
        return json.loads(response.text)

    def write_text(self, language: str, level: str, kind: str, topic: str, sentences: int, known_words: list[str]) -> dict:
        others = _others(language)
        return self._ask(f"""
You write graded reading texts for learners of {LANGUAGE_NAMES[language]}.
Write a {kind.lower()} of {sentences} sentences at CEFR level {level} about: {topic}.
- Natural, correct {LANGUAGE_NAMES[language]}, as a native speaker would write it for a learner at {level}.
- Prefer these words the learner already met: {", ".join(known_words[:300])}.
- At most about 10% new words. Short sentences at A1/A2. No names of real people.
- {"Romanian: write ș and ț with a comma below (U+0219, U+021B), never a cedilla." if language == "ro" else ""}
Translate every sentence into {", ".join(LANGUAGE_NAMES[c] for c in others)}: faithful, natural translations.
Answer with JSON only:
{{"title": "...", "minutes": <reading time in minutes, 1 to 5>,
  "sentences": [{{"text": "...", "translation": {{{", ".join(f'"{c}": "..."' for c in others)}}}}}]}}
""")

    def lemmatise(self, language: str, sentences: list[list[str]]) -> list[list[dict]]:
        numbered = "\n".join(f"{i}: {json.dumps(words, ensure_ascii=False)}" for i, words in enumerate(sentences))
        answer = self._ask(f"""
For each word of these {LANGUAGE_NAMES[language]} sentences (already cut into words), give its base form
(dictionary form) and its part of speech, in context.
Base forms: {LEMMA_CONVENTIONS[language]}. A proper name gets "PROPER_NAME" as part of speech.
Parts of speech: NOUN, VERB, ADJECTIVE, ADVERB, PRONOUN, PREPOSITION, CONJUNCTION, ARTICLE, NUMERAL, INTERJECTION, PROPER_NAME.
Sentences (index: words):
{numbered}
Answer with JSON only, one list per sentence, one entry per word, same order:
{{"sentences": [[{{"word": "...", "lemma": "...", "partOfSpeech": "..."}}]]}}
""")
        return answer["sentences"]

    def describe_lemmas(self, language: str, lemmas: list[dict]) -> list[dict]:
        others = _others(language)
        listed = "\n".join(f"- {l['text']} ({l['partOfSpeech']}), seen in: {l['example']}" for l in lemmas)
        answer = self._ask(f"""
Dictionary entries for a learner of {LANGUAGE_NAMES[language]}. For each base form below, give its main meaning
in {", ".join(LANGUAGE_NAMES[c] for c in others)} (one to three words, the meaning used in the example),
its grammatical gender if it is a noun (MASCULINE, FEMININE or NEUTER, else null).
{listed}
Answer with JSON only, same order:
{{"lemmas": [{{"text": "...", "gender": null, "meaning": {{{", ".join(f'"{c}": "..."' for c in others)}}}}}]}}
""")
        return answer["lemmas"]

    def review(self, language: str, level: str, text: dict) -> list[dict]:
        answer = self._ask(f"""
You are a strict proofreader, native speaker of {LANGUAGE_NAMES[language]}, and also fluent in English, French and
Romanian. Check this text meant for learners at CEFR level {level}, and its translations.
Report only real problems: grammar or agreement errors, unnatural phrasing, wrong diacritics, words far above the
level, wrong or unfaithful translations. Do not rewrite what is correct.
{json.dumps(text, ensure_ascii=False, indent=1)}
Answer with JSON only (empty list if everything is correct):
{{"issues": [{{"sentence": <index from 0>, "where": "text" or "translation:<code>", "problem": "...", "suggestion": "..."}}]}}
""")
        return answer["issues"]


class FakeLlm:
    """Deterministic answers for the tests: a tiny Romanian text and a dictionary of base forms."""

    def __init__(self, text: dict, lemmas: dict[str, tuple[str, str]], issues: list[dict] | None = None):
        self._text = text
        self._lemmas = lemmas  # word (lower case) -> (base form, part of speech)
        self._issues = issues or []

    def write_text(self, language, level, kind, topic, sentences, known_words):
        return self._text

    def lemmatise(self, language, sentences):
        return [
            [{"word": w, "lemma": self._lemmas.get(w.lower(), (w, "NOUN"))[0],
              "partOfSpeech": self._lemmas.get(w.lower(), (w, "NOUN"))[1]} for w in words]
            for words in sentences
        ]

    def describe_lemmas(self, language, lemmas):
        return [{"text": l["text"], "gender": None, "meaning": {c: f"<{l['text']}>" for c in _others(language)}} for l in lemmas]

    def review(self, language, level, text):
        return self._issues
