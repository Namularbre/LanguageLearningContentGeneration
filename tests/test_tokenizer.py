import unittest

from pipeline import packs, tokenizer
from tests import PACKS


def words(sentence):
    return [p.text for p in tokenizer.split(sentence) if p.is_word]


class TokenizerTest(unittest.TestCase):
    # Same cases as the app's TokenizerTest.
    def test_joining_the_pieces_gives_the_sentence_back(self):
        sentence = "„Bună dimineața, Ana! Ce mai faci?”"
        self.assertEqual(sentence, "".join(p.text for p in tokenizer.split(sentence)))

    def test_romanian_diacritics_stay_inside_words(self):
        self.assertEqual(["Ea", "cumpără", "roșii", "și", "brânză"], words("Ea cumpără roșii și brânză."))

    def test_a_french_elision_gives_two_words(self):
        self.assertEqual(["l'", "homme", "qu'", "il", "aime"], words("l'homme qu'il aime"))

    def test_a_hyphen_separates_words(self):
        self.assertEqual(["într", "o", "zi"], words("într-o zi"))

    def test_a_sentence_without_letters_has_no_word(self):
        self.assertEqual([tokenizer.Piece("…", False, 0)], tokenizer.split("…"))

    def test_cuts_every_published_sentence_like_the_app(self):
        # The published packs were cut by the app's tokenizer: this one must give the same pieces.
        for path in PACKS:
            for text in packs.load(path)["texts"]:
                for sentence in text["sentences"]:
                    expected = [t["text"] for t in sentence["tokens"]]
                    actual = [p.text for p in tokenizer.split("".join(expected))]
                    self.assertEqual(expected, actual, text["id"])
