# LanguageLearning — content generation

Produces the **language packs** read by the [LanguageLearning](https://github.com/Namularbre/LanguageLearning) Android app: graded texts, their words and the "How the language works" lessons, one JSON file per language (`packs/ro-RO.json`, `en-GB.json`, `fr-FR.json`). The format is described in the app's `docs/understanding/content-packs.md`.

The app never writes content and never guesses the base form of a word: this project does it, once, and a review step checks it before publication.

## The pipeline

```
python -m pipeline draft   →  drafts/<id>.json + drafts/<id>.md   (AI text, annotated, with what to check)
        review             →  edit the draft, set "status": "approved"
python -m pipeline publish →  packs/<lang>.json, version + 1     (refused if the checks fail)
copy packs/*.json          →  app: core/data/src/main/assets/packs/   (M2: upload to the content API)
```

1. **Writing** (`llm.py`, Gemini): a text at the requested CEFR level and topic, reusing the words the pack already has, with the translation of every sentence into the other UI languages.
2. **Cutting** (`tokenizer.py`): the same rules as the app's `Tokenizer` (French elisions are two words, a hyphen separates words). A test checks it cuts every published sentence like the app.
3. **Base forms, two opinions** (`analysis.py` + `llm.py`): **Stanza** (a Stanford NLP library trained on annotated corpora) and **Gemini** each give the base form of every word. When they agree, the word is linked to it, with a grammar note from Stanza's features (`notes.py`: a fixed table, so the same form always gets the same note). When they disagree, Stanza's answer is kept and the word is **flagged** for the reviewer.
4. **New words** (`llm.py`): words the pack does not know yet get a dictionary entry (meanings, gender).
5. **AI proofreading** (`llm.py`): a second Gemini call, as a strict proofreader, lists grammar, naturalness, level and translation problems. It only reports; it does not rewrite.
6. **Review** (a person): reads `drafts/<id>.md` (text, translations, flagged words, AI remarks, new words), fixes `drafts/<id>.json` if needed, sets `"status": "approved"`, and `"reviewedBy": "human"` only if they are fluent in the language.
7. **Publishing** (`drafts.py`, `packs.py`): the text and its new words are added to the pack, the version is raised, and the pack goes through the same checks as the app's `PackContentTest`. Nothing is saved if a check fails.

### Who reviews what

No native Romanian speaker is available yet. Every text and lesson therefore carries `"review": "ai"` (checked by the two AI opinions, the AI proofreader and the automatic checks) or `"review": "human"` (read by a fluent person). French content can be reviewed by the author; Romanian content stays `"ai"` until a native speaker (tutor, student) reads it, and the field says exactly what is left. The app ignores this field for now.

## Commands

```bash
python -m unittest discover -s tests -t .     # tests: no dependency, no network
python -m pipeline check                      # check every pack (as the app's PackContentTest)
python -m pipeline format                     # rewrite packs in the stable layout (one-line diffs)

# Writing drafts needs the dependencies and a Gemini API key:
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt               # Stanza pulls PyTorch: about 500 MB to 1 GB
export GEMINI_API_KEY=...                     # https://aistudio.google.com/apikey (never commit it)
python -m pipeline draft --language ro-RO --id ro-bakery --level A1 --kind STORY --topic "buying bread at the bakery"
python -m pipeline publish drafts/ro-bakery.json
```

The first `draft` for a language downloads its Stanza model (a few hundred MB). The Gemini model is `gemini-flash-latest` by default; set `GEMINI_MODEL` to pin another one.

## Files

| File | Role |
|---|---|
| `pipeline/tokenizer.py` | Cutting sentences into words, like the app |
| `pipeline/analysis.py` | Stanza: base form, part of speech, features of each word |
| `pipeline/llm.py` | Every Gemini prompt (writing, base forms, dictionary entries, proofreading), and `FakeLlm` for tests |
| `pipeline/notes.py` | Grammar notes from Stanza's features, in English, French and Romanian |
| `pipeline/drafts.py` | Building a draft, the review sheet, publishing into a pack |
| `pipeline/packs.py` | Reading, checking, formatting packs |
| `pipeline/__main__.py` | Command line |
| `packs/` | Published packs (the source of truth for the app's bundled packs) |
| `drafts/` | Drafts waiting for review |

## Choices and limits

- **Two opinions on base forms rather than one**: Stanza is reliable on common forms but trips on ambiguous ones; the AI knows context but invents forms. Their disagreement is a cheap signal of where a person must look.
- **Grammar notes from a table rather than from the AI**: identical forms get identical notes, and the table is reviewed once.
- **New words are ranked after the known ones** (`frequencyRank`): the level test orders words by this rank, so an approximate order is acceptable; a frequency list could replace it later.
- **Lessons** are still written by hand in the packs; only texts are generated for now.
