"""Cuts a sentence into words and the text between them, exactly like the app's `Tokenizer`
(`:core:domain/reading/Tokenizer.kt`): joining the pieces gives the sentence back.

A word is a run of letters. An apostrophe right after letters stays with them, so French elisions
give two words ("l'homme" -> "l'", "homme"). A hyphen separates words ("într-o" -> "într", "-", "o").
"""

import re
from dataclasses import dataclass

# [^\W\d_] is "a letter" in Python's re (no \p{L}).
_WORD = re.compile(r"[^\W\d_]+['’]?")


@dataclass(frozen=True)
class Piece:
    text: str
    is_word: bool
    start: int  # offset of the piece in the sentence

    @property
    def end(self) -> int:
        return self.start + len(self.text)


def split(sentence: str) -> list[Piece]:
    pieces = []
    end = 0
    for match in _WORD.finditer(sentence):
        if match.start() > end:
            pieces.append(Piece(sentence[end:match.start()], False, end))
        pieces.append(Piece(match.group(), True, match.start()))
        end = match.end()
    if end < len(sentence):
        pieces.append(Piece(sentence[end:], False, end))
    return pieces
