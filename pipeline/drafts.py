"""Turning an AI-written text into a draft to review, then publishing a reviewed draft into a pack.

A draft is a JSON file in `drafts/`: the text in pack format plus what the reviewer must look at
(`flags`: words where Stanza and Gemini disagree; `aiReview`: problems found by the AI proofreader).
A Markdown sheet with the same content is written next to it, easier to read.
"""

from . import notes, packs, tokenizer

# Gemini's parts of speech are the app's `PartOfSpeech`; Stanza's are Universal Dependencies tags.
UPOS_TO_PART_OF_SPEECH = {
    "NOUN": "NOUN", "VERB": "VERB", "AUX": "VERB", "ADJ": "ADJECTIVE", "ADV": "ADVERB", "PRON": "PRONOUN",
    "ADP": "PREPOSITION", "CCONJ": "CONJUNCTION", "SCONJ": "CONJUNCTION", "DET": "ARTICLE", "NUM": "NUMERAL",
    "INTJ": "INTERJECTION",
}
CEDILLA_FIXES = str.maketrans({"ş": "ș", "Ş": "Ș", "ţ": "ț", "Ţ": "Ț"})


def stanza_base_form(language: str, analysis) -> str | None:
    """Stanza's lemma written the way the packs write base forms (Romanian verbs take "a")."""
    if analysis.lemma is None or analysis.upos == "PROPN":
        return None
    lemma = analysis.lemma.lower()
    if language == "ro" and analysis.upos in ("VERB", "AUX"):
        lemma = "a " + lemma
    return lemma


def make_draft(pack: dict, llm, analyser, *, text_id: str, level: str, kind: str, topic: str, sentences: int = 8) -> dict:
    language = packs.language_of(pack)
    known = {lemma["id"]: lemma for lemma in pack["lemmas"]}
    known_words = [lemma["text"] for lemma in sorted(pack["lemmas"], key=lambda l: l["frequencyRank"])]

    written = llm.write_text(language, level, kind, topic, sentences, known_words)
    if language == "ro":  # the AI sometimes writes ş/ţ with a cedilla: the comma below is the correct letter
        written["title"] = written["title"].translate(CEDILLA_FIXES)
        for sentence in written["sentences"]:
            sentence["text"] = sentence["text"].translate(CEDILLA_FIXES)

    pieces_by_sentence = [tokenizer.split(s["text"]) for s in written["sentences"]]
    words_by_sentence = [[p.text for p in pieces if p.is_word] for pieces in pieces_by_sentence]
    ai_lemmas = llm.lemmatise(language, words_by_sentence)

    flags, new_lemmas, out_sentences = [], {}, []
    for index, (sentence, pieces) in enumerate(zip(written["sentences"], pieces_by_sentence)):
        analyses = analyser.analyse(sentence["text"])
        ai_words = iter(ai_lemmas[index])
        stanza_words = iter(analyses)
        tokens = []
        for piece in pieces:
            if not piece.is_word:
                tokens.append({"text": piece.text})
                continue
            ai = next(ai_words, {"lemma": None, "partOfSpeech": "NOUN"})
            stanza = next(stanza_words)
            token = _token(language, piece.text, ai, stanza, index, flags)
            tokens.append(token)
            lemma_id = token.get("lemma")
            if lemma_id and lemma_id not in known and lemma_id not in new_lemmas:
                part_of_speech = ai.get("partOfSpeech") if ai.get("partOfSpeech") in UPOS_TO_PART_OF_SPEECH.values() \
                    else UPOS_TO_PART_OF_SPEECH.get(stanza.upos, "NOUN")
                new_lemmas[lemma_id] = {"text": lemma_id.split(":", 1)[1], "partOfSpeech": part_of_speech,
                                        "example": sentence["text"]}
        out_sentences.append({"tokens": tokens, "translation": sentence["translation"]})

    described = llm.describe_lemmas(language, list(new_lemmas.values())) if new_lemmas else []
    lemmas = []
    for (lemma_id, entry), description in zip(new_lemmas.items(), described):
        lemma = {"id": lemma_id, "text": entry["text"], "partOfSpeech": entry["partOfSpeech"]}
        if description.get("gender") and entry["partOfSpeech"] == "NOUN":
            lemma["gender"] = description["gender"]
        lemma["meaning"] = description["meaning"]
        lemmas.append(lemma)

    text = {"id": text_id, "level": level, "kind": kind, "title": written["title"], "minutes": written["minutes"],
            "sentences": out_sentences, "review": "ai"}
    issues = llm.review(language, level, {"title": written["title"], "sentences": written["sentences"]})
    return {
        "languageCode": pack["languageCode"],
        "status": "to review",  # the reviewer sets "approved" once the flags and issues are handled
        "reviewedBy": "ai",     # the reviewer sets "human" if a person fluent in the language read it
        "text": text,
        "newLemmas": lemmas,
        "flags": flags,
        "aiReview": issues,
    }


def _token(language: str, word: str, ai: dict, stanza, sentence_index: int, flags: list) -> dict:
    ai_is_name = ai.get("partOfSpeech") == "PROPER_NAME"
    stanza_is_name = stanza.upos == "PROPN"
    if ai_is_name and stanza_is_name:
        return {"text": word}  # names cannot be tapped and do not count in comprehension
    ai_lemma = (ai.get("lemma") or "").lower() or None
    stanza_lemma = stanza_base_form(language, stanza)
    if ai_lemma and ai_lemma == stanza_lemma:
        token = {"text": word, "lemma": f"{language}:{ai_lemma}"}
        note = notes.form_note(word, ai_lemma, stanza.upos, stanza.feats)
        if note:
            token["formNote"] = note
        return token
    # Disagreement: keep Stanza's answer when it has one (it is trained on annotated corpora),
    # and ask the reviewer.
    chosen = stanza_lemma or ai_lemma or word.lower()
    flags.append({"sentence": sentence_index, "word": word, "chosen": f"{language}:{chosen}",
                  "stanza": stanza_lemma if not stanza_is_name else "PROPER_NAME",
                  "gemini": ai_lemma if not ai_is_name else "PROPER_NAME"})
    return {"text": word, "lemma": f"{language}:{chosen}"}


def review_sheet(draft: dict) -> str:
    """The draft as Markdown, for the reviewer."""
    text = draft["text"]
    lines = [f"# {text['title']} ({text['id']}, {text['level']}, {text['kind'].lower()})", "",
             "Status: " + draft["status"] + " · reviewed by: " + draft["reviewedBy"], "", "## Text", ""]
    for index, sentence in enumerate(text["sentences"]):
        lines.append(f"{index}. **{''.join(t['text'] for t in sentence['tokens'])}**")
        for code, translation in sentence["translation"].items():
            lines.append(f"   - {code}: {translation}")
    lines += ["", "## Words to check (Stanza and Gemini disagree)", ""]
    lines += [f"- sentence {f['sentence']}, *{f['word']}*: kept `{f['chosen']}` (Stanza: {f['stanza']}, "
              f"Gemini: {f['gemini']})" for f in draft["flags"]] or ["None."]
    lines += ["", "## AI proofreading", ""]
    lines += [f"- sentence {i['sentence']} ({i['where']}): {i['problem']} → {i['suggestion']}"
              for i in draft["aiReview"]] or ["Nothing reported."]
    lines += ["", "## New words", ""]
    lines += [f"- {l['text']} ({l['partOfSpeech'].lower()}): " + ", ".join(f"{c}: {m}" for c, m in l["meaning"].items())
              for l in draft["newLemmas"]] or ["None."]
    lines += ["", "To publish: fix the draft JSON if needed, set \"status\" to \"approved\" (and \"reviewedBy\" to "
              "\"human\" if a fluent speaker read it), then run `uv run pipeline publish <draft>`.", ""]
    return "\n".join(lines)


def publish(pack: dict, draft: dict) -> list[str]:
    """Adds an approved draft to the pack (in place) and raises its version. Returns the problems
    found by `packs.check`; the caller must not save the pack when there are any."""
    if draft["status"] != "approved":
        return [f"draft {draft['text']['id']} is not approved (status: {draft['status']})"]
    if draft["languageCode"] != pack["languageCode"]:
        return [f"draft is in {draft['languageCode']}, pack in {pack['languageCode']}"]
    known = {lemma["id"] for lemma in pack["lemmas"]}
    next_rank = max((lemma["frequencyRank"] for lemma in pack["lemmas"]), default=0) + 1
    for lemma in draft["newLemmas"]:
        if lemma["id"] not in known:
            # New words go after the known ones: the ranks order the level test, most frequent first.
            pack["lemmas"].append({**lemma, "frequencyRank": next_rank})
            known.add(lemma["id"])
            next_rank += 1
    text = {**draft["text"], "review": draft["reviewedBy"]}
    pack["texts"] = [t for t in pack["texts"] if t["id"] != text["id"]] + [text]
    pack["version"] += 1
    return packs.check(pack)
