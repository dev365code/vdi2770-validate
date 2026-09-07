import sys

# `entry.run`, not `cli._run`: the check that the two halves agree has to happen
# before anything is imported that needs the reader, and `cli` is not that.
# Two entry points existed and only one of them got the console handling once;
# the same shape, one layer up, is why this file names what the console script
# names rather than repeating it.
from .entry import run

sys.exit(run())
