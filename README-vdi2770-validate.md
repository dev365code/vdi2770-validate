# vdi2770-validate

**This is the old import name for a tool that now lives in
[`vdi2770`](https://pypi.org/project/vdi2770/), and it goes on working.**

```bash
pip install vdi2770-validate
```

That command means what it has always meant: it brings the whole tool, the
`vdi2770-validate` command, and everything written against
`import vdi2770_validate`. If that is what you came for, you are done — the
[front page](https://github.com/dev365code/vdi2770-validate#readme) is where the
tool is documented.

## What this distribution actually is

Two lines. They make `vdi2770_validate` the same object as `vdi2770.validate`,
so the old name resolves to the code rather than to a copy of it: submodules,
deep submodules, `python -m vdi2770_validate` and the console script all keep
working, and a module imported through the old path still carries the old name.

It asks for `vdi2770[validate]>=0.8.0.dev0` — its own version as the floor, so
installing it can never leave you an engine older than the one it stands for.

## What changed in 0.8

The readers and the rules were two distributions that had to match, and this one
named the reader with an exact pin so the pair could not be half-moved. They are
one distribution now, and the pin has nothing left to hold together.

**`pip install -U vdi2770-validate` is the upgrade, and it is now an ordinary
one.** On an installation of 0.7 that same command used to leave a tool that
could not run: the two distributions shared file paths, so installing one wrote
files the other's record still listed, and removing either took them away. There
are no shared paths any more — a gate compares the built wheels against the ones
already published to say so — and the upgrade ends with everything at the new
version.

## What has not gone away

Saying otherwise would be untrue, so:

- An installation that takes half the upgrade still has old rules in it. Move
  the engine forward and leave this package behind, and this package keeps its
  own command and goes on judging with its own rules — honestly, under its own
  version number, which is what its reports say.
- If the halves that are loaded disagree about which release they are, the tool
  **refuses to judge** rather than sign a verdict it cannot account for: exit 3,
  on a line beginning `vdi2770-validate: INSTALLATION`. That is not a verdict on
  any container.
- A pickle written through the **new** module path names `vdi2770.validate.…`,
  and code that only has the old release cannot read it. No aliasing technique
  removes that.

## If you only want the readers

```bash
pip install vdi2770
```

opens a container, refuses what it should refuse, and hands back a typed model
with a line number on every node. It decides nothing and has no dependencies.
`pip install "vdi2770[validate]"` adds the schema parser and the rules — but no
command: run that one as `python -m vdi2770.validate check YOUR-CONTAINER.zip`.
The `vdi2770-validate` executable is installed by the distribution of that name,
which is this one, and it stays there so that no upgrade has two distributions
taking turns owning the same file.

Apache-2.0. Source, issues and the full documentation:
<https://github.com/dev365code/vdi2770-validate>.
