"""Command line: uv run pipeline {draft,publish,check,format} …  (see README.md)."""

import argparse
import json
import sys
from pathlib import Path

from . import drafts, packs

PACKS = Path(__file__).resolve().parent.parent / "packs"
DRAFTS = Path(__file__).resolve().parent.parent / "drafts"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="pipeline")
    commands = parser.add_subparsers(dest="command", required=True)

    draft = commands.add_parser("draft", help="write a new text with Gemini and annotate it")
    draft.add_argument("--language", required=True, help="pack language, e.g. ro-RO")
    draft.add_argument("--id", required=True, help="text id, e.g. ro-bakery")
    draft.add_argument("--level", required=True, choices=["A1", "A2", "B1", "B2", "C1"])
    draft.add_argument("--kind", default="STORY", choices=["STORY", "DIALOGUE", "NEWS"])
    draft.add_argument("--topic", required=True)
    draft.add_argument("--sentences", type=int, default=8)

    publish = commands.add_parser("publish", help="add approved drafts to their pack")
    publish.add_argument("drafts", nargs="+", type=Path)

    check = commands.add_parser("check", help="check packs as the app's PackContentTest does")
    check.add_argument("packs", nargs="*", type=Path)

    fmt = commands.add_parser("format", help="rewrite packs in the stable layout")
    fmt.add_argument("packs", nargs="*", type=Path)

    args = parser.parse_args(argv)
    if args.command == "draft":
        return _draft(args)
    if args.command == "publish":
        return _publish(args.drafts)
    paths = args.packs or sorted(PACKS.glob("*.json"))
    if args.command == "check":
        failed = False
        for path in paths:
            problems = packs.check(packs.load(path))
            print(f"{path.name}: {'OK' if not problems else f'{len(problems)} problem(s)'}")
            for problem in problems:
                print(f"  - {problem}")
            failed |= bool(problems)
        return 1 if failed else 0
    for path in paths:
        packs.save(packs.load(path), path)
    return 0


def _draft(args) -> int:
    from .analysis import StanzaAnalyser
    from .llm import GeminiLlm

    pack = packs.load(PACKS / f"{args.language}.json")
    language = packs.language_of(pack)
    result = drafts.make_draft(pack, GeminiLlm(), StanzaAnalyser(language), text_id=args.id, level=args.level,
                               kind=args.kind, topic=args.topic, sentences=args.sentences)
    DRAFTS.mkdir(exist_ok=True)
    (DRAFTS / f"{args.id}.json").write_text(packs.dumps(result) + "\n", encoding="utf-8")
    (DRAFTS / f"{args.id}.md").write_text(drafts.review_sheet(result), encoding="utf-8")
    print(f"Draft: drafts/{args.id}.json ({len(result['flags'])} word(s) to check, "
          f"{len(result['aiReview'])} AI remark(s)). Review sheet: drafts/{args.id}.md")
    return 0


def _publish(paths) -> int:
    for path in paths:
        draft = json.loads(path.read_text(encoding="utf-8"))
        pack_path = PACKS / f"{draft['languageCode']}.json"
        pack = packs.load(pack_path)
        problems = drafts.publish(pack, draft)
        if problems:
            print(f"{path.name}: not published")
            for problem in problems:
                print(f"  - {problem}")
            return 1
        packs.save(pack, pack_path)
        print(f"{path.name}: published in {pack_path.name}, version {pack['version']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
