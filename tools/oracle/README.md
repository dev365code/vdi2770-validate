# The differential oracle

The MIT-licensed reference implementation
([DigitalDataChainConsortium/vdi2770](https://github.com/DigitalDataChainConsortium/vdi2770))
is the only other thing that reads these containers and says what is wrong with
them. Comparing against it is the closest this project gets to an external check,
so `docs/divergences.md` may not claim "the reference does X" without it.

It is **not** part of `make check`: it needs a JDK, Maven, network access to
Maven Central, and a checkout of another project. What is checked in instead is
the *result* — `docs/oracle-sweep.json` — plus everything needed to regenerate it.

## Regenerating

```
brew install openjdk@17            # or any JDK 17
git clone https://github.com/DigitalDataChainConsortium/vdi2770.git /tmp/ref
git -C /tmp/ref checkout e47c13c1925abc3ed4698cb5ed9e73b5eb544353
python tools/capture_oracle.py --reference /tmp/ref
```

`capture_oracle.py --check` re-runs it and fails if the verdicts moved.

## Two things that will bite you

**Pin the locale.** The implementation selects its message bundle from
`Locale.getDefault()`. On a machine set to German or Chinese you get different
strings and the codes shift with them. The capture pins `en_US`/UTF-8/UTC.

**Do not use its command line.** `Application` registers `-report` with
`Option.builder(...).hasArg().optionalArg(false)`, which under commons-cli 1.6.0
resolves to an option that takes no argument; the CLI then dereferences a null
path. `Sweep.java` calls `ContainerValidator` directly, which also yields the
`Report` tree instead of indented stdout.

`Sweep.java` is our code (Apache-2.0) and imports theirs (MIT). It is not
distributed in either wheel — see `MANIFEST.in`.
