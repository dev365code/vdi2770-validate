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
    """Every `pip install` the page gives.

    `finditer` over the whole page, not one match per line: a line can carry two
    commands, and the flag has two spellings. The first version took `--upgrade`
    for the package name and dropped that command entirely.
    """
    return re.findall(
        r"""pip install (?:-U |--upgrade )?["']?(vdi2770[A-Za-z0-9_.\[\]-]*)["']?""",
        page.read_text(encoding="utf-8"))


def test_both_pages_name_the_same_installs():
    """Not the same order of prose — the same set of commands.

    A command on one page and not the other is a reader told to do something
    the other reader is not, about one upgrade.
    """
    front, alias = set(installs(FRONT)), set(installs(ALIAS))
    # Non-empty first: two pages that give no commands at all are equal, and
    # this assertion passed on them.
    assert front, "the front page gives no install command"
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
        # The clause, not the word. `ordinary` appears on the front page 116
        # lines earlier, about the archive format — so rewriting the upgrade
        # sentence entirely left this green while its message claimed otherwise.
        assert "is the upgrade, and it is now an ordinary" in text, (
            f"{page.name} names the upgrade and does not say what it is now")


def test_neither_page_says_the_trap_is_gone():
    """What went away is the overlap this project created, not the shape of the
    failure. A page that says otherwise is selling a guarantee nobody has: an
    installation that takes half the upgrade still has old rules in it, and both
    pages have to say so."""
    for page in (FRONT, ALIAS):
        text = prose(page)
        # A blacklist cannot bound what a page might claim -- "no longer any
        # way" and "cannot recur" walk straight past the one that used to be
        # here, and a review wrote a passing sentence to prove it. What is
        # asked instead is that the caveat is present and says what it says.
        assert "takes half the upgrade still has old rules in it" in text, (
            f"{page.name} does not tell the reader what a half-taken upgrade "
            f"leaves them with. `half` alone is not that sentence: it appears "
            f"in `half-moved`, about the pin this release removed.")


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


def test_a_page_that_names_the_extra_says_how_to_run_it():
    """`pip install "vdi2770[validate]"` installs no command at all.

    Measured on a clean environment: the whole tool arrives and the scripts
    directory holds the parser's three and nothing of ours. The console script
    is declared by the alias distribution, which this install deliberately does
    not pull in — and that is the right owner, because it is the owner that
    does not change across the upgrade. If the engine declared the command
    instead, then upgrading from 0.7 would have pip writing that file from one
    distribution while removing it from another's record, and which one goes
    last decides whether the command survives. That is the failure this release
    exists to remove.

    So the price is that this install has one door, `python -m
    vdi2770.validate`, and a page that gives the install without naming it
    hands the reader a tool they cannot start.
    """
    for page in (FRONT, ALIAS):
        if "vdi2770[validate]" not in installs(page):
            continue
        # The command, with something to run it on. The bare module path also
        # appears where the page lists what is stable, so asking for it alone
        # was satisfied by a sentence a hundred lines away -- measured: deleting
        # the instruction next to the install left this green. A page that
        # names the door in a list of guarantees has still not told anybody how
        # to open it.
        assert "python -m vdi2770.validate check" in prose(page), (
            f"{page.name} tells the reader to install `vdi2770[validate]` and "
            f"never says how to run it. That install carries no command — the "
            f"console script belongs to the other distribution — so the reader "
            f"is left with a tool and no way to start it.")
