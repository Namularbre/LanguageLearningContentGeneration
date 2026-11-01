import unittest

try:
    from fastapi.testclient import TestClient

    from api.main import app
except ImportError:  # the `api` extra is not installed
    TestClient = None

from pipeline import packs
from tests import PACKS


@unittest.skipIf(TestClient is None, "needs the api extra: uv run --extra api …")
class ApiTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.romanian = packs.load(next(p for p in PACKS if p.name == "ro-RO.json"))

    def test_languages_lists_every_pack_with_its_version(self):
        response = self.client.get("/languages")
        self.assertEqual(200, response.status_code)
        self.assertIn({"languageCode": "ro-RO", "version": self.romanian["version"]}, response.json())
        self.assertEqual(len(PACKS), len(response.json()))

    def test_a_pack_is_served_whole(self):
        response = self.client.get("/packs/ro-RO")
        self.assertEqual(200, response.status_code)
        self.assertEqual(self.romanian, response.json())

    def test_an_older_version_gets_the_pack(self):
        response = self.client.get("/packs/ro-RO", params={"since": self.romanian["version"] - 1})
        self.assertEqual(200, response.status_code)

    def test_the_current_version_gets_nothing(self):
        response = self.client.get("/packs/ro-RO", params={"since": self.romanian["version"]})
        self.assertEqual(204, response.status_code)
        self.assertEqual(b"", response.content)

    def test_an_unknown_language_is_not_found(self):
        self.assertEqual(404, self.client.get("/packs/xx-XX").status_code)
        self.assertEqual(404, self.client.get("/packs/..%2Fpyproject").status_code)
