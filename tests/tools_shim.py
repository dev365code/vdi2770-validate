"""Rules exercised by the vendored corpus rather than by a built fixture."""
from functools import lru_cache

from vdi2770_validate.runner import check_file

from conftest import CORPUS


@lru_cache(maxsize=1)
def corpus_fired():
    out = set()
    for z in sorted(CORPUS.rglob("*.zip")):
        out |= {f.rule.id for f in check_file(str(z)).findings}
    return frozenset(out)
