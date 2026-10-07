"""Refresh the published rule/pair counts and the capability picture's input."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "packages/vdi2770/src")]

from vdi2770 import __version__
from vdi2770.validate.catalog import rules


def main():
    total = len(rules())
    manifest = json.loads((ROOT / "tests/fixtures/MANIFEST.json").read_text(encoding="utf-8"))
    paired = len({row["rule"] for row in manifest["fixtures"].values() if row["basedOn"] is not None})
    fired = len(json.loads((ROOT / "docs/rule-coverage.json").read_text(encoding="utf-8"))["fired"])
    for name in ("README.md", "docs/what-it-catches.md"):
        path = ROOT / name
        text = path.read_text(encoding="utf-8")
        text = re.sub(r"\d+ of \d+ rules have", f"{paired} of {total} rules have", text)
        text = re.sub(r"\d+ of \d+, every rule that can have one", f"{paired} of {total}, every rule that can have one", text)
        text = re.sub(r"rules-\d+_each", f"rules-{total}_each", text)
        text = re.sub(r": \d+ rules, each", f": {total} rules, each", text)
        text = re.sub(r"(?:Forty(?:-one)?|\d+) of the\s+\d+ fire", f"{fired} of the\n  {total} fire", text)
        path.write_text(text, encoding="utf-8")
    path = ROOT / "docs/capabilities.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["as_of"] = __version__
    coverage = next(axis for axis in data["axes"] if axis["key"] == "coverage")
    coverage.update(now=paired, target=paired, now_text=f"{paired} of {total} rules have a fixture pair",
                    target_text=f"{paired} of {total}, every rule that can have one")
    coverage["evidence"] = [{"file": "README.md", "says": f"{paired} of {total} rules have a minimal fixture pair"}]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"summary: {paired}/{total} fixture pairs")


if __name__ == "__main__":
    main()
