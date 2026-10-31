import copy
import json
import unittest

from pipeline import packs
from tests import PACKS


class PacksTest(unittest.TestCase):
    def test_published_packs_pass_the_checks(self):
        self.assertEqual(3, len(PACKS))
        for path in PACKS:
            self.assertEqual([], packs.check(packs.load(path)), path.name)

    def test_formatting_keeps_the_content(self):
        pack = packs.load(PACKS[0])
        self.assertEqual(pack, json.loads(packs.dumps(pack)))

    def test_published_packs_are_formatted(self):
        for path in PACKS:
            self.assertEqual(packs.dumps(packs.load(path)) + "\n", path.read_text(encoding="utf-8"), path.name)

    def test_a_cedilla_in_romanian_is_reported(self):
        pack = copy.deepcopy(packs.load(next(p for p in PACKS if p.name == "ro-RO.json")))
        pack["texts"][0]["title"] = "Şcoala"
        self.assertTrue(any("cedilla" in problem for problem in packs.check(pack)))

    def test_a_word_without_lemma_entry_is_reported(self):
        pack = copy.deepcopy(packs.load(PACKS[0]))
        pack["lemmas"].pop(0)
        problems = packs.check(pack)
        self.assertTrue(any("unknown lemma" in problem for problem in problems), problems)
