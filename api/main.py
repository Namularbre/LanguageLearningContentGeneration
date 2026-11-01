"""Content API, kept as small as possible: two read-only routes over the files of `packs/`.

Run it with `uv run --extra api fastapi dev api/main.py`, then open http://127.0.0.1:8000/docs.
The files are read at each request, so a `pipeline publish` is served at once, without a restart.
"""

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Response

PACKS = Path(__file__).resolve().parent.parent / "packs"

app = FastAPI(title="LanguageLearning content API")


def _packs() -> dict[str, Path]:
    """Language code -> pack file, e.g. "ro-RO" -> packs/ro-RO.json."""
    return {path.stem: path for path in sorted(PACKS.glob("*.json"))}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/languages")
def languages() -> list[dict]:
    """The available packs and their content version: the app compares it with the one it has."""
    return [{"languageCode": code, "version": _load(path)["version"]} for code, path in _packs().items()]


@app.get("/packs/{language_code}")
def pack(language_code: str, since: int | None = None):
    """The whole pack of a language. With `since`, answers 204 (no content) when the app already has
    this version or a newer one, so nothing is downloaded for nothing."""
    path = _packs().get(language_code)  # only known file names: no path built from the request
    if path is None:
        raise HTTPException(status_code=404, detail=f"No pack for {language_code}")
    content = _load(path)
    if since is not None and since >= content["version"]:
        return Response(status_code=204)
    return content
