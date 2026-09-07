"""One rule for both suites: a test is named, not quoted.

`pytest.mark.parametrize` builds each case's id out of the parameter values, and
a `bytes` value goes in escaped and entire. Three cases here were handed whole
PDFs, so their ids were 12,000, 66,000 and 70,000 characters of document.

Unreadable in a log everywhere. Fatal on one platform: pytest writes the current
id into `PYTEST_CURRENT_TEST`, and Windows refuses an environment variable over
32767 characters, so those cases passed and then failed in teardown with a
`ValueError` out of `os.environ`. A suite that had been green for weeks went red
the hour a Windows row was added to CI.

Fixed here rather than case by case. Every one of them already had a readable
name in another parameter; what they lacked was a rule saying a document is not
one. Putting `ids=` on each decorator would fix the three that exist and none of
the ones written next week.

This file sits at the root because that is the only place a hook reaches both
`tests/` and `packages/vdi2770/tests/` — two suites, one rule.
"""


def pytest_make_parametrize_id(config, val, argname):
    """What a parameter contributes to a case's name.

    Returning `None` leaves pytest's own answer alone, which is right for the
    small scalars it renders well. A block of bytes is named by what it is: how
    much of it there was.
    """
    if isinstance(val, (bytes, bytearray)):
        return f"{argname}<{len(val)}B>"
    if isinstance(val, str) and len(val) > 40:
        return f"{argname}<{len(val)} chars>"
    return None
