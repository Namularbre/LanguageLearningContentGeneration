"""Word analysis with Stanza (https://stanfordnlp.github.io/stanza/): base form, part of speech and
grammatical features of every word, cut the same way as the app does.

Stanza has its own cutting rules (it splits French "du" into "de le", for instance), so its words
are matched to the app's words by their position in the sentence.
"""

from dataclasses import dataclass

from . import tokenizer


@dataclass(frozen=True)
class WordAnalysis:
    text: str          # the word as written in the sentence
    lemma: str | None  # base form, None when Stanza could not decide (several words in one)
    upos: str          # Universal Dependencies part of speech: NOUN, VERB, PROPN…
    feats: str | None  # e.g. "Case=Gen|Definite=Def|Number=Sing"


class StanzaAnalyser:
    """Loads Stanza once per language. The first run downloads the model (a few hundred MB)."""

    def __init__(self, language: str):
        import stanza  # imported here so the rest of the pipeline (and its tests) works without it
        from stanza.resources.common import download_resources_json, load_resources_json

        # Not every language has every processor: Romanian has no multi-word token model ("mwt"),
        # French and English do. Ask only for what the language offers.
        download_resources_json()
        processors = processors_for(load_resources_json().get(language, {}))
        stanza.download(language, processors=processors, verbose=False)
        self._nlp = stanza.Pipeline(language, processors=processors, download_method=None, verbose=False)

    def analyse(self, sentence: str) -> list[WordAnalysis]:
        """One analysis per word of the app's tokenizer, in order."""
        tokens = []  # (start, end, [words])
        for stanza_sentence in self._nlp(sentence).sentences:
            for token in stanza_sentence.tokens:
                tokens.append((token.start_char, token.end_char, token.words))
        return [_match(piece, tokens) for piece in tokenizer.split(sentence) if piece.is_word]


WANTED_PROCESSORS = ("tokenize", "mwt", "pos", "lemma")


def processors_for(available: dict) -> str:
    """The processors to load, among those Stanza offers for the language, e.g. "tokenize,pos,lemma"."""
    missing = [p for p in ("tokenize", "pos", "lemma") if p not in available]
    if missing:
        raise ValueError(f"Stanza has no {', '.join(missing)} model for this language")
    return ",".join(p for p in WANTED_PROCESSORS if p in available)


def _match(piece: tokenizer.Piece, tokens) -> WordAnalysis:
    overlapping = [words for start, end, words in tokens if start < piece.end and piece.start < end]
    if len(overlapping) != 1 or len(overlapping[0]) != 1:
        # The app's word covers several Stanza words (or the reverse): left to the AI and the reviewer.
        upos = overlapping[0][0].upos if overlapping else "X"
        return WordAnalysis(piece.text, None, upos, None)
    word = overlapping[0][0]
    return WordAnalysis(piece.text, word.lemma, word.upos, word.feats)
