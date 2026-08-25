import sys

# `_run`, not `main`: the console handling lives there. Two entry points existed
# and only one of them got it, so `python -m vdi2770_validate` kept the crash
# that `vdi2770-validate` no longer had — one fix, applied to one of two doors.
from .cli import _run

sys.exit(_run())
