import unittest

from pipeline.notes import form_note


class NotesTest(unittest.TestCase):
    def test_the_base_form_needs_no_note(self):
        self.assertIsNone(form_note("casă", "casă", "NOUN", "Gender=Fem|Number=Sing"))
        self.assertIsNone(form_note("merge", "a merge", "VERB", "Mood=Ind|Person=3|Tense=Pres"))

    def test_a_definite_noun(self):
        note = form_note("casa", "casă", "NOUN", "Case=Acc,Nom|Definite=Def|Gender=Fem|Number=Sing")
        self.assertEqual({"en": "definite article", "fr": "article défini", "ro": "articulat hotărât"}, note)

    def test_a_genitive_definite_noun(self):
        note = form_note("casei", "casă", "NOUN", "Case=Dat,Gen|Definite=Def|Gender=Fem|Number=Sing")
        self.assertEqual("genitive-dative, definite", note["en"])

    def test_a_present_verb(self):
        note = form_note("cumpără", "a cumpăra", "VERB", "Mood=Ind|Number=Sing|Person=3|Tense=Pres|VerbForm=Fin")
        self.assertEqual({"en": "present, he/she", "fr": "présent, il/elle", "ro": "prezent, el/ea"}, note)

    def test_unknown_features_give_no_note(self):
        self.assertIsNone(form_note("bine", "bun", "ADV", "Degree=Pos"))
