"""The reference implementation's own examples are the closest thing to ground
truth we have. A structural rule that fires on one of them is our bug until
proven otherwise.

Written before the fix it forced, because the alternative — changing a constant
and then finding out — is how this file came to exist.
"""
import pytest

from conftest import CORPUS
from vdi2770_validate.runner import check_file

# Archives the upstream project named as broken. Everything else is theirs to
# consider valid, and our structural rules must not contradict that.
DELIBERATELY_BROKEN = {
    "empty.zip", "InvalidXMLName.zip", "missing_Maindocument.zip", "missing_Metadata.zip",
    "demo_invalid_doc_type_names.zip", "documentcontainer-invalid.zip",
    "document-invalid-pdfa-b.zip", "missingdocuments.zip", "morethanonepdfcontainer.zip",
    "folders.zip",
}

# Rules that describe the *shape* of a container. A rule about content may
# legitimately disagree with an upstream example; a rule about shape may not.
STRUCTURAL = {"Z1", "Z2", "Z3", "Z6", "Z7", "Z9"}

CONTAINERS = sorted(p for p in CORPUS.rglob("*.zip") if p.name not in DELIBERATELY_BROKEN)


@pytest.mark.parametrize("path", CONTAINERS, ids=lambda p: p.name)
def test_no_structural_rule_fires_on_an_upstream_example(path):
    fired = {f.rule.id for f in check_file(str(path)).findings} & STRUCTURAL
    assert not fired, (
        f"{path.name} is an example the reference project ships as usable, and we "
        f"call its shape wrong: {sorted(fired)}")
