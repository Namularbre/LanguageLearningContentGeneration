import bz2
import copy
import io
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pipeline import packs, tatoeba
from pipeline.tatoeba import Corpus, TatoebaSentence
from tests import PACKS


def romanian_pack():
    return copy.deepcopy(packs.load(next(p for p in PACKS if p.name == "ro-RO.json")))


def corpus_with(*sentences, links=(), audio=None):
    corpus = Corpus()
    for sentence in sentences:
        corpus.sentences[sentence.id] = sentence
    for a, b in links:
        corpus.links[a].add(b)
        corpus.links[b].add(a)
    corpus.audio.update(audio or {})
    return corpus


class SelectionTest(unittest.TestCase):
    def setUp(self):
        self.pack = romanian_pack()
        self.forms = tatoeba.known_forms(self.pack)
        # Two forms the pack's texts use, and their lemmas.
        self.form_a, self.form_b = "și", "în"
        self.assertIn(self.form_a, self.forms)
        self.assertIn(self.form_b, self.forms)

    def test_a_readable_translated_sentence_becomes_an_example(self):
        corpus = corpus_with(
            TatoebaSentence(1, "ro", f"Ana {self.form_a} Mihai.", "ana_ro"),
            TatoebaSentence(2, "en", "Ana and Mihai.", "bob"),
            TatoebaSentence(3, "fr", "Ana et Mihai.", "chloe"),
            links=[(1, 2), (1, 3)],
            audio={1: {"url": "https://tatoeba.org/audio/download/9", "author": "ana_ro", "license": "CC BY 4.0"}},
        )
        found = tatoeba.select_examples(self.pack, corpus)
        example = found[self.forms[self.form_a][0]][0]
        self.assertEqual(f"Ana {self.form_a} Mihai.", "".join(t["text"] for t in example["tokens"]))
        self.assertEqual({"en": "Ana and Mihai.", "fr": "Ana et Mihai."}, example["translation"])
        self.assertEqual({"tatoeba": 1, "author": "ana_ro", "license": "CC BY 2.0 FR"}, example["source"])
        self.assertEqual("CC BY 4.0", example["audio"]["license"])

    def test_untranslated_long_or_hard_sentences_are_skipped(self):
        corpus = corpus_with(
            TatoebaSentence(1, "ro", f"Ana {self.form_a} Mihai.", "x"),  # no translation
            TatoebaSentence(2, "ro", " ".join([self.form_a] * 11), "x"),  # 11 words
            TatoebaSentence(3, "ro", f"{self.form_a} zbârnâit fulgerător", "x"),  # 2 unknown words
            TatoebaSentence(4, "en", "x", "y"), TatoebaSentence(5, "en", "y", "y"),
            links=[(2, 4), (3, 5)],
        )
        self.assertEqual({}, tatoeba.select_examples(self.pack, corpus))

    def test_fully_translated_and_short_sentences_come_first(self):
        corpus = corpus_with(
            TatoebaSentence(1, "ro", f"{self.form_a} {self.form_b} {self.form_a}.", "x"),
            TatoebaSentence(2, "ro", f"{self.form_a} {self.form_b}.", "x"),
            TatoebaSentence(3, "ro", f"{self.form_a}.", "x"),
            TatoebaSentence(10, "en", "a", "y"), TatoebaSentence(11, "fr", "b", "y"),
            TatoebaSentence(12, "en", "c", "y"), TatoebaSentence(13, "fr", "d", "y"),
            TatoebaSentence(14, "en", "e", "y"),
            links=[(1, 10), (1, 11), (2, 12), (2, 13), (3, 14)],
        )
        found = tatoeba.select_examples(self.pack, corpus, per_word=2)
        ids = [e["source"]["tatoeba"] for e in found[self.forms[self.form_a][0]]]
        self.assertEqual([2, 1], ids)  # 3 is shortest but has no French translation

    def test_cedillas_are_fixed(self):
        corpus = corpus_with(TatoebaSentence(1, "ro", f"Şi {self.form_a}.", "x"), TatoebaSentence(2, "en", "And.", "y"),
                             links=[(1, 2)])
        found = tatoeba.select_examples(self.pack, corpus)
        self.assertTrue(all("Ş" not in t["text"] for e in found[self.forms[self.form_a][0]] for t in e["tokens"]))

    def test_examples_pass_the_checks_and_raise_the_version(self):
        corpus = corpus_with(TatoebaSentence(1, "ro", f"Ana {self.form_a} Mihai.", "x"),
                             TatoebaSentence(2, "en", "Ana and Mihai.", "y"), links=[(1, 2)])
        version = self.pack["version"]
        self.assertEqual(1, tatoeba.apply_examples(self.pack, tatoeba.select_examples(self.pack, corpus)))
        self.assertEqual(version + 1, self.pack["version"])
        self.assertEqual([], packs.check(self.pack))
        # Same examples again: nothing changes.
        tatoeba.apply_examples(self.pack, tatoeba.select_examples(self.pack, corpus))
        self.assertEqual(version + 1, self.pack["version"])

    def test_an_example_without_credit_is_reported(self):
        corpus = corpus_with(TatoebaSentence(1, "ro", f"Ana {self.form_a} Mihai.", "x"),
                             TatoebaSentence(2, "en", "Ana and Mihai.", "y"), links=[(1, 2)])
        tatoeba.apply_examples(self.pack, tatoeba.select_examples(self.pack, corpus))
        lemma = next(l for l in self.pack["lemmas"] if l.get("examples"))
        del lemma["examples"][0]["source"]["author"]
        self.assertTrue(any("credits" in p for p in packs.check(self.pack)))


class LoadingTest(unittest.TestCase):
    """Reads files shaped like Tatoeba's exports (tab-separated, .tsv.bz2 and .tar.bz2)."""

    def test_load_corpus(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            files = {
                "ron_sentences_detailed.tsv.bz2": bz2.compress(
                    "1\tron\tȘi eu.\tana\t2020-01-01\t2020-01-01\n".encode()),
                "eng_sentences_detailed.tsv.bz2": bz2.compress("2\teng\tMe too.\tbob\t\\N\t\\N\n".encode()),
                "fra_sentences_detailed.tsv.bz2": bz2.compress("3\tfra\tMoi aussi.\tchloe\t\\N\t\\N\n".encode()),
                "links.tar.bz2": _tar("links.csv", "1\t2\n2\t1\n1\t3\n3\t1\n1\t999\n"),
                "sentences_with_audio.tar.bz2": _tar("sentences_with_audio.csv", "1\t77\tana\tCC BY-NC 4.0\t\\N\n2\t78\tbob\t\t\\N\n"),
            }

            def fake_download(url, cache):
                path = tmp / url.rsplit("/", 1)[1]
                path.write_bytes(files[path.name])
                return path

            with mock.patch.object(tatoeba, "_download", fake_download):
                corpus = tatoeba.load_corpus(["en", "fr", "ro"], tmp)
        self.assertEqual(TatoebaSentence(1, "ro", "Și eu.", "ana"), corpus.sentences[1])
        self.assertEqual({2, 3}, corpus.links[1])
        self.assertEqual({"url": "https://tatoeba.org/audio/download/77", "author": "ana", "license": "CC BY-NC 4.0"},
                         corpus.audio[1])
        self.assertNotIn(2, corpus.audio)  # no licence: may not be reused


def _tar(name, text):
    data = text.encode()
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:bz2") as archive:
        info = tarfile.TarInfo(name)
        info.size = len(data)
        archive.addfile(info, io.BytesIO(data))
    return buffer.getvalue()
