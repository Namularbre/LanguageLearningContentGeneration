"""Reading, checking, writing and updating language packs (format 1, read by the app's
`ContentPackParser`). A pack is a plain dict, exactly as found in the JSON file."""

import json
from pathlib import Path

FORMAT = 1
UI_LANGUAGES = {"en", "fr", "ro"}
CEDILLAS = set("şŞţŢ")
WIDTH = 110  # a JSON object or array that fits in this many characters stays on one line


def load(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def dumps(value, level: int = 0) -> str:
    """Readable, stable JSON: short objects on one line, so a change is a one-line diff."""
    compact = json.dumps(value, ensure_ascii=False, separators=(", ", ": "))
    if len("  " * level) + len(compact) <= WIDTH or not isinstance(value, (dict, list)) or not value:
        return compact
    inner = "  " * (level + 1)
    if isinstance(value, dict):
        items = [f"{inner}{json.dumps(k, ensure_ascii=False)}: {dumps(v, level + 1)}" for k, v in value.items()]
        return "{\n" + ",\n".join(items) + "\n" + "  " * level + "}"
    items = [inner + dumps(v, level + 1) for v in value]
    return "[\n" + ",\n".join(items) + "\n" + "  " * level + "]"


def save(pack: dict, path: Path) -> None:
    Path(path).write_text(dumps(pack) + "\n", encoding="utf-8")


def language_of(pack: dict) -> str:
    """"ro" for "ro-RO": the key of the pack's own language in translation objects."""
    return pack["languageCode"].split("-")[0]


def check(pack: dict) -> list[str]:
    """Problems that would make the app's `PackContentTest` fail. Empty when the pack is fine."""
    problems = []
    own = language_of(pack)
    others = UI_LANGUAGES - {own}
    if pack.get("format") != FORMAT:
        problems.append(f"format is {pack.get('format')}, expected {FORMAT}")

    lemma_ids = [lemma["id"] for lemma in pack.get("lemmas", [])]
    text_ids = [text["id"] for text in pack.get("texts", [])]
    lesson_ids = [lesson["id"] for lesson in pack.get("lessons", [])]
    for kind, ids in (("lemma", lemma_ids), ("text", text_ids), ("lesson", lesson_ids)):
        duplicates = {i for i in ids if ids.count(i) > 1}
        if duplicates:
            problems.append(f"duplicate {kind} ids: {sorted(duplicates)}")

    ranks = [lemma["frequencyRank"] for lemma in pack.get("lemmas", [])]
    if len(ranks) != len(set(ranks)):
        problems.append("frequency ranks are not unique")

    for lemma in pack.get("lemmas", []):
        if not lemma["id"].startswith(own + ":"):
            problems.append(f"lemma {lemma['id']} is not in {own}")
        if set(lemma["meaning"]) != others:
            problems.append(f"lemma {lemma['id']}: meaning in {sorted(lemma['meaning'])}, expected {sorted(others)}")

    used = set()
    known = set(lemma_ids)
    for text in pack.get("texts", []):
        words = 0
        for number, sentence in enumerate(text["sentences"], start=1):
            where = f"{text['id']} sentence {number}"
            if set(sentence["translation"]) != others:
                problems.append(f"{where}: translated into {sorted(sentence['translation'])}, expected {sorted(others)}")
            for token in sentence["tokens"]:
                if "lemma" in token:
                    words += 1
                    used.add(token["lemma"])
                    if token["lemma"] not in known:
                        problems.append(f"{where}: '{token['text']}' points to unknown lemma {token['lemma']}")
                if "formNote" in token and set(token["formNote"]) != UI_LANGUAGES:
                    problems.append(f"{where}: note of '{token['text']}' is not in every UI language")
        if words == 0:
            problems.append(f"{text['id']} has no word")

    for lemma_id in lemma_ids:
        if lemma_id not in used:
            problems.append(f"lemma {lemma_id} is never used")

    if own == "ro":
        for text in romanian_strings(pack):
            if any(char in CEDILLAS for char in text):
                problems.append(f"cedilla instead of comma below in: {text}")
    return problems


def romanian_strings(pack: dict) -> list[str]:
    """Every piece of Romanian written in a Romanian pack: titles, sentences, base forms, examples."""
    found = []
    for text in pack.get("texts", []):
        found.append(text["title"])
        found += ["".join(t["text"] for t in s["tokens"]) for s in text["sentences"]]
    found += [lemma["text"] for lemma in pack.get("lemmas", [])]
    for lesson in pack.get("lessons", []):
        found += [e["text"] for section in lesson["sections"] for e in section.get("examples", [])]
    return found
