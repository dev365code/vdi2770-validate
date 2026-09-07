"""The published data this tool loads, turned into values.

Two families, both read from `data/` at import and both immutable afterwards:
the rule catalogue (`rules`, `rule`) and the vocabulary the rules are written
against (`document_classes`, `german_for`, `english_for`,
`CLASSIFICATION_SYSTEM`, `ISO_639_1`).

The first line used to say "and nothing else" while the second family sat
underneath it. They change for different reasons -- a rule is added; IDTA
republishes a table -- so this docstring is the honest version rather than a
claim about cohesion the file did not keep. Splitting them is on the board.
"""
from __future__ import annotations

from functools import lru_cache
from types import MappingProxyType
from typing import Dict, Tuple

from .model import About, Obligation, Rule, Severity
from .resources import load_json


@lru_cache(maxsize=1)
def rules() -> Dict[str, Rule]:
    doc = load_json("rules.json")
    out: Dict[str, Rule] = {}
    for r in doc["rules"]:
        out[r["id"]] = Rule(
            id=r["id"],
            title=r["title"],
            severity=Severity(r["severity"]),
            obligation=Obligation(r["obligation"]),
            about=About(r["about"]),
            layer=r["layer"],
            remedy=r["remedy"],
            basis=r.get("basis", ""),
            ref_codes=tuple(r.get("refCodes", ())),
            ref_keys=tuple(r.get("refKeys", ())),
            why_ours=r.get("whyOurs", ""),
        )
    # The cache hands out the same object every call, so a caller could empty
    # the catalogue for the whole process — while this module's first line
    # says both families are immutable after import.
    return MappingProxyType(out)


def rule(rule_id: str) -> Rule:
    return rules()[rule_id]


@lru_cache(maxsize=1)
def document_classes() -> Dict[str, dict]:
    doc = load_json("document-classes.json")
    return MappingProxyType({c["classId"]: c for c in doc["classes"]})


def german_for(class_id: str) -> Tuple[str, ...]:
    """Both published German renderings for a class id. They agree on all twelve
    today; accepting both means a future divergence widens the accepted set
    instead of silently failing conformant documents."""
    c = document_classes().get(class_id)
    if not c:
        return ()
    de = c["nameDe"]
    return tuple(dict.fromkeys([de["idta02004"], de["ddcReference"]]))


def english_for(class_id: str) -> Tuple[str, ...]:
    """Both published renderings for a class id. We accept either, because the
    two sources disagree and we are not the ones who get to break the tie."""
    c = document_classes().get(class_id)
    if not c:
        return ()
    en = c["nameEn"]
    return tuple(dict.fromkeys([en["idta02004"], en["ddcReference"]]))


CLASSIFICATION_SYSTEM = "VDI2770:2018"

# ISO 639-1 plus the ISO 639-2 codes that have no two-letter form are far too many
# to embed usefully; we check shape and the common set, and say so in scope.md.
ISO_639_1 = {
    "ab","aa","af","ak","sq","am","ar","an","hy","as","av","ae","ay","az","bm","ba","eu","be","bn",
    "bh","bi","bs","br","bg","my","ca","ch","ce","ny","zh","cv","kw","co","cr","hr","cs","da","dv",
    "nl","dz","en","eo","et","ee","fo","fj","fi","fr","ff","gl","ka","de","el","gn","gu","ht","ha",
    "he","hz","hi","ho","hu","ia","id","ie","ga","ig","ik","io","is","it","iu","ja","jv","kl","kn",
    "kr","ks","kk","km","ki","rw","ky","kv","kg","ko","ku","kj","la","lb","lg","li","ln","lo","lt",
    "lu","lv","gv","mk","mg","ms","ml","mt","mi","mr","mh","mn","na","nv","nd","ne","ng","nb","nn",
    "no","ii","nr","oc","oj","cu","om","or","os","pa","pi","fa","pl","ps","pt","qu","rm","rn","ro",
    "ru","sa","sc","sd","se","sm","sg","sr","gd","sn","si","sk","sl","so","st","es","su","sw","ss",
    "sv","ta","te","tg","th","ti","bo","tk","tl","tn","to","tr","ts","tt","tw","ty","ug","uk","ur",
    "uz","ve","vi","vo","wa","cy","wo","fy","xh","yi","yo","za","zu",
}
