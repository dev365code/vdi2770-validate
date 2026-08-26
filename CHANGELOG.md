# Changelog

## 0.7.0 — 2026-08-25

Things that were true of the code and not of what the project said about it,
plus the guards that make each one say so next time. The count that used to open
this section was written when it held six; it holds seventy now, and a number
nobody re-derives is the kind of claim the rest of these entries are about.


The trailer scan had been repaired four times, and each repair fixed the shape
in front of it rather than the class of shape, so the next shape was always
waiting. This one repairs the class — and then the class repair turned out to
have a class of its own.

- **The trailer scan is one pass that knows PDF, with a budget on each axis of
  its cost.** A whole-file token search reported any PDF that mentioned
  `/Encrypt`; a fixed window missed one a long `/ID` pushed past it; a brace walk
  counted `<<` inside a string; a brace walk that skipped strings still ran the
  token search over raw bytes, so `/Encrypt` in a *comment* counted. And every
  per-keyword bound multiplied by however many `trailer` keywords a sender wrote
  — 16,000 bare ones cost 135 s, and when that was fixed, 8,000 that *open* a
  dictionary cost 28 s from a 20 KB archive. Structure and token are now found in
  the same pass, so nothing downstream can disagree with the endpoint.
- **And the budget that stopped that then produced a silent miss.** Replacing the
  per-keyword bound with one total for the whole file was the same mistake in the
  other direction: an ordinary earlier trailer carrying a long `/ID` or `/Info`
  spent the budget, the authoritative trailer of an incrementally updated file was
  never scanned, and a genuinely encrypted PDF read as clean — after which the
  report told the producer to *export it as PDF/A*. Cost has two axes and one
  bound cannot hold both. `MAX_TRAILER_SCAN` is again per dictionary;
  `MAX_TRAILERS` bounds how many are read, **from the end**, because an
  incremental update appends and the newest trailer is the one that counts.
  Worst case is 4 MiB walked, **0.07 s**; the ordinary case is **0.008 s** and
  does not move when the input grows fivefold.
- **Two more misses in the same scan, both the same asymmetry.** Comments were
  skipped inside the dictionary but not between `trailer` and the `<<`, so a file
  that wrote one there had its dictionary declared absent. And the token was
  matched at any depth, so `/Encrypt` as an array element or a nested
  dictionary's value read as the trailer's encryption reference — a false alarm
  telling a producer to unprotect a file that was never protected. The token is
  now a key only where a key can be, and the two comment skips are one function,
  so there is no longer a door to forget. Twenty-two shapes are pinned,
  including the real encrypted PDF in the corpus.
- **And the attributes hung off them, which was the axis nobody charged.** The
  parse is linear in attributes; the schema check afterwards is **quadratic in
  how many sit on a single element**. 12,000 of them, in a **27 KiB** archive,
  cost **13.6 s**, and a 3 MB one ran past two minutes — the denial of service
  every other budget in this reader exists to refuse, reached along the one axis
  that had no name. Two bounds again, because one would not have held:
  `MAX_ATTRIBUTES_PER_ELEMENT` flattens the quadratic and `MAX_ATTRIBUTES` stops
  a sender paying the flattened cost once per element. **0.04 s** and **0.53 s**
  now. Across every `VDI2770_*.xml` in this repository's corpus the worst
  element carries three attributes and the worst document fifty-one — so the
  per-element cap sits 43× above the worst element seen, and the total 1,900×
  above the worst document. (Naming the set matters: counting the loose XML
  files beside the containers as well gives 74, and a number whose subject is
  unstated cannot be re-derived from the sentence that states it.)
- **One path that blocks no longer stops the sweep.** `cli` wraps each path in
  `try/except` so a bad one cannot stop the rest — but a hang is not an
  exception. Opening a FIFO with no writer waits forever, so a single named pipe
  in a supplier drop folder meant the run produced a verdict on *nothing*. A
  directory and a dead symlink were already refused by raising; the third shape
  is opened without blocking instead. The first attempt refused everything
  `S_ISREG` said no to, which also refused `check <(unzip -p …)` and
  `… | check /dev/stdin` — both of which worked, and neither of which is a pipe
  without a writer. `O_NONBLOCK` tells the two apart, and the Unix-only import
  it needs is behind a platform test, because the first version of that made the
  package fail to import on Windows — in the release whose headline fix is the
  Windows console.
- **A name the archive stores twice is told to remove the repeat.** `F1` said the
  bytes could not be read — they read fine — and the remedy was "re-create the
  archive and send it again", which, followed exactly, produces the same archive
  and the same finding. The right words were already in `files.py`, behind a test
  against a set that is always empty: the reader refuses *both* entries of a
  repeated name, so the name never reaches `file_names`. The branch reads the
  refusal now, which is where the reader put the answer.
- **`Z9` and `Z13` name one folder one way.** They were spelling the same place
  `AB393/` and `./AB393/` in the same report. What the folder list *returns*
  still keeps the archive's prefix, because `F2` suppression matches member
  names against it; the sentence is what changed.
- **The reader now has to ship before the validator that pins it.** The two
  packages release from one repository and the validator depends on the reader
  with `~=`. `release.yml` installs the reader from the working tree, so nothing
  in the gate ever asks an index whether that version exists, and `python -m
  build` does not resolve runtime dependencies at all — so tagging `v*` before
  `sdk-v*` built green, published, and left `vdi2770-validate` permanently
  unresolvable under a number PyPI will not let anyone reuse. The constraint had
  lived in a test docstring; the test that names it asserted that `API.json`
  exists, which it always does. It is a step in the workflow now, and a test
  fails if the workflow loses it.
- **`--check-swept` can fail.** The gate that stands between a release and
  published divergence counts excluding containers nobody swept had no test at
  all: both its comparison and the canary beside it survived being neutered
  against the whole suite. Seven cases now, one per way the recording can lie —
  including a sweep of nothing over nothing, which every other case passes.
- **The record's own published-version guard can fail.** Its test never ran the
  tool. It read `API.json`, called `_at_tag`, skipped when the tag was absent —
  which it is for every unreleased version, so always — and asserted its own
  premise; replacing the guard with `if False:` left the suite green. And the
  `--first` guard beside it could not run at all: `_tags()` either raises or
  returns a non-empty set, so the line above always answered first. A guard that
  cannot run is a comment that looks like code, and it is gone.
- **CI fetches tags, and a skip looks like a skip.** `ci.yml` was a default
  checkout — `--depth 1 --no-tags` — so the two assertions that compare the tree
  against `sdk-v*` skipped on every pull request. One of them was not even
  skipping: it `return`ed, which reports as a pass, on the condition that holds
  for every unreleased version.
- **`make oracle-fully-swept` works on a fresh clone.** The fixtures it compares
  against are generated and not committed, so on a clean checkout the target
  failed and blamed the sweep for twenty-seven containers nobody had built. It
  passed in the release workflow only because `make check` happens to run
  `fixtures` first, which is a coincidence rather than a dependency. Now it is
  a dependency.
- **`X6` reports what it measures.** It said "this read has already built
  *n* elements" for a number that is a charge taken from the markup *before* the
  parse — deliberately, because refusing a document is the expensive path and
  counting the tree that came back charged nothing for it. The two readings
  differ by five orders of magnitude in exactly the case that trips the rule: a
  1 KB archive whose read built about six elements reported 520,007. The number
  was right and the noun was wrong, and a finding that names the wrong thing
  sends its reader to look for a document that does not exist.
- **One pinned PDF shape was pinning nothing.** `<< /ID [<2f456e...>] >>` was
  listed as the case that proves the hex-string branch matters; the bytes are
  hex, so no scanner finds `/Encrypt` in them with the branch or without it, and
  removing the branch left the parametrised test green. What the branch actually
  protects is `<< /X <41>> /Encrypt 4 0 R >>`, where the string's `>` abuts the
  dictionary's — without it the dictionary closes a byte early and the
  encryption reference is never seen.
- **The scan returns one thing, and says what it looks for.**
  `_scan_dictionary` still handed back how many bytes it had read, so a caller
  could spend one budget across a whole file — which is exactly what let an
  ordinary earlier trailer hide the encrypted one behind it. Nothing has read
  that count since, and its docstring still described the design that produced
  the bug, and still claimed the key was matched "at depth one or more" after
  that stopped being true.
- **Both packages advertise the Python they are tested on.** CI runs 3.9, 3.12
  and 3.13; the classifiers listed 3.9 and 3.13, so PyPI under-reported the
  supported range by the interpreter the release workflow actually uses. 3.10
  and 3.11 are deliberately still absent: nothing runs them, and a classifier is
  a promise to whoever reads it before installing.
- **The offline promise is guarded by something the tool cannot swallow.** The
  network guard raised `AssertionError`; the schema loader and the rule runner
  both wrap their work in `except Exception` and turn what they catch into a
  finding, which is right for hostile input and fatal here — a fetch during
  schema compilation was caught, became `X0` on both sides of the comparison,
  and the test passed. It raises a `BaseException` now, and fails in both
  directions when the compile reaches for a socket or a URL. The compile also
  happens *inside* the guard now: the schema is compiled once and held, so in a
  full-suite run this test had been measuring a cache hit that some earlier test
  had filled.
- **One decision, said once.** The runner decided "a container we declined to
  model gets no schema check" in two places and two spellings — `not modelled`
  on one line, `tree is not None` three lines down. Removing the first changed
  nothing, which is how it was found; two spellings of one decision are two
  things to keep in step, and this file has already paid for that. The live one
  now has a test that counts the calls, so it is a decision something notices.
- **`_is_encrypted`'s summary claimed more than it delivers.** It said "an
  `/Encrypt` key"; the scan requires the key's value to be an indirect
  reference, which is the only form ISO 32000-1 permits for the encryption
  dictionary. The behaviour is right; the sentence was loose, and `docs/scope.md`
  had always been the honest one.
- **The last stopwatch assertion is a counted one.** `elapsed < 5` on a
  16,000-error document failed four runs in six under load, and it was not
  measuring what it defended: the cost it exists for was `_resolve` rebuilding
  the whole sibling list once per error, 38% of the 29 seconds that prompted
  this area. It counts the rebuilds now and compares two sizes rather than
  holding each under a ceiling — what matters is that the number does not grow
  with the error count. Three timed assertions in this project have flaked in
  one week; every one of them has been replaced by a count of the thing that
  actually costs.
- **The trailer scan follows `startxref` instead of guessing where to look.**
  Repaired again, and this time not by another guess: reading the *last*
  sixty-four dictionaries was pushable by sixty-four occurrences of `%trailer`
  appended after `%%EOF` — 640 bytes a conformant reader ignores — and an
  encrypted PDF came back clean, with `P3` (*produce the file as PDF/A*) in
  place of `P2` (*remove the protection*). Every window is pushable, because a
  window is a guess. `startxref` is the one offset the file itself declares, and
  all fifty-five PDFs in this repository's corpus carry one; the token scan
  stays as the fallback for a file damaged enough to have none. Two costs came
  down with it: comments were scanned twice per comment, once for each newline
  byte, so sixty-four dictionaries of them cost **11.6 s** and now cost
  **0.9 s** of CPU; and the match offsets were built into a list and then
  sliced, so six million tokens in a 68 KiB archive held **337 MiB** of offsets
  nobody would look at.
- **Two rules stopped calling one file two things.** `names.py` exists because
  "every place that compares a name has to reconcile them the *same* way" — and
  it reconciled Unicode composition and nothing else, while three other places
  deliberately dropped `.` segments. So `./B.pdf` was `F1` *declared but not in
  the archive* and `F2` *in the container but not named in the metadata*, in one
  report, about one file — and its PDF was never scanned, because the resolution
  that failed is the one the PDF rules use to find it. The path normalisation
  now lives in `names.py` with the composition, which is the layer everything
  else already goes through.
- **`F2`'s folder check stopped being quadratic.** It asked, once per undeclared
  member, whether any unopened folder was a prefix of it — with both sides
  bounded only by the member cap. Four thousand of each, in a **900 KiB**
  archive, cost **24 seconds**, past every budget the reader has because not one
  of them measures this. A path has at most `MAX_FOLDER_DEPTH` ancestors, which
  is the bound `Z9` already puts on the same walk one file away. **0.8 s** now,
  and flat in the number of folders.
- **Two doors, one fix, applied to one of them.** The console script and
  `python -m vdi2770_validate` are separate entry points; the console handling
  went into the first and the second kept the crash. Both go through `_run` now.
- **A refusal about an unreleased version said something untrue, and its remedy
  cost a version number.** The record's `--check` told the reader *"whoever
  installs 0.6.2 from PyPI does not get this — bump the version"* about a version
  that was never published. Nobody can install it, so nobody is missing anything,
  and following the remedy would have burned a number to repair a problem that
  did not exist. `--write` had the distinction right all along; only the sentence
  explaining the refusal did not. It is two sentences now, because the repair is
  genuinely different: a published version cannot take back what it shipped, and
  an unpublished one has shipped nothing.
- **A publishing workflow asks the index before it builds.** Both fire on
  `push: tags`, and a *forced* tag update emits that event exactly as a new tag
  does — so re-pointing an old tag walks a days-old tree through the gate and
  then asks the index to accept a filename it already holds. The answer is a
  rejection and a failed run against the publishing environment. One HTTP
  request up front turns that into a clean stop. It is also the only network
  call in this repository, and deliberately so: the index is the only thing that
  knows what has been published.
- **A gate's failure message no longer fails.** The check that keeps a step
  running in the right directory formatted a `str` as a match object, so a real
  failure printed a type error instead of the workflow, the step and the missing
  line. It reported red, which is why it survived; it just could not say why.
- **Numbers that could not be re-derived, re-derived.** Three published
  measurements were wrong and one was right but unusable. The reader's README —
  which is the front page of a package people install — said one character
  reference repeated cost 287 MB from a 4.2 KiB archive; measured in a fresh
  process, the whole tool holds **48 MB** on that archive and **23 MB** with the
  ceiling. `docs/scope.md` said a crafted file could make one rule true two
  hundred thousand times; the element budget refuses the document first, so the
  real ceiling is **99,997** and the page now says so — and the gate that guards
  that page derives the number instead of trusting it, which is what it did for
  six of the page's other limits and not for the one that drifted. The attribute
  caps were called "two orders of magnitude above anything a delivery can reach";
  they are **43×** the worst element seen and **1,900×** the worst document, which
  is one order and three, not two and two.
  The fourth was the interesting one. "The corpus's worst document carries
  fifty-one attributes" is *true* — over every `VDI2770_*.xml`. Counting the loose
  XML beside the containers gives 74. Both numbers are honest and the sentence
  did not say which set it meant, so it could not be checked. Naming the set was
  the repair; changing the number would have been a mistake.
- **A gate that starts Python leaves no bytecode.** `__pycache__` is not where it
  goes on every machine: `sys.pycache_prefix` can put it outside the tree, where
  nothing cleans it and where a same-size restore inside one second leaves a
  `.pyc` CPython still considers valid. That produced a `make check` failure
  naming a budget as moved while the source on disk was correct, and 73,000 cache
  files outside the tree. The mutation table already set this; the sdist, wheel
  and standalone gates start Python the same way and did not.
- **Text arriving in pieces has a ceiling.** The tree had a bound on elements and
  none on how many times the parser handed back character data. 450,000 `&#120;`
  references — a **4.1 KiB** archive — held **48 MB**, because a byte count is not
  the cost: each reference decodes to one character while the callback that
  carries it is a whole Python object. `MAX_TEXT_PIECES` counts the callbacks,
  which is where the cost is: **23 MB** on the same input.
- **Two rules stopped contradicting each other about the same folder.** Writers
  mix `./` prefixes and doubled slashes inside one archive. `Z13` decided a
  folder existed after dropping `.` segments, and `files.py` suppressed `F2` by
  matching the archive's raw spelling — so a file could be reported undeclared in
  the same report that said its folder had never been opened. One `folder_path`
  now makes the decision for both; a finding still shows the archive's own
  spelling, because a name a user cannot find in their ZIP listing is not a
  report they can act on.
- **The record is checked against its tag unconditionally.** That check was
  guarded by "is the recorded version published?" — a value the editor of the
  file chooses. Point `version` at a tag that does not exist and the branch never
  ran at all, so the compatibility check was handed a version out of thin air and
  waved a removal through as a patch; `--write` then overwrote the field, so the
  committed diff showed an ordinary version bump.
- **The bundled schema is compiled once.** `validate` runs per container and
  rebuilt it every time. A legitimate delivery of 900 document containers — a
  93 MB archive — takes **3.3 s** now and **11.2 s** with the cache removed, so
  the recompilation was about eight of those seconds. (The figure first recorded
  here was *21 of 26*, measured before the rest of this release cut the other
  costs down; it does not reproduce against this tree, and a number a reader
  cannot re-derive from the entry is not worth keeping. These two do: remove the
  `lru_cache` and measure the same archive.) Only the success is cached — a
  broken installation must not answer from memory.
- **Two gates could not fail, for the same reason.** The harness in the API
  record's tests committed nothing before tagging, so every tag it made pointed
  at an empty tree and `_at_tag` returned `None` for every test in the file: the
  comparison that matters — "the baseline is not what its tag published" — was
  never exercised, and weakening it to `is None` survived the suite.


The suppression added above silenced findings that never depended on the thing
being suppressed.

- **Spending the budget silenced a path-traversal member.** Not judging a
  container whose metadata we declined to model threw out the rules that never
  read the model: `r_container.check` opens by turning the reader's own defects
  into findings — `Z1`, `Z2`, **`Z4`**, `Z5`, `Z6`, `Z10`, `Z12` — and only
  `Z11` and `Z3`'s payload test touch `declared`. So an archive with
  `../../etc/evil.pdf` reported `Z4` when checked alone and **nothing** when it
  sat behind a sibling that spent the budget, with `X6` — `about: tool` — the
  only substitute. A CI gate filtering the tool axis saw no container finding for
  the subtree. From a **969-byte** archive. Worse: a container with no metadata
  of its own, under a parent whose metadata was skipped, emitted nothing at all
  and was absent from the report, the summary and the JSON. `None` now says
  "unknown" to the two rules that read the model; everything else fires as it
  would alone.
- **A version is a promise about what you get.** The fingerprint watches the
  reader's public *surface*, so two repairs to `pdfread._is_encrypted` — a scan
  that cost 135 s on a 1.5 KB archive, and one that called a plain PDF encrypted
  — left it green at 0.6.1 without touching a name in `__all__`. A user
  installing this validator would have got the reader on PyPI: the one without
  the repairs, which it was never tested against. A gate compares the reader's
  source against its own published tag now, and the reader is 0.6.2.


Four defects, three of them introduced by the repairs that came before them. A
repair is not finished when it stops the shape that was reported.

- **A refused parse is the expensive one, and it was charged nothing.** The tree
  budget counted the tree that came back — so metadata *over* the per-document
  cap built a hundred thousand nodes, raised, and cost the counter zero. A
  thousand of those is a 280 KiB archive that took **51 seconds** with the
  counter reading 2 against a budget of 500,000. Charged before the parse now,
  from the bytes: **6.7 s**, and the nine-hundred-document handover still passes.
- **A container we declined to model was then judged.** Skipping the parse leaves
  `declared` empty, and the rules that read it said things about the sender: a
  conforming document container declaring a `.zip` payload came back with `Z11`
  and `Z3`, both errors, both `about: container`, beside the `X6` saying this
  tool had not looked. Checked alone it is clean — so the verdict depended on
  what else was in the sweep. Unknown is not "declares nothing", and it
  propagates to the children.
- **Balancing braces re-opened both holes it closed.** `<<` inside a PDF string
  or comment counted as an opening, so `(value <<redacted)` ran the scan to its
  cap and found an `/Encrypt` that a *comment* mentioned; and `>>` inside a
  string ended a real dictionary early, hiding a genuine one. A `trailer`
  keyword with no dictionary after it walked the full 64 KiB cap, so 16,000 of
  them in a 128 KB member cost **135 seconds** — from a 1.5 KB archive. Now
  0.023 s, and strings, hex strings and comments are skipped.
- **Dropping `.` segments broke what `Z13` exists to enable.** `files.py`
  suppresses `F2` inside a folder this tool did not open by matching the
  archive's own member names against that prefix, and normalising the prefix
  made it match nothing — so the files in a folder the same report calls
  unopened were accused of being undeclared. The decision drops `.`; the value
  keeps the archive's spelling.
- **The release gate failed open where it could not see.** "No such tag" and
  "this checkout has no tags" were the same answer, and the second turns every
  judgement in `api_fingerprint.py` off: in a `--depth 1 --no-tags` clone —
  which is what `actions/checkout` gives you by default — a moved surface
  recorded cleanly under a version live on PyPI with the whole gate green. It
  refuses now, and `release.yml` fetches the tags it judges by. Three more holes
  went with it: recording over a version that is itself published, `--first`
  against a package with releases behind it, and a version going backwards.
- **Four gates could not fail.** The mutation row for the new exception gate
  killed a different test; the schema-budget test measured rendered findings
  rather than errors drawn from the generator, so it passed with the bound
  deleted; nothing asserted the release workflows run `make oracle-fully-swept`;
  and one comment line inside a `defaults:` block made the working-directory
  check pass vacuously over the failure it exists to prevent.
- **`--check-swept` never looked at the repository.** It read the recorded file's
  own key set, so a sweep missing a container answered "complete" and an empty
  one answered "every one of 0 containers has a reference verdict".


Review of this release candidate found one thing that had to
stop it and a dozen that had to be fixed before it went out. What follows is what
they found, not a summary written after the fact.

- **Bounding one document did not bound the tree of them.** `MAX_ELEMENTS` caps
  the elements in one metadata file; nothing capped the sum. A documentation
  container holding forty document containers, each with metadata just under that
  cap, is **12 KiB** on disk and cost **74 seconds** of CPU. Memory stays flat —
  the trees are built and dropped one at a time — so every budget the reader has
  let it through. `MAX_TOTAL_ELEMENTS` bounds the read: the same archive costs
  **12 s**, and a legitimate nine-hundred-document handover of real corpus
  metadata still passes untouched at 17.8 s. The attacker cannot buy more work
  than a real customer.
- **A malformed encoding declaration was reported as our crash.** expat resolves
  `encoding="XXXX"` through the codec registry and raises `LookupError`, which is
  not an `ExpatError` and escaped the parser — so the report said *"a check in
  this tool raised an error"*, `about: tool`, and told the sender nothing in
  their container needed changing. It is `X1` now, `about: container`, naming the
  encoding the document declared.
- **A window is the wrong shape for a dictionary.** `_is_encrypted` read 4 KB
  after each `trailer` keyword, and a legal trailer whose `/ID` strings are long
  pushes `/Encrypt` past any window you pick. Such a file read as *not*
  encrypted, and the report then told the producer to re-export as PDF/A — a
  remedy for a different problem, on a document this tool could not open. It
  reads to where the dictionary closes.
- **`Z13` called a root-level file a folder.** `./VDI2770_Metadata.xml` **is** at
  the root; some writers spell it that way. `Z9` learned to skip a `.` segment
  this cycle and the reader grew a `path-prefixed` near-miss kind for it — this
  was the third place and it was missed, so a conforming container got an error
  saying this tool had not looked inside something it had read.
- **`XmlTooLarge` could not be caught by name.** Raised at the reader's boundary
  and left out of `__all__`, so the validator was reduced to comparing
  `__class__.__name__` and the release fingerprint could not see it at all — it
  could have been renamed in a patch release with the gate green. Exported, and a
  new gate walks every exception the package raises and fails if one of them
  cannot be caught by name.
- **The release gate refused every release.** Once `sdk-v0.6.0` existed, the
  branch that noticed "the recorded version is published and the package has
  moved past it" returned 1 with nowhere to go — a wall across the one operation
  a release performs. It judges the move now, and takes its evidence from the tag
  rather than from the `version` field of the file it is judging, because that
  field is editable and pointing it at some tag that exists is exactly how you
  make the tool compare against a past that never was.
- **Two gates could not fail, and one flaked.** The layering check for a second
  definition of Unicode canonical form was a `grep`, so writing the function's
  name in a comment counted as a definition; it reads the syntax now. The
  changelog helper raised `ValueError` on a file with no sections, missed a
  heading on the first line, and ended a section at a `## ` inside a code fence.
  And two budget tests asserted on `time.monotonic()` and went red on a loaded
  machine — they count what the budget bounds instead. Others still measure the
  clock, deliberately: an amplification test has no meaning without one.
- **Packaging.** An sdist built in a tree somebody had run the suite in carried
  pytest's cache, because `recursive-include packages ... *.md` matches
  `.pytest_cache/README.md` — gitignored is not excluded. Six links in the README
  are relative, and PyPI does not rewrite them, so they 404 on the project page.
  The root package declared no specific Python versions while the reader declared
  two.

### Two new rule ids, and one changed verdict

- **`Z13` — documents delivered as folders.** A folder holding
  `VDI2770_Metadata.xml` is a document container that was not zipped. This tool
  opens `.zip` members and nothing else, so everything inside went unchecked —
  and the report said nothing, which told the reader it had passed. It is an
  **error**, `about: tool`: the reference implementation does read such folders,
  so this is our limit rather than a fault in the delivery. If you deliver that
  way you will see a new error id on upgrade, and `F2`/`Z8` no longer fire on
  the files inside those folders, because accusing them of being undeclared was
  the false positive that hid this.
- **`X6` — metadata this tool did not build a model of.** New, `about: tool`,
  an error. See the element budgets below.

- **The sweep is complete, and it runs where a JVM already is.** Two containers
  had never been through the reference implementation, because the reference half
  needs a JDK, Maven and a checkout of another project — three shell lines in a
  README that only ever ran on a maintainer's laptop. It is a workflow now: a
  pinned JDK, the reference at the commit the sweep records, the result uploaded
  for a human to read. The first run filled both in, and settled something no
  local run could — the other 44 verdicts came back **byte-identical** to the
  ones captured on a laptop, which is the property the whole comparison rests on.
  The reference reports errors on the over-the-cap fixture too, for its own
  reasons; both tools reject that container.
- **A release cannot publish counts that exclude something.** `make
  oracle-fully-swept` asks whether every container has a reference verdict, reads
  the recorded file and nothing else — a release must not depend on Maven Central
  being reachable — and both release workflows run it. A container may sit
  unswept while the divergence counts exclude it; that stops being acceptable the
  moment those counts are published, which is what a release does.

- **An empty column in the oracle sweep meant "we never asked", and the page read
  it as "it reported nothing".** `docs/divergences.md` derives its disagreement
  counts from `oracle-sweep.json`, and two containers postdate the recorded run —
  the reference half needs a JDK and the pinned checkout, so a fixture added
  afterwards waits for the next full sweep. One of them errors on our side, so it
  was counted as a container where *"we report an error and it does not"*: a
  disagreement with a tool that has never seen the file. The counts exclude
  unswept containers now, the page names any that are outstanding, and the gate derives
  both numbers — how many exist and how many were measured — instead of one
  doing the work of both.

- **The bytes were bounded and the tree built out of them was not.** A metadata
  member of 7.98 MB — under the compression-ratio guard's size floor, so it was
  never ratio-checked, and under the 16 MB metadata cap — holding 1.14 million
  nested elements compresses to a **115 KB archive** and drove this process to
  **952 MB**, measured. The reader's own first paragraph says an untrusted
  archive does not get to decide how much memory we spend. `xmlread.parse` caps
  the element count now: the same archive costs **101 MB**. Deliberately no depth
  limit — 99,999 nested elements parse in 0.11 s once the count is bounded, and a
  depth limit would take a real limit away from the caller by refusing documents
  the schema checker gives up on and reports honestly.
- **A document this tool would not model is not a malformed document.** Bounding
  the tree earned the same archive a verdict that was false the other way:
  *"The metadata file is not well-formed XML"*, because every parse error that
  was not an entity refusal mapped to `X1`. New rule **`X6`**, `about: tool`:
  the file is well-formed and we declined to build objects out of it.
- **A name that means two entries identifies neither.** Every refusal in the
  reader is recorded against a *name*, and `zipfile` resolves a duplicated name
  to the **last** entry — so the accepted member, the budget charge and the
  allow-list all came from the first while the bytes came from the second. A
  **505 KiB** archive whose second `d.zip` was 400 MB of zeros cost **1.25 GiB**
  while the report said that member had been refused for expanding 1028x. Both
  entries are refused now, once, under the new `ambiguous-name` defect kind,
  which `Z10` already had the sentence for. (The three figures first recorded
  here — 505 KiB, 1.25 GiB, 28.8 MB — cannot be reproduced from this
  description: how large the archive
  is depends entirely on how the 400 MB member compresses, which the sentence
  never said. The behaviour reproduces exactly — both entries refused, `Z10`
  with the `ambiguous-name` detail — and that is the claim that matters.)
- **A patch release of the reader was impossible.** `__version__` is in the
  reader's `__all__` and the fingerprint records its value, and the compatibility
  check is only ever consulted when the version moved — so `__version__` was in
  the changed set every time, the "nothing incompatible changed" branch was
  unreachable, and the verdict collapsed to "the minor must move, always". The
  release path was shut in both directions: `--check` failed until `--write`
  succeeded, and `--write` refused. Its unit test could not see it, because it
  was written against a two-entry synthetic surface with no `__version__` in it.
- **A finding about a name points at the name.** `M3`, `M4` and `M8` each object
  to one `ClassName` and each reported the line of the `DocumentClassification`
  around it — the same line for every name in the block, so the only thing
  telling "the German name is wrong" from "this tool does not check French" was
  the detail string. `M5` and `M7` had the same shape against `DocumentVersion`,
  which is the largest element in the file — languages, descriptions, parties,
  status and every digital file — so its opening line answered "where" with "in
  this document somewhere". (`vdi2770` 0.6.0, breaking: `Classification.names`
  holds `ClassName` objects and `DocumentVersion.languages` holds `Tagged`
  objects, each with its own `src`, where both were bare tuples;
  `DocumentVersion` gains `life_cycle_src`.)
- **The reader is behind the same door as everything else.** `_into` guards the
  rules and `_step` guards what feeds them; `zipread.read` and
  `zipread.member_bytes` sat outside both. The reader's contract is that it
  records a defect rather than raising — and it is a separately versioned
  package, so a crash there produced the exact failure those guards exist to
  prevent: a traceback naming internals, with the rest of the batch unchecked.
  `nfc` is deliberately left alone: it is `unicodedata.normalize` on a `str`, it
  cannot raise, and the validator calls it in four places besides — a wrapper on
  two of nine call sites is an inconsistency dressed as a guard.
- **Two subprocesses were measuring a different tree than the one under test.**
  `pytest`'s `pythonpath` does not cross a subprocess boundary, so `-m
  vdi2770_validate` in a child imported whatever was installed. On a dev box that
  is an editable install of the same checkout and the difference never shows;
  under `make mutations` and the sdist gate, which both run the suite from a
  *copy*, the child measured the original. A mutation to the CLI left the
  mutation table's own canary green in the copy it was judging.
- **The reader's own suite now holds the locations the reader publishes.**
  `ClassName.src`, `Tagged.src` and `life_cycle_src` are its public surface, and
  every test of them lived in the validator — while the sdist gate makes it
  literal that a packager building `vdi2770` alone runs that suite and nothing
  else. Pointing all three back at their parent element left it green.
- **Six numbers in prose, and the gates that make them derive.** The README gave
  a count of rules with a fixture pair and then called the odd one out by that
  very ordinal — the two cannot both be true — and the test pinning the sentence
  hard-coded the ordinal, off by one, so writing the correct one turned the
  build red. The reader README's opening snippet
  prints a list of `(domain, value)` pairs and its output block showed a bare
  one-tuple with the domain dropped — on the front page of the package whose
  own rule, test file and changelog entry are about identifiers being pairs.
  `make standalone` runs 56 files and the entry said 48. Seven rules fire because
  this tool declined and the entry said four. `docs/rules.md` called `obligation`
  "basis", while `rules.json` has a *different* field named `basis`. And the
  citation floor was `>= 12` against a real count of 22, so ten could vanish in
  silence. Each of those now derives from the thing it counts.
- **"CI runs exactly these targets" is proved in both directions.** Only one was:
  every `make check` command had to appear in the workflow, and nothing stopped
  CI growing a check nobody runs locally — or replacing one — with "exactly"
  still reading as proved.
- **A report for an archive that was never opened does not say the rest stands.**
  `X5`'s remedy ends *"Every other finding in this report still stands; only the
  named check did not run"* — true of one rule crashing among thirty, false of
  the container read, which every other check is downstream of. A user whose
  archive could not be opened got one finding and a sentence telling them the
  rest of the report held. `_step` now takes the remedy for steps whose failure
  the catalogue's sentence does not cover.
- **A failing test no longer deletes the fixtures.** The check that the fixture
  generator clears its own output directory planted its stray file in the real
  `tests/fixtures/` and put the tree back in a `finally` — which deleted the
  directory and rebuilt it *without checking whether the rebuild worked*. One
  failing assertion left 26 fixtures gone, the next test file unable to collect,
  and the run after that reporting four unrelated failures. It runs against a
  disposable copy of the generator now. A sweep for anything else in either suite
  that writes inside the repository found nothing.
- **A breaking change cannot ship as a patch release.** The API gate asked for
  *a* version bump. The validator pins the reader with `~=0.6.0`, which admits
  every 0.6.x, so a removal published as 0.6.1 would install itself on machines
  that asked for 0.6.0 — a mistake this project has already shipped once. The
  gate now distinguishes additions from removals and signature changes, and
  requires the minor to move for the latter.
- **The wheel carries the package and nothing else.** `check_wheel.py` asked
  whether everything in `src/` shipped and never the other direction, while
  NOTICE told readers the MIT-derived oracle evidence is in the sdist and in
  neither wheel. It was a claim with no gate; a `package-data` glob could have
  falsified it silently. NOTICE and THIRD_PARTY.md now say sdist where they said
  "neither package", which is what is true.
- **The mutation harness stopped poisoning the tree it measures.** One row runs
  the fixture generator under a mutation that deletes a fixture. Restoring the
  source file did not restore the fixtures, so the three rows after it failed
  their own baseline and were reported as "already fail before the mutation" —
  including the canary, which turns the whole run red.
- **Four gates were reading a shape rather than a value, or one file rather than
  all of them.** The reader README's defect-kind check scraped `Defect("…")` and
  saw eight of thirteen; the reference-corpus check would have degraded to a
  silent skip if its glob emptied; the folder-delivery check asked only that
  "some `about: tool` rule fired", which a crash report satisfies; and the
  citation check read `SECURITY.md` and no other document.


Three ways a small file could make this tool spend without limit. Each number
below is measured on this machine, before and after, on the same input.

- **A rule can no longer flood the report.** One rule fires once per element, so
  a 116 KB archive naming 99,000 identifiers produced 99,004 listed findings and
  tens of megabytes of output. The listing is now capped at 100 per (rule,
  container) — that input prints 101 findings, **26.3 KB of text, 74.8 KB of
  JSON, 179 MB** — and the report says
  `... 98900 more M10 findings in flood99.zip, counted below but not listed`,
  with `notListed` in the JSON. **The count is not capped**: the summary still
  reads 99,000 errors and the exit code is still 1, because a bounded listing
  must not become a quieter verdict. What memory remains is the parse tree, which
  is bounded: measured at 18x the metadata bytes, so 0.3 GB at
  `MAX_METADATA_BYTES` and 1.2 GB across the whole tree budget.
- **Decompression is now budgeted across the whole read.** Every individual
  member was under its cap while the total was not, so 40 inner containers could
  demand 19,200 MiB between them. `MAX_TOTAL_DECOMPRESSED` is 4 GiB across one
  `read()`; on exhaustion the sweep stops verifying, members are still listed,
  and `Z5` says why. That input now stops at 1.29 s.
- **Character data no longer accumulates quadratically.** `&#nnn;` forces one
  expat callback per reference and the parser appended to a string each time, so
  a 198 KB archive cost **60 s** for a clean verdict. Text is collected per open
  element and joined once: 200k/400k/800k references are **0.020 / 0.040 /
  0.079 s**, down from 0.317 / 1.085 / 4.724.

Three gates that ask what `make check` cannot ask of itself.

- **`make mutations`** takes every claim this project makes about a gate, breaks
  the thing that gate protects, and checks the gate notices — 59 rows, each
  naming the pytest selection or the tool that has to go red. The harness checks
  itself as hard as it checks the code: a row whose anchor no longer appears
  exactly once is an error rather than a pass; every apply and restore clears
  `__pycache__` and touches the file, because restoring a file to its previous
  *size* leaves bytecode CPython still considers valid and a mutation can look
  like it survived when it never loaded; a selection that collects nothing is a
  broken row, not a kill; and **one row must survive**, because a harness that
  reports red for a change that does not matter is reporting red for everything.
  It found two holes on its first full run.
- **`make standalone`** runs each of the 58 test files on its own. A suite is a
  shared process, so a file can pass because an earlier one imported something —
  `tests/test_offline.py` did exactly that for weeks, patching `socket.socket`
  and then importing `urllib.request`, which breaks `class SSLSocket(socket)`
  inside the standard library.
- **`oracle-half`** recomputes our column of the differential sweep and compares
  it. The reference column needs a JDK and somebody else's checkout; ours needs
  neither, and ours is the half that goes stale — a rule's severity could move
  and leave a recorded verdict describing a tool that no longer exists, while
  `docs/divergences.md` went on deriving counts from it.

Also: the vendored reference messages have a generator at last
(`capture_oracle.py --messages`) and, for the half that works offline, a pinned
hash — that file is what proves no remedy here is a translation of somebody
else's, and quietly shrinking it would quietly weaken the proof. And every
Makefile target `make check` does not run now carries a written reason, because
an exemption list is otherwise a way to make a gate go quiet.

Review of the packaging work, and what it found.

- **The workflow that publishes the reader could not run its own gate.**
  `release-sdk.yml` sets `working-directory: packages/vdi2770` for every step,
  and the step that runs `make check` was added without overriding it — there is
  no Makefile there. The SDK release would have failed before publishing
  anything. A test now checks structurally that a step running a repository-root
  command overrides a file-wide default.
- **The API fingerprint was blind to four kinds of breaking change.** A sweep put
  thirteen mutations through it; four passed both the fingerprint and the whole
  suite: a positional parameter made keyword-only, a public dataclass field
  losing its default, a return annotation changing, and an enum member's *value*
  changing. It recorded parameter names and type strings, which carry none of
  those. It now records the whole signature, the repr of every constant, class
  bases and members, and enum values — and it carries a format version, because
  "the recorder changed" and "the library changed" are different events that
  need different answers.
- **The pin's floor was never checked against anything published.** At one point
  today the validator pinned `vdi2770~=0.5.0` for a reader that existed nowhere
  but this working tree. Tagging from there would have published something pip
  could not resolve — the same failure as a loose pin, arriving from the other
  side. The floor now has to be a released `sdk-v*` tag or the reader being
  released beside it.
- **`--write` would create a baseline from nothing.** `rm API.json && --write` was
  exactly as easy as regenerating it, and looked the same in a diff. It takes
  `--first` now. The baseline also shipped in neither source distribution, so a
  downstream packager got the tool without the thing it compares against.
- **Deleting a duplicated test file cost the reader four behaviours.** The
  duplicates were real, but `tools/check_sdist.py` runs the reader's suite alone
  — that is what a packager of `vdi2770` runs — and after the deletion that suite
  passed a build in which every PDF is reported as encrypted, a non-ZIP is
  misclassified, `XmlError` carries no line, and an unreadable inner archive
  vanishes from the tree. Four tests, against the public API, in the suite that
  ships.

Packaging: the artifact people actually install is now looked at.

- **The wheel is built, opened, installed and run.** Nobody installs a source
  distribution, and nothing here built a wheel — so *"the licences travel with
  the package"* and *"the bundled schema ships"* were claims about strings in a
  `pyproject.toml`. `make check` now builds both wheels, checks that everything
  under `src/<package>/` and every licence file is in them, installs them into a
  temporary directory and runs the command line out of them. Removing the
  bundled schema does not crash the tool — it reports `X0` — so the smoke test
  asks about `X0` rather than only about the exit code.
- **A file deleted from the source could still ship.** setuptools assembles the
  wheel from `<project>/build/lib` and leaves behind files the source no longer
  has. Measured: with `data/rules.json` moved out of the tree, the built wheel
  still contained it. The gate now clears that directory before building, so
  what it measures is this commit rather than whatever the workspace last built.
- **The reader's public surface is recorded against the version that published
  it.** The pin gate catches "the pin is too loose"; it cannot catch the other
  half, which is the code moving while the version does not. This release's
  reader gained `DEFECT_KINDS` and `Container.parent` and changed
  `Container.rejected` from `Dict[str, str]` to `Dict[str, Defect]` while still
  calling itself 0.5.0. That 0.5.0 was never tagged and so never published — the
  newest reader on PyPI is 0.4.0 — so nobody was served a broken pair. What the
  gate prevents is the next one, and the release that would have shipped a
  validator pinning a reader version that exists nowhere but this tree. **The reader is
  0.6.0 and the validator asks for `~=0.6.0`.** `--write` refuses to record a
  changed surface under a version it has already recorded, because otherwise
  regenerating the baseline is a way to make the gate quiet.

One rule's crash used to be every container's crash.

- **A check that raises is a finding, not the end of the run.** The project's own
  conventions say so and the runner did not do it: a rule module raising killed
  the whole run, so a sweep over a supplier's drop folder died on one archive
  with a traceback naming this tool's internals, and every container after it
  went unchecked — the exact failure a validator exists to prevent. Each rule
  module and each step feeding them now demotes a crash to `X5`, an error,
  because a check that did not run is not a check that passed. Whatever a rule
  managed to report before crashing is kept.
- **The handler that existed so one bad path could not stop the rest was itself
  stopping the rest.** `except Exception as e: ... {e.strerror or e}` — that
  attribute is on `OSError` and nowhere else, so any other surprise raised an
  `AttributeError` out of the handler. `getattr` now, and the OS's own message
  is still preferred when there is one.

Two rules answering a question other than the one they ask.

- **`Z8` counts document containers now, which is what its title says.** It
  tested whether the reader had opened *any* archive, and a declared `.zip`
  payload is an opened archive — so a documentation container delivering no
  documents at all came back clean, exit 0. It also declines to answer when a
  child was there and unreadable: `Z1` says we could not look, and "there are
  none" would be a second and different claim.
- **A member the reader could not read is still in the archive.** A single bad
  CRC produced a report that contradicted itself twice. On `VDI2770_Main.pdf`:
  `Z12` *"a file could not be read"*, `Z7` *"there is no VDI2770_Main.pdf, add
  it"*, and `F1` *"declared but not in the archive"* — about one file that was
  right there. On `VDI2770_Main.xml`, worse: the container was classified from
  the readable names only, so it became `UNKNOWN`, `Z3` said *"this is neither a
  document nor a documentation container"*, and no `M`, `F` or `X` rule ran at
  all. Presence is now a fact about the archive's directory (`Container.present`
  in the reader, beside `file_names`), classification reads it, and `Z7` reads
  it. `F1` still fires — at the line in the metadata that named the file, which
  is what `Z12` cannot give you — but says *"in the container but could not be
  read"* and carries the remedy that fits. `metadata-unreadable` maps to `Z12`
  rather than `Z3`, and is no longer appended on top of a reason already
  recorded, which is how one file came to have two explanations.

Boundary findings — the module edges rather than the verdicts. The user-facing
ones are above in the same section.

- **One severity policy for "this tool stopped", and a field that says so.**
  Seven rules fire because the validator declined — a broken installation, a
  document the schema checker would not finish, one it would not build a model
  of, a check of ours that crashed, an archive over a budget, a tree deeper than
  we open, and documents delivered as folders. The four that existed when this
  policy was settled disagreed with each other: three were errors arguing *"a report that silently skipped
  the check would be worse than no report"*; `Z6` was a warning arguing the
  opposite for the same situation. Both are good arguments and only one can be
  the policy: if we did not look, exit 0 would be telling somebody we did. **`Z6`
  is an error now.** Every finding also carries `about: "container" | "tool"` in
  the JSON, because both kinds are errors on purpose and severity therefore
  cannot carry the distinction a CI consumer needs.
- **The reader stopped writing remedies.** `near_misses` carried the sentence
  *"it must sit at the root of the archive"* — a normative claim about VDI 2770,
  authored inside the package whose first line is that it decides nothing. It
  reports `(kind, name)` now and `Z3` writes the sentence; the output a user sees
  is unchanged. (`vdi2770` 0.6.0, breaking: `near_misses` values are tuples.)
- **`model.py` really is the single vocabulary a rule imports.** Its docstring
  said so while three rule modules reached past it for `Kind` and the reserved
  filenames in function-local imports, which the layering test had no opinion
  about. It re-exports them, the rules import them from there, and `vdi2770` is
  on the forbidden list.
- **One definition of canonical form.** Canonicalising a member name belongs to
  whoever reads archives; there was a second copy of that line in the validator,
  inside the module created because every place that compares a name has to do it
  the same way. `vdi2770.nfc` is public and a test fails on a second definition.
- **`DEFECT_TO_RULE` is gated.** It is the reader-to-rules interface, the lookup
  is `.get()` followed by `continue`, and nothing checked it — so a defect kind
  the reader grew would have been dropped in silence.
- **A gate that reads outside its own distribution is now caught by a gate.**
  Three times a check written in the reader package's suite reached up to the
  repository and broke the sdist test. The rule — a claim about the repository
  belongs to the repository's suite — is enforced rather than relearned.


Gates that could not fail. Nothing here changes what the tool reports; all of it
changes what the build refuses to let through.

- **"A rule that fires nowhere fails the build" is now true.** README said it;
  `rule_coverage --check` computed `unexercised` and never looked at it, so
  `--write` followed by `--check` printed *"ok ... 1 unexercised"* and exited 0 —
  the baseline blessing the one thing the tool exists to catch. The judging is a
  function now, tested against synthetic catalogues, and the baseline cannot
  excuse a dead rule: either it fires, or it is in `CANNOT_FIRE` with a reason.
- **A bound with no floor passes when the code does nothing.** Two assertions
  read *"we inflated less than N"*. A `_haystacks` that yielded an empty list
  satisfied both — measured, by stubbing it — and a PDF nobody looks inside
  reports no PDF/A claim at all. Both now assert that the raw bytes are searched
  and that something was inflated, and the budget test measures the same input
  unbounded and bounded so it tests the budget rather than the fixture.
- **Six hostile names were not six branches.** The parametrised name test
  asserted only that each was rejected. `dir\..\..\evil.txt`, labelled
  *"backslash separator with traversal"*, never reached the backslash rule —
  traversal is checked first. Each case now asserts the reason, which made the
  wrong label visible immediately, and `5:/ratio.pdf` was added because
  `5:1.pdf` never reaches the `isalpha` guard it was there to protect.
- **The validator's rule-id check now looks as hard as the SDK's.** Five
  hard-coded ids in quotes, against a regex over every id, quoted or not — and
  the regex had already caught an unquoted id in a comment that also had the
  severity wrong.
- **A test that could not fail is deleted, not left to look like coverage.**
  `test_ci_runs_every_make_command` searched the workflow text; its sibling
  searches the actual `run:` steps and subsumes it completely.


## 0.6.0 — 2026-08-24

What turned up over the earlier work.
No new coverage: every item is a wrong answer replaced with a true one, or a test
that could not fail replaced with one that can.

- **`X0` blamed this tool for the container's doing.** Two different failures
  wore one flag: the bundled schema failing to load, which is ours, and
  `iter_errors` giving up part-way through somebody's document, which is not.
  The second was reported as *"The schema check could not run — check the
  installation … re-install with pip"*, so a metadata file nested a thousand
  levels deep was told to reinstall the tool. New rule **`X4`** says what
  actually happened, and its remedy points at the document while `X0`'s keeps
  pointing at the installation. Neither can say the other's thing now — a test
  holds both apart. `tools/rule_coverage.py` justifies `X0` as "only fires when
  this tool's own installation is broken, which no container can cause"; that
  sentence is true again.
- **The report no longer contradicts itself.** `--quiet` hides the notes, and
  the "no findings" line then printed above a summary reading "1 note(s)". It
  says how many were not shown. A test had pinned both halves of that; replacing
  it turned up something worth knowing — a report with nothing at all in it is
  unreachable for a conforming container, because `M6` requires a PDF per version
  and every PDF yields `P3` or `P4`.
- **`Z9` names every folder on the path**, not only the last one. `a/b/x.pdf`
  puts the file in `a/b/` and in `a/`, and the rule called that "1 folder".
- **Four tests that could not fail.** The amplification measurement used
  `ru_maxrss`, a process high-water mark that never comes down — inside the full
  suite it was already above anything the test could add — and on Linux it is in
  kilobytes, so on the only platform CI runs the threshold was a thousand times
  looser than it read. It uses `tracemalloc` now, and the mutation it was written
  for fails both alone and in the suite. Alongside: a dead `or` clause that
  swallowed its own assertion, a "both levels" test that checked one, and a
  stream-budget test with a ceiling and no floor.
- **Every budget constant is pinned, and a test says so.** Three caps were added
  after the table was written and never joined it, while the file's docstring
  claimed each one is pinned separately. The table is now checked against the
  modules rather than maintained by memory.
- **`Z8` knew three of the six ways the reader stops descending.** The guard
  listed defect kinds and missed the three rejections that drop a `.zip` before
  the descent loop sees it — an unsafe name, an oversized member, a suspicious
  compression ratio — so `Z4` or `Z5` named the archive it had refused and `Z8`
  said on the next line that no document containers were there. It asks
  `container.rejected` now, which is every member the reader dropped whatever the
  reason, including reasons added later.
- **The container budget says how many it did not open.** Stopping at the limit
  emitted one defect naming one archive and left the remaining siblings
  unmentioned, so a report of one skipped container was hiding several. The count
  is in the message, and the counter behind it no longer climbs past the limit it
  names — it was incrementing on refusals too.
- **Absent and empty are different wherever the reader flattens a value.** The
  distinction `M5` learned was given to `Description.language` and not to
  `Classification`, so it survived twice over in the class table: an empty
  `<ClassId></ClassId>` — which the schema accepts, the element being required and
  typed `xs:string` — switched `M2` off entirely and nothing said a word, while a
  `ClassName` carrying no `Language` attribute at all produced `M8` *and* `X2` for
  one defect. `Node.child_text` returns `None` for an absent element now, and the
  class table carries the distinction the way the descriptions already did.
- **Two Unicode spellings of one name are two files.** Reconciling NFD and NFC
  was right; doing it by mapping every member onto its canonical spelling was
  not. An archive holding both spellings kept whichever came last, so a valid
  declared PDF was judged by reading its junk twin, the twin was never reported
  as undeclared, and reversing the member order flipped the verdict. `Z10` — the
  rule for "two members whose names a reader cannot tell apart" — now covers
  canonical equivalence, an ambiguous name resolves to nothing rather than to a
  guess, and `F2` reports the archive's own spelling instead of the normalised
  one, which is the only one a user can find in their ZIP listing.
- **One place decides what a name means.** `nfc()` moved out of the model into
  `names.py` with the resolver beside it, and the F rules, the PDF rules and the
  runner all ask that. The two mistakes behind this are written at the top of the
  file: applying the normalisation to two of three comparisons, and each layer
  keeping its own copy until they disagreed. `F1` also looks up a refused member
  under either spelling now — it was keyed by the archive's and asked in the
  metadata's, so a file that was present and declined was reported as absent.
- Corrections to earlier entries, found by re-reading them against the code: the
  0.3.0 notes said three `container` rules where there were four and 42
  containers where the recorded sweep says 43, `docs/divergences.md` said thirty
  reference citations where the catalogue carries 28, and the reader's README
  listed six budgets and left out the three most recently added.


## 0.5.1 — 2026-08-24

**0.5.0 did not deliver its own fix.** The quadratic scan lives in the reader,
and the dependency was `vdi2770~=0.3.0` — a range that *permits* the fixed 0.3.1
without *requiring* it. Installing `vdi2770-validate==0.5.0` from a clean
environment pulled `vdi2770` 0.3.0 and reproduced the hang: 0.65 seconds for a
64 KiB input, still quadratic. Verified by installing it, not by reading the
metadata.

The floor is the reader version these tests ran against, and a test now checks
that rather than only checking the pin accepts it.

If you installed 0.5.0, upgrade — or check with
`pip show vdi2770` that the reader is 0.3.1 or later.


## 0.5.0 — 2026-08-24

Released promptly rather than batched: the first item is a way to make the tool
run for hours on a small file, and it is in 0.4.0.

- **A malformed PDF could hang the tool.** The XMP packet scan was
  `START.*?END` with `re.S`; with the closer absent, every opener rescanned to
  the end of the buffer. 128 KiB of `<?xpacket begin` took 2.6 seconds and the
  cost squared with size, so a member sized just under the compression-ratio
  floor — which the reader accepts without a single defect — would have run for
  hours on a file small enough to email. None of the budgets caught it: they
  bound inflation, and this is the pass over the raw bytes. Packets are found by
  scanning now; the same input takes 16 milliseconds.
- **The tree budget did not cover the runner.** `MAX_CONTAINERS` and
  `MAX_TOTAL_METADATA_BYTES` bound what the *reader* holds, and the runner then
  kept every container's decompressed bytes in a dictionary keyed by path and
  never dropped one. Measured: a 2 MB input with two hundred inner containers
  reached 2,199 MB. It keeps one buffer per nesting level now — the walk is
  pre-order, so the parent's bytes are the only ones a container needs — and the
  same input reaches 582 MB, which is the reader's own peak. That is the third
  half-fix of the day: the budget was right about the thing it measured.
- **A container knows which member it came from.** `Container.member_name`
  replaces splitting the path on the JAR separator, which got the wrong answer
  for a member whose own name contains one — and silently, since both lookups
  simply missed and the PDF rules were skipped without a word.
- **A reserved name is only reserved where it is reserved.** The structural
  exemption that keeps `F2` quiet about `VDI2770_Main.xml`, `VDI2770_Metadata.xml`
  and `VDI2770_Main.pdf` named all three in every container, so a stray
  `VDI2770_Main.pdf` inside a *document* container — a name that means nothing
  there — was never reported as undeclared. The exemption now follows the
  container's kind.
- **The reader package carries a NOTICE.** Apache-2.0 asks for it to travel with
  the distribution; the validator shipped one from its first release and
  `vdi2770` shipped only a LICENSE, because its `license-files` named only that.
  Its NOTICE says what is true of it and not of its sibling: nothing third-party
  is bundled here at all. (`vdi2770` 0.3.1.)
- **The differential-oracle evidence is accounted for.** `docs/oracle-sweep.json`
  is derived from running someone else's MIT-licensed software, and was in
  neither NOTICE nor THIRD_PARTY.md. It is in both now, and a test asserts every
  string in it is an identifier rather than their message text — which is the
  property that keeps the attribution small and true.
- **Both spellings of a filename, in both directions.** The earlier NFD/NFC
  reconciliation normalised `present` and `declared` and missed the `F1` lookup
  itself, so a container whose *metadata* was decomposed and whose *archive* was
  composed had its file reported as declared-but-missing while `F2` stayed quiet
  about it — absent and accounted for at the same time. Only one of the two
  directions had a test. Both do now.


## 0.4.0 — 2026-08-24

All seven defects left open above, fixed one at a time. Verdicts on the 43
recorded corpus and fixture containers are unchanged throughout — checked at the
level of finding counts, not just which rules fired, because several of these
changes are the kind a set comparison cannot see.

- **A declared `application/zip` payload is no longer judged as a container.**
  The reader opens every member ending in `.zip` because it has no metadata and
  cannot know better; the rules do have the metadata and now use it. A parts list
  attached as `teileliste.zip` used to earn `Z3` — "neither a document container
  nor a documentation container" — which it had never claimed to be, while `F3`'s
  own remedy blesses `application/zip` with `.zip` in the same breath. Inside a
  document container it also earned `Z11`, whose own argument excuses it: that
  rule exists because an undeclared container is "a way to carry something past a
  check that only looks at declared files", and a declared one is not past that
  check. An **undeclared** inner `.zip` still fires both, and a declared payload
  that turns out to be a real container is still validated as one.
- **An identifier is `(domain, value)`, not a bare string.** The schema makes
  `DomainId` required — an id belongs to whoever runs that domain — and `M9`
  compared the text alone, so the same drawing number registered by an OEM and by
  its supplier read as a repeat. The remedy said "remove the repeated DocumentId",
  which would have destroyed a real registration; a warning whose advice is
  harmful is worse than silence. The reader now carries `Document.identifiers`
  (`vdi2770.DocumentId`, with the domain and the source position); `Document.ids`
  stays as a view of the values alone. Findings point at the repeated element
  rather than at the top of the document.
- **The main document is looked at.** `VDI2770_Main.pdf` is the file a
  documentation container is built around, and three rules each handed it to the
  next: `Z7` is satisfied by the name, `F2` exempts it as structural, and the P
  rules only looked at files the metadata declares. Declaring some other PDF is
  schema-legal, so an eighteen-byte text file called `VDI2770_Main.pdf` passed
  with exit 0. The reserved name is now a declaration in its own right, in a
  documentation container only — inside a document container it is just a file
  with a confusing name, and inventing a requirement there would be worse than
  the gap.
- **An empty value no longer switches a check off.** `M5` fired on an empty
  `<Language/>` element and stayed silent on an empty `Language=""` attribute —
  the guard was `if d.language`, which is the shape `M8`'s own `whyOurs` warns
  about. The reader now distinguishes an absent attribute (`None`) from a present
  empty one (`""`), so the absent case stays with the schema layer where it
  belongs and the empty one is reported.
- **A namespace prefix is arbitrary.** A PDF/A identification is identified by
  its URI; `pa:part` bound to `http://www.aiim.org/pdfa/ns/id/` says exactly what
  `pdfaid:part` says. The scan matched the literal token, so a file from a
  conforming exporter read as having no claim and `P3` told its author to fix
  something that was already right. The prefix now comes from the packet's own
  declaration — and a prefix bound to some other URI is still not a claim.
- **A refusal to look is no longer reported as an absence.** `Z8` said a
  documentation container held no document containers while `Z6`, one line above,
  named the one it had found inside it. `Z8` tested for absent children, and the
  reader stops populating them at three levels, at the tree's container budget,
  and for a `.zip` member it could not decompress. It stays quiet in those three
  cases, where `Z6` and `Z12` already say what happened, and a container that
  genuinely holds nothing is still reported.
- **A folder is a folder whether or not the ZIP says so.** `Z9` tested
  `ZipInfo.is_dir()`, which is a trailing slash on a member name, and directory
  entries are optional in the format — so whether the rule fired depended on
  which library wrote the archive rather than on the archive's shape. A container
  that put every file in `docs/` passed clean; adding one empty `anhang/` entry
  to the same layout did not. It now reports the folders the member paths imply,
  and names them.
- **One note per file, not per declaration.** A metadata file naming the same PDF
  in three document versions printed three identical `P4` lines about one file.
- **A decomposed filename is scanned, not silently skipped.** Reconciling NFD and
  NFC in the F rules alone turned out to be worse than not doing it: `F1` stopped
  reporting the file as missing while the P rules went on failing to find it, so
  a Mac-zipped delivery with an umlaut in a filename had its PDFs checked by
  nobody. Both layers resolve names the same way now.
- A test now checks that the reader version in this repository satisfies the
  range the validator declares for it. Getting that wrong sends `pip` to PyPI for
  a package that only exists in the working tree — it happened once while writing
  the change above, and only running the install caught it.


## 0.3.1 — 2026-08-24

**A small file could exhaust the machine.** Found while drawing the architecture
to check it, which is the argument for drawing it.

Every limit in the reader bounded one archive or one member. None bounded the
container *tree*, and a documentation container may hold thousands of inner
containers whose metadata is held for as long as the caller walks it. Measured:
a **274 KB** input produced **265 MB** resident, and no per-archive cap came near
engaging — the outer archive's uncompressed total was 254 KB against a 2 GiB
limit. The only binding constraint was the ten-thousand-member cap, so ten
thousand inner containers each carrying sixteen megabytes of metadata was a
permitted input: roughly **156 GiB**, from a file small enough to email.

Two budgets now span the whole read — `MAX_CONTAINERS` (1,000) and
`MAX_TOTAL_METADATA_BYTES` (64 MiB) — and exhausting either is reported as a
`container-budget-exhausted` defect rather than silently truncating the tree.
The same 274 KB input now peaks at 95 MB. Ordinary nested containers are
untouched.

The gap was structural rather than an oversight in any one cap: each limit was
correct about the thing it measured, and nothing measured the total. The
amplification test that existed checked a single archive.


## 0.3.0 — 2026-08-24

Thirteen defects, six of them fixed here. The three that mattered most were
containers this tool passed with exit 0 that `unzip -t` refuses, and legitimate
deliveries it failed.

**It said nothing about archives that are broken**

- **New rule `Z12`** — a member listed in the directory that cannot be
  decompressed. A truncated transfer (broken CRC) and a member with a password
  both produced "no findings", exit 0: the bytes came back empty and every later
  layer read that as "not declared". These are the commonest defects a handover
  archive has, and this tool certified them clean.

**It failed deliveries that were fine**

- `Z5` no longer treats a high compression ratio as hostile below 8 MiB. An
  uncompressed TIFF scan of a line drawing expands ~220× and lands at one
  megabyte; a 104 KB archive was refused with "exceeds this tool's limits for
  untrusted input" and the unactionable remedy "split the delivery".
- `Z4` no longer calls `5:1.pdf` an absolute path. The drive-letter test looked
  only for a colon in the second position; a gear ratio is not a drive.
- `F1`/`F2` compare filenames under Unicode NFC. macOS writes decomposed names
  into a ZIP while metadata authored elsewhere is composed, so the report used to
  say the same visible name was both missing and undeclared.
- `Z2` no longer says "the archive is empty" when the archive has members we
  refused to read, and no longer swallows `Z3` when it does.
- `M2` no longer tells you to pick a valid class id when the `ClassId` element is
  absent. There is nothing to correct; `X2` reports the missing element.

**Seven rules were wearing the wrong provenance**

`container` means "true without knowing VDI 2770 at all" — the strongest thing
this project claims about a rule. It had become the default for anything not
obviously schema or table. `Z3`, `F1`, `F2`, `F3`, `F4` and `P1` all rest on VDI
reserved filenames or the VDI metadata model, and are now `reference`; `X1` was
`schema`, but well-formedness is XML 1.0 and the schema cannot speak until it
holds, so it is now `container`. A test lists the four remaining `container`
rules with a written reason each, and fails if a fifth appears unexplained.

The count moves in the honest direction: fourteen rules now rest on behaviour
read out of someone else's Java and never checked against the guideline, where
the release notes for 0.1.0 implied none did.

**Measured, at last**

`docs/divergences.md` said "comparing all nineteen corpus containers against
captured output is on the board and not done". It is done: 43 containers through
the reference implementation at its pinned commit, and `tools/oracle/` carries
what is needed to repeat it. Every reference message key the catalogue cites
exists in that project and agrees with the code it is paired with — 0 defects on
30 citations. Two things the sweep found: the reference **crashes** on a
path-traversal archive rather than reporting it (zip4j blocks the traversal, so
this is a robustness gap and not a vulnerability), and it extracts every
container to a temporary folder on disk before validating, which this tool
never does.

**Still open**, recorded rather than quietly dropped: seven verified defects,
listed here — a declared `application/zip` payload is judged as
if it were a container, `Z9` misses subdirectories that carry no explicit folder
entry, `M9` treats one id string in two `DomainId`s as a repeat, an undeclared
`VDI2770_Main.pdf` is never content-checked, `Z8` contradicts `Z6` at four levels
of nesting, `M5` skips an empty `Language` attribute, and `P3` misses a PDF/A
claim bound to a prefix other than `pdfaid`.


## 0.2.0 — 2026-08-24

The readers moved out into their own package. `vdi2770` is now a dependency-free
library that reads a container and hands you a typed model; `vdi2770-validate` is
that library plus a rule set. Nothing about the verdicts changed — the same 207
tests pass on both sides of the move, and the reference corpus produces byte-identical
output.

Why bother: a rule set is an opinion, and opinions should be replaceable. Anyone
who wants to check a container against *their* customer's supplement, or feed the
parsed model into an AAS submodel builder, should not have to take our 33 rules
with them to do it.

- New package `vdi2770` (Apache-2.0, no dependencies) — `read_container`,
  `parse_xml`, `build_document`, `read_pdf`, and the value types.
- `vdi2770-validate` now depends on `vdi2770~=0.1.0`. The CLI, the rules and the
  output are unchanged.
- Moved, not copied: there is one implementation of each reader, in the SDK.
- Fixed: the 0.1.0 changelog said "32 rules" in a bullet and "33 rules" a
  paragraph above it. The catalogue had 33. A test now holds that number so the
  two cannot drift again.

**If you import from `vdi2770_validate.readers` or `vdi2770_validate.domain`,**
those paths are gone; import from `vdi2770` instead. The CLI is unaffected.

## 0.1.0 — 2026-08-24

First release. It reads a VDI 2770 container and tells you what is wrong with
it, offline, with a remedy on every finding.

What 0.1.0 means here: the 33 rules it has are gated — each was killed in turn to
confirm the suite notices, 22 have a minimal violating/conforming fixture pair,
and the rest are exercised by the reference project's own examples, which no
structural rule is allowed to fire on. What it does *not* mean is broad coverage
of VDI 2770. The scope is small and written down in docs/scope.md, and the
refusals there are the honest part.

- Reads VDI 2770 document and documentation containers without extracting them.
- 33 rules across five layers — container shape, schema conformance, declared
  files versus actual members, metadata model, and PDF claims — each with a
  remedy sentence and each traceable to the schema VDI publishes free, to a
  freely published table, to container mechanics, or to a stated judgement of
  our own. *(Corrected in 0.3.0: this list left out `reference` — behaviour read
  out of the reference implementation and never checked against the guideline —
  which eight of those rules carried, and fourteen carry now.)*
- Document classification matched on class id and German name. The two freely
  published sources disagree on five of twelve English names, so an English name
  never decides a verdict here; it produces a note showing both renderings.
- Reports what a PDF *claims* about PDF/A. Does not verify the claim, and says so
  on every line where it matters.
- Gates: fixture pairs, firing coverage, import layering, offline, determinism,
  CI/local parity, the declared Python floor, licence notices, remedy text not
  copied from the reference, no structural rule firing on an upstream example,
  and the README sample being output the tool really produces.
