"""Real example sentences from Tatoeba (https://tatoeba.org) for the words of a pack.

Tatoeba sentences are written and translated by people, under CC BY 2.0 FR: they can be reused
with credit (each example keeps its sentence id and author). Some have a recording, whose licence
is chosen by the person who recorded it: only recordings with a licence are kept.

An example is kept for a word when the sentence uses a form of that word the pack already knows,
is short, and has almost only known words: the learner can read it. Words are linked to their base
form through the forms seen in the pack's texts; a form seen with two base forms is not used.
"""

import bz2
import csv
import tarfile
import urllib.error
import urllib.request
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from . import packs, tokenizer

LICENSE = "CC BY 2.0 FR"
EXPORTS = "https://downloads.tatoeba.org/exports"
# Tatoeba uses ISO 639-3 codes.
TATOEBA_CODES = {"ro": "ron", "en": "eng", "fr": "fra"}
CEDILLA_FIXES = str.maketrans({"ş": "ș", "Ş": "Ș", "ţ": "ț", "Ţ": "Ț"})


@dataclass(frozen=True)
class TatoebaSentence:
    id: int
    language: str  # "ro", "en", "fr"
    text: str
    author: str


@dataclass
class Corpus:
    """What the selection needs from Tatoeba, already filtered to the useful languages."""
    sentences: dict[int, TatoebaSentence] = field(default_factory=dict)
    links: dict[int, set[int]] = field(default_factory=lambda: defaultdict(set))  # sentence -> translations
    audio: dict[int, dict] = field(default_factory=dict)  # sentence -> {"url", "author", "license"}


# ---------------------------------------------------------------- selection (pure, tested)

def known_forms(pack: dict) -> dict[str, tuple[str, dict | None]]:
    """Written form (lower case) -> (lemma id, grammar note), from the words of the pack's texts.
    A form found with two different lemmas is ambiguous and left out."""
    seen: dict[str, set] = defaultdict(set)
    notes: dict[tuple[str, str], dict | None] = {}
    for text in pack["texts"]:
        for sentence in text["sentences"]:
            for token in sentence["tokens"]:
                if "lemma" in token:
                    form = token["text"].lower()
                    seen[form].add(token["lemma"])
                    notes.setdefault((form, token["lemma"]), token.get("formNote"))
    return {form: (next(iter(ids)), notes[(form, next(iter(ids)))]) for form, ids in seen.items() if len(ids) == 1}


def known_names(pack: dict) -> set[str]:
    """Proper names the pack's texts use (words written without a lemma): readable, not unknown."""
    return {token["text"] for text in pack["texts"] for sentence in text["sentences"] for token in sentence["tokens"]
            if "lemma" not in token and any(char.isalpha() for char in token["text"])}


def select_examples(pack: dict, corpus: Corpus, per_word: int = 3, max_words: int = 10,
                    max_unknown: int = 1) -> dict[str, list[dict]]:
    """Lemma id -> examples, the shortest sentences first."""
    language = packs.language_of(pack)
    others = sorted(packs.UI_LANGUAGES - {language})
    forms = known_forms(pack)
    names = known_names(pack)
    candidates: dict[str, list[tuple[int, dict]]] = defaultdict(list)

    for sentence in corpus.sentences.values():
        if sentence.language != language:
            continue
        text = sentence.text.translate(CEDILLA_FIXES) if language == "ro" else sentence.text
        pieces = tokenizer.split(text)
        words = [p for p in pieces if p.is_word]
        unknown = [w for w in words if w.text.lower() not in forms and w.text not in names]
        if not words or len(words) > max_words or len(unknown) > max_unknown:
            continue
        translation = {}
        for other_id in sorted(corpus.links.get(sentence.id, ())):
            other = corpus.sentences.get(other_id)
            if other and other.language in others and other.language not in translation:
                translation[other.language] = other.text
        if not translation:
            continue
        tokens = []
        for piece in pieces:
            token = {"text": piece.text}
            if piece.is_word and piece.text.lower() in forms:
                lemma_id, note = forms[piece.text.lower()]
                token["lemma"] = lemma_id
                if note:
                    token["formNote"] = note
            tokens.append(token)
        example = {"tokens": tokens, "translation": dict(sorted(translation.items())),
                   "source": {"tatoeba": sentence.id, "author": sentence.author, "license": LICENSE}}
        if sentence.id in corpus.audio:
            example["audio"] = corpus.audio[sentence.id]
        # Sentences translated into every other UI language first, then the shortest.
        rank = (len(others) - len(translation), len(words), sentence.id)
        for lemma_id in {t["lemma"] for t in tokens if "lemma" in t}:
            candidates[lemma_id].append((rank, example))

    return {lemma_id: [example for _, example in sorted(found, key=lambda c: c[0])[:per_word]]
            for lemma_id, found in candidates.items()}


def apply_examples(pack: dict, examples: dict[str, list[dict]]) -> int:
    """Sets the examples of every lemma (replacing older ones) and raises the pack version when
    something changed. Returns the number of lemmas that have examples."""
    changed = False
    for lemma in pack["lemmas"]:
        new = examples.get(lemma["id"], [])
        if lemma.get("examples", []) != new:
            changed = True
            if new:
                lemma["examples"] = new
            else:
                lemma.pop("examples", None)
    if changed:
        pack["version"] += 1
    return sum(1 for lemma in pack["lemmas"] if lemma.get("examples"))


# ---------------------------------------------------------------- download (network)

def _download(url: str, cache: Path) -> Path:
    path = cache / url.rsplit("/", 1)[1]
    if not path.exists():
        print(f"Downloading {url} …")
        cache.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".part")
        urllib.request.urlretrieve(url, tmp)
        tmp.rename(path)
    return path


def _rows(path: Path):
    """Tab-separated rows of a Tatoeba export, whether .tsv.bz2 or .tar.bz2 (one file inside)."""
    if path.name.endswith(".tar.bz2"):
        with tarfile.open(path, "r|bz2") as archive:
            for member in archive:
                if member.isfile():
                    lines = (line.decode("utf-8") for line in archive.extractfile(member))
                    yield from csv.reader(lines, delimiter="\t", quoting=csv.QUOTE_NONE)
    else:
        with bz2.open(path, "rt", encoding="utf-8") as file:
            yield from csv.reader(file, delimiter="\t", quoting=csv.QUOTE_NONE)


def load_corpus(languages: list[str], cache: Path) -> Corpus:
    """Downloads (once, into `cache`) and reads the exports for these UI languages."""
    corpus = Corpus()
    by_code = {TATOEBA_CODES[l]: l for l in languages}
    try:  # one small file per language…
        files = [_download(f"{EXPORTS}/per_language/{code}/{code}_sentences_detailed.tsv.bz2", cache / code)
                 for code in by_code]
    except urllib.error.HTTPError:  # …or, if Tatoeba renamed them, the export of every language
        files = [_download(f"{EXPORTS}/sentences_detailed.tar.bz2", cache)]
    for path in files:
        # Columns: sentence id, language, text, username, date added, date last modified.
        for row in _rows(path):
            if len(row) >= 4 and row[1] in by_code:
                corpus.sentences[int(row[0])] = TatoebaSentence(int(row[0]), by_code[row[1]], row[2], row[3])

    # Columns: sentence id, translation id (both directions are listed).
    for row in _rows(_download(f"{EXPORTS}/links.tar.bz2", cache)):
        if len(row) < 2:
            continue
        source, target = int(row[0]), int(row[1])
        if source in corpus.sentences and target in corpus.sentences:
            corpus.links[source].add(target)

    # Columns: sentence id, audio id, username, licence, attribution URL. No licence: not reusable.
    for row in _rows(_download(f"{EXPORTS}/sentences_with_audio.tar.bz2", cache)):
        sentence_id = int(row[0])
        if sentence_id in corpus.sentences and len(row) >= 4 and row[3] and sentence_id not in corpus.audio:
            corpus.audio[sentence_id] = {"url": f"https://tatoeba.org/audio/download/{row[1]}",
                                         "author": row[2], "license": row[3]}
    return corpus
