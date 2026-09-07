"""`python -m vdi2770_validate`, which has to be a real module.

`runpy` reads `__spec__` off whatever it finds under this name, and a module
fabricated at run time has none — the ValueError that follows becomes an exit of
1, which is this tool's code for *a container has findings*, about a container
nobody looked at. So this file exists, and `.entry` is whatever the package
decided it should be: the door on a healthy installation, and the refusal on one
whose engine is older than this alias stands for.
"""
import sys

from .entry import run

sys.exit(run())
