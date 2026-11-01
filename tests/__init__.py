from pathlib import Path

PACKS = sorted((Path(__file__).resolve().parent.parent / "packs").glob("*.json"))
