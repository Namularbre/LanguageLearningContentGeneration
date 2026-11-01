import unittest

from pipeline.analysis import processors_for


class ProcessorsTest(unittest.TestCase):
    # Shapes taken from Stanza's resources.json (version 1.15).
    def test_romanian_has_no_multi_word_tokens(self):
        self.assertEqual("tokenize,pos,lemma", processors_for({"tokenize": {}, "pos": {}, "lemma": {}, "depparse": {}}))

    def test_french_uses_multi_word_tokens(self):
        self.assertEqual("tokenize,mwt,pos,lemma", processors_for({"tokenize": {}, "mwt": {}, "pos": {}, "lemma": {}}))

    def test_a_language_without_lemmatiser_is_refused(self):
        with self.assertRaises(ValueError):
            processors_for({"tokenize": {}})
