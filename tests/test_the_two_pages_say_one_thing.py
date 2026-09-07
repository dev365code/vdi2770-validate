"""Two public pages carry the same upgrade, so they have to carry it the same way.

The front page is what `vdi2770-validate` used to render on its index page and
what the repository shows. `README-vdi2770-validate.md` is what that name
renders now — the distribution is two lines of alias, and a page describing a
conformance checker for it would be a near-truth.

One risk on two surfaces is how a warning ends up meaning two things: the
commands drift, one page gets a caveat the other never grew, and the reader who
saw the wrong one does the wrong thing. So the commands are compared, in order,
and each page has to carry the same three refusals to overclaim.
"""
import re

from conftest import ROOT

FRONT = ROOT / "README.md"
ALIAS = ROOT / "README-vdi2770-validate.md"


def prose(page):
    """The page with its line breaks taken out.

    What a page says does not depend on where it wraps, and a phrase this file
    looks for lands across a break as often as not — which made the first
    version of these assertions fail on pages that said the right thing.
    """
    return " ".join(page.read_text(encoding="utf-8").split())


def installs(page):
    """Every `pip install` the page gives, in the order it gives them."""
    found = []
    for line in page.read_text(encoding="utf-8").splitlines():
        m = re.search(r"pip install (?:-U )?[\"']?([A-Za-z0-9_.\[\]-]+)[\"']?", line)
        if m and m.group(1).startswith("vdi2770"):
            found.append(m.group(1))
    return found


def test_both_pages_name_the_same_installs():
    """Not the same order of prose — the same set of commands.

    A command on one page and not the other is a reader told to do something
    the other reader is not, about one upgrade.
    """
    front, alias = set(installs(FRONT)), set(installs(ALIAS))
    assert front == alias, (
        f"the front page gives {sorted(front)} and the old name's page gives "
        f"{sorted(alias)}; one upgrade, two sets of instructions")


def test_the_upgrade_command_is_the_same_command_on_both():
    """And it is the one that used to destroy an installation.

    That sentence is the reason both pages exist in this state, and a page that
    gives a different command for it is telling somebody to take a path nobody
    tested.
    """
    for page in (FRONT, ALIAS):
        text = prose(page)
        assert "pip install -U vdi2770-validate" in text, (
            f"{page.name} does not name the upgrade command")
        assert "ordinary" in text, (
            f"{page.name} names the upgrade and does not say what it is now")


def test_neither_page_says_the_trap_is_gone():
    """What went away is the overlap this project created, not the shape of the
    failure. A page that says otherwise is selling a guarantee nobody has: an
    installation that takes half the upgrade still has old rules in it, and both
    pages have to say so."""
    for page in (FRONT, ALIAS):
        text = prose(page)
        for forbidden in ("no longer possible", "cannot happen", "trap is gone",
                          "impossible to break", "nothing can go wrong"):
            assert forbidden not in text.lower(), (
                f"{page.name} claims {forbidden!r}; what went away is the "
                f"overlap this project made, and the half-upgrade is still a "
                f"half-upgrade")
        assert "half" in text.lower(), (
            f"{page.name} does not tell the reader what a half-taken upgrade "
            f"leaves them with")


def test_both_pages_carry_the_refusal_and_what_it_is_not():
    """Exit 3 is a versioned surface and it is not a verdict on a container.
    A page that mentions the refusal without that second half invites a reader
    to log it against their supplier."""
    for page in (FRONT, ALIAS):
        text = prose(page)
        assert "exit 3" in text, f"{page.name} does not name the refusal"
        assert "not a verdict on any container" in text, (
            f"{page.name} names the refusal and does not say what it is not")


def test_both_pages_admit_the_thing_that_cannot_be_carried():
    """A pickle written through the new path names the new modules, and no
    aliasing technique changes that. It is the one promise the alias cannot
    keep, so it is on both pages rather than in a changelog nobody reads."""
    for page in (FRONT, ALIAS):
        text = prose(page)
        assert "pickle" in text.lower(), (
            f"{page.name} does not mention the one thing the old name cannot "
            f"carry across")
