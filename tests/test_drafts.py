import copy
import unittest

from pipeline import drafts, packs
from pipeline.analysis import WordAnalysis
from pipeline.llm import FakeLlm
from tests import PACKS

TEXT = {
    "title": "Casa Anei",
    "minutes": 1,
    "sentences": [
        {"text": "Ana cumpără o pâine.", "translation": {"en": "Ana buys a loaf.", "fr": "Ana achète un pain."}},
        {"text": "Pâinea e caldă.", "translation": {"en": "The bread is warm.", "fr": "Le pain est chaud."}},
    ],
}
AI_LEMMAS = {
    "ana": ("Ana", "PROPER_NAME"), "cumpără": ("a cumpăra", "VERB"), "o": ("un", "ARTICLE"),
    "pâine": ("pâine", "NOUN"), "pâinea": ("pâine", "NOUN"), "e": ("a fi", "VERB"), "caldă": ("cald", "ADJECTIVE"),
}
STANZA = {
    "Ana": WordAnalysis("Ana", "Ana", "PROPN", None),
    "cumpără": WordAnalysis("cumpără", "cumpăra", "VERB", "Mood=Ind|Number=Sing|Person=3|Tense=Pres|VerbForm=Fin"),
    "o": WordAnalysis("o", "un", "DET", "Gender=Fem"),
    "pâine": WordAnalysis("pâine", "pâine", "NOUN", "Definite=Ind|Gender=Fem|Number=Sing"),
    "Pâinea": WordAnalysis("Pâinea", "pâine", "NOUN", "Case=Acc,Nom|Definite=Def|Gender=Fem|Number=Sing"),
    "e": WordAnalysis("e", "fi", "AUX", "Mood=Ind|Number=Sing|Person=3|Tense=Pres"),
    # Stanza and the AI disagree on purpose here.
    "caldă": WordAnalysis("caldă", "caldă", "ADJ", "Gender=Fem|Number=Sing"),
}


class FakeAnalyser:
    def analyse(self, sentence):
        from pipeline import tokenizer
        return [STANZA[p.text] for p in tokenizer.split(sentence) if p.is_word]


class DraftsTest(unittest.TestCase):
    def setUp(self):
        self.pack = copy.deepcopy(packs.load(next(p for p in PACKS if p.name == "ro-RO.json")))
        issues = [{"sentence": 1, "where": "text", "problem": "e is informal", "suggestion": "este"}]
        self.draft = drafts.make_draft(self.pack, FakeLlm(TEXT, AI_LEMMAS, issues), FakeAnalyser(),
                                       text_id="ro-test-bread", level="A1", kind="STORY", topic="bread")

    def tokens(self, sentence):
        return self.draft["text"]["sentences"][sentence]["tokens"]

    def test_tokens_give_the_sentences_back(self):
        for index, sentence in enumerate(TEXT["sentences"]):
            self.assertEqual(sentence["text"], "".join(t["text"] for t in self.tokens(index)))

    def test_a_name_has_no_lemma(self):
        self.assertEqual({"text": "Ana"}, self.tokens(0)[0])

    def test_agreeing_lemmas_are_kept_with_a_grammar_note(self):
        buys = self.tokens(0)[2]
        self.assertEqual("ro:a cumpăra", buys["lemma"])
        self.assertEqual("present, he/she", buys["formNote"]["en"])

    def test_a_disagreement_is_flagged_for_the_reviewer(self):
        self.assertEqual([{"sentence": 1, "word": "caldă", "chosen": "ro:caldă", "stanza": "caldă", "gemini": "cald"}],
                         self.draft["flags"])

    def test_new_words_get_a_dictionary_entry(self):
        new_ids = {lemma["id"] for lemma in self.draft["newLemmas"]}
        self.assertIn("ro:caldă", new_ids)
        self.assertNotIn("ro:a fi", new_ids)  # already in the pack

    def test_the_ai_review_and_the_sheet_are_kept(self):
        self.assertEqual("este", self.draft["aiReview"][0]["suggestion"])
        sheet = drafts.review_sheet(self.draft)
        self.assertIn("caldă", sheet)
        self.assertIn("e is informal", sheet)

    def test_a_draft_must_be_approved_before_publishing(self):
        problems = drafts.publish(self.pack, self.draft)
        self.assertTrue(problems)
        self.assertNotIn("ro-test-bread", [t["id"] for t in self.pack["texts"]])

    def test_an_approved_draft_is_added_and_raises_the_version(self):
        version = self.pack["version"]
        self.draft["status"] = "approved"
        self.assertEqual([], drafts.publish(self.pack, self.draft))
        self.assertEqual(version + 1, self.pack["version"])
        published = self.pack["texts"][-1]
        self.assertEqual(("ro-test-bread", "ai"), (published["id"], published["review"]))
        ranks = [lemma["frequencyRank"] for lemma in self.pack["lemmas"]]
        self.assertEqual(len(ranks), len(set(ranks)))

    def test_cedillas_from_the_ai_are_fixed(self):
        text = copy.deepcopy(TEXT)
        text["title"] = "Şcoala"
        draft = drafts.make_draft(self.pack, FakeLlm(text, AI_LEMMAS), FakeAnalyser(),
                                  text_id="ro-x", level="A1", kind="STORY", topic="x")
        self.assertEqual("Școala", draft["text"]["title"])
