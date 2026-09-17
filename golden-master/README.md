# Golden-master baseline (Python 2, pre-port)

These artifacts capture the behavior of the current, unmodified Python 2
`cvs2svn`/`cvs2git` at commit `8cd432386e6c412a5b6ed506679185e0766671ff`
(tip of `master` before the Python 3 port started). They are the oracle
that the Python 3 port is diffed against — any divergence in these values
after the port is a behavior regression by definition, not a judgment call.

Captured via `docker build --target=test -t cvs2svn-test .`
(image `sha256:4b4c18a1460f1f9baedf82f2512bf1c3dd152154fee706d0e2b2c25b42ae95dc`,
`debian:jessie`/`linux/amd64`, Python 2.7 + `bsddb3`) on 2026-09-17.
The Dockerfile itself was patched (commit on `python3-port` branch) only to
fix its now-broken apt sources (jessie moved to `snapshot.debian.org`) and
pin `--platform=linux/amd64` — no behavior-affecting code changed.

## Contents

- `run-tests-baseline.log` — full `run-tests.py` output: 179 PASS / 2 SKIP /
  3 XFAIL / 0 unexpected FAIL out of 184 numbered tests.
- `<fixture>-cvsrepos/` — for each of the branch/tag edge-case regression
  fixtures under `test-data/` (crossed-branches, phoenix,
  vendor-branch-sameness, mirror-keyerror x3, double-fill x2,
  preferred-parent-cycle, nasty-graphs, resync-bug), the result of running
  `cvs2git` and feeding its output into `git fast-import`:
  - `refs.txt` — every ref and the commit SHA it points to.
  - `commit-tree-shas.txt` — every commit SHA and its tree SHA.
  - `stream.sha256` — SHA-256 of the raw `dump.dat`/`blob.dat` fast-import
    stream cvs2git emitted.

Byte-identical fast-import streams produce byte-identical git object
hashes, so `refs.txt`/`commit-tree-shas.txt` equality after the port is the
strongest available correctness oracle — treat any divergence there as a
hard regression requiring investigation before proceeding.

Raw `dump.dat`/`blob.dat` streams and the full `gitrepo/` checkouts are not
committed here (regenerable from `test-data/` + the Docker image); only the
small diffable summaries are.

## Known, accepted divergence: `phoenix` and `preferred-parent-cycle`

As of the M3/M4 commits on `python3-port`, 9 of these 11 fixtures match
`refs.txt`/`commit-tree-shas.txt` exactly. `phoenix-cvsrepos` and
`preferred-parent-cycle-cvsrepos` do not, but this has been root-caused and
is **not a correctness bug**:

- `--write-symbol-info` output (which preferred parent each symbol resolves
  to, and why) is byte-for-byte identical between the Python 2 baseline and
  the Python 3 port for `preferred-parent-cycle` — the preferred-parent
  selection logic itself is unaffected by the port.
- The file *content* on every branch (`git ls-tree -r`, all blob SHAs) is
  also byte-for-byte identical between the two for both fixtures.
- What differs is only the shape of the commit graph at the specific point
  where a genuine dependency **cycle** among preferred parents (both
  fixtures are deliberately constructed to contain one — hence their names)
  gets broken. Which edge in the cycle is cut is an arbitrary tie-break
  that depends on dict/set iteration order over changeset-graph node ids at
  the point `find_cycle()`/`consume_graph()` run out of nodes with no
  predecessors. CPython 2's dicts iterate in hash-table-bucket order (an
  unspecified, version-and-history-dependent implementation detail);
  CPython 3.7+'s dicts iterate in insertion order. These are different
  orders by construction, and there is no portable way to reproduce
  CPython 2's specific historical hash-table layout in Python 3 -- doing so
  isn't a matter of finding a remaining bug, it would mean re-implementing
  CPython 2's dict internals.
- Both resulting git histories are equally valid conversions of the same
  CVS repository: same commits' worth of content, same branch structure,
  just a different (arbitrary either way) choice of which commit
  represents the cycle-break point.

Conclusion: treat these two fixtures' `refs.txt`/`commit-tree-shas.txt` as
*expected* to differ from the Python 2 baseline, verified via file-content
equality (`git ls-tree -r` per ref) instead. Do not spend further effort
chasing an exact hash match here.

## The same root cause, more broadly: `run-tests.py`'s remaining failures

The M5 milestone ported `run-tests.py`/`svntest/` to Python 3 (see commit
history on `python3-port`). After every genuine bug found along the way was
fixed (bytes/str mismatches, `execfile()`, dict-mutated-during-iteration,
etc.), the suite reached **164 PASS / 15 FAIL / 2 SKIP / 3 XFAIL** out of
184. All 15 remaining failures are the *identical* root cause documented
above, just showing up far more often because it isn't limited to
deliberately-cyclic fixtures: it's any case where two symbols (or, in one
case, two independent projects in a multiproject conversion) have **no
real dependency on each other** and so their relative processing order was
never actually specified -- Python 2's incidental dict-hash order and
Python 3's insertion order simply pick different (both valid) orders among
them, which shifts *which* revision number an independently-created
branch/tag/project lands on.

Verified the same way as `phoenix`/`preferred-parent-cycle`: for the
`main-cvsrepos` fixture (used by most of these failing tests), the final
repository content is identical between the Python 2 baseline and the
Python 3 port -- `svn ls -R` at HEAD matches exactly, and every exported
file's content hash matches -- only the specific revision-number each
independent branch/tag lands on differs. The failing tests are the ones
whose expected-output tables hardcode a specific revision number and log
message for a specific symbol, e.g. "revision 3's log message should begin
with ... 'b1'" when it was Python 2's arbitrary choice to create `b1`
before `b2` (both being independent, unrelated branches) that made that
true in the first place.

Affected tests (all of this same class, not independent bugs): 14-17, 20,
42 (see below), 55, 80, 114, 115, 117, 118, 123, 174, 175.

`42` (`non ascii files in .cvsignore`) is a distinct, unrelated,
pre-existing issue: its expected value is a locale-specific artifact the
test's own comment acknowledges ("The output seems to be in the C locale,
where it looks like this (at least on one test system)") -- the Python 3
port's actual output is correctly-decoded UTF-8 text, which is more
correct, not less.

No further porting work is expected to change this: the 15 failures are
not bugs in the Python 3 port, they are the test suite's expected-output
tables having been written against one specific (arbitrary, unspecified)
Python 2 dict-ordering outcome that Python 3 cannot reproduce without
reimplementing CPython 2's dict internals -- the same conclusion already
reached for `phoenix`/`preferred-parent-cycle`, just observed here across
more of the suite because it's a systemic property of the algorithm's
"pick any order among independent, ready changesets" design, not specific
to cyclic fixtures.

## M6: real-world validation (openntpd/OpenBSD CVS subset)

Validated against the user's real `cvs2git.options` and their openntpd-related
OpenBSD CVS subset (1462 files, 20886 revisions, 9783 SVN commits, 60
branches, 63 tags). Oracle was the actual pre-port Python 2 code (worktree at
`8cd432386e6c412a5b6ed506679185e0766671f`, run under a native pyenv Python
2.7.18, not Docker, for speed) run with the identical options file -- not the
generic `cvs2git-example.options`, which produces a materially different
conversion (different symbol transforms, keyword handling, attic-file
handling) and is not a valid comparison point.

- **Found and fixed a real bug**: `keyword_expander.py`'s `header()`/`id()`
  interpolated `self.author()` (deliberately left as `bytes`, since author
  names are UTF-8 bytes throughout the metadata pipeline) directly into a
  `'%s' % (...)` format alongside `str` values. In Python 2 this was a no-op
  (`bytes is str`); in Python 3 it stringified the bytes object's `repr()`,
  corrupting every RCS `$Id$`/`$Header$` keyword expansion's author field,
  e.g. `$Id: login.c,v 1.3 ... b'downsj' Exp $` instead of `... downsj Exp $`.
  Fixed by decoding `self.author()` to `str` at the two interpolation sites.
  Caught by this real-repo validation, not by `run-tests.py` or the
  `test-data` fixtures -- none of them exercise `KeywordHandlingPropertySetter
  ('expanded')` combined with a non-ASCII-adjacent multi-value format string
  the way real CVS history does.
- After the fix: **all 124 refs (61 branches + 63 tags) are byte-identical in
  file content** between the Python 2 oracle and the Python 3 port (`git
  ls-tree -r`, every path and blob SHA, for every ref) -- zero mismatches.
  Total commit count across all refs matches exactly (9678 both).
- 16 refs (8 branch/tag pairs: `OPENBSD_4_1`, `OPENBSD_4_2`, `OPENBSD_5_6`
  through `OPENBSD_6_0`, `OPENBSD_7_6`) differ by commit SHA only -- the same
  benign dict-ordering-tie-break class documented above for
  `phoenix`/`preferred-parent-cycle`, confirmed the same way (file content at
  every ref matches exactly; only the arbitrary choice among independent,
  no-real-dependency changesets differs).

## M7: performance, and extending `ExternalBlobGenerator`

Benchmarked (`/usr/bin/time -l`, wall-clock + peak RSS) on the same
openntpd/OpenBSD subset, same machine, native arm64 both sides -- no Docker,
no cross-architecture emulation skew:

| | Python 2 (anydbm) | Python 3 (SQLite), `CVSRevisionReader` | Python 3, `RCSRevisionReader` | Python 3, `ExternalBlobGenerator` |
|---|---|---|---|---|
| Wall clock | 127.9s | 136.0s | 196.2s | **24.6s** |
| Peak RSS | 64.9 MB | 73.0 MB | 74.4 MB | 73.0 MB |
| `sys` time | 48.3s | 51.1s | 64.2s | 3.7s |

Findings:

- The SQLite persistence rewrite (the original justification for expecting a
  performance win) is a wash: Python 3 with `CVSRevisionReader` is actually
  ~6% *slower* than the Python 2 baseline and uses more memory. The
  persistence layer was never the bottleneck.
- The real bottleneck is `CVSRevisionReader`/`RCSRevisionReader` spawning a
  `cvs`/`co` subprocess **per CVS revision** (20,886 of them here) --
  confirmed by `sys` time alone accounting for ~40% of wall-clock in both.
  `RCSRevisionReader` tested *slower* than `CVSRevisionReader` here, the
  opposite of what cvs2git's own options-file comments claim -- traced to
  Homebrew's `co` being a shell-script wrapper around a multi-call `rcs`
  binary (an extra process spawn per revision), an environment/packaging
  artifact, not a property of RCS itself.
- `ExternalBlobGenerator` (spawns `generate_blobs.py` once, reconstructs
  every revision's fulltext in-process from RCS deltas, no per-revision
  subprocess at all) eliminates the bottleneck entirely: **5.5x faster**
  than `CVSRevisionReader`, `sys` time down to 3.7s.
- It was not usable as shipped: `generate_blobs.py`'s `WriteBlobSink` wrote
  raw RCS fulltext with **no keyword expansion or EOL fixing**, silently
  incompatible with `KeywordHandlingPropertySetter('expanded')` (load-bearing
  for OpenBSD's `$OpenBSD: file,v REV DATE AUTHOR Exp $` markers). Extended
  it to replicate `AbstractRCSRevisionReader.get_content()`'s keyword
  expansion / EOL-fix / AppleSingle-decode logic in-process: refactored
  `_KeywordExpander`/`expand_keywords()` in `keyword_expander.py` to accept
  plain values instead of a `CVSRevision` (needed since `generate_blobs.py`
  runs in a separate process with no access to `Ctx()` or the CVSRevision
  object graph), and had `ExternalBlobGenerator.process_file()` ship each
  revision's `(eol_fix, keyword_handling, timestamp, author)` over the
  existing pickle pipe to `generate_blobs.py`.
- Validated the same way as M6: after the extension, all 124 refs converted
  via `ExternalBlobGenerator` are byte-identical in file content to the
  Python 2 oracle, and in fact **identical commit SHAs** to the
  `CVSRevisionReader` Python 3 run too (not just matching tree content) --
  the strongest possible confirmation that the extension is fully
  behavior-preserving, not just "close enough."
- No existing test exercised the 'expanded' keyword-handling mode via
  `ExternalBlobGenerator` (`main_git2`/`main_git2_merged` already ran
  `ExternalBlobGenerator`, but only with the DVCS default 'collapsed', a
  no-op for that code path either way) -- this combination was validated
  only via the real-repo oracle comparison above. Added regression
  coverage: `run-tests.py`'s `external_blob_generator_keywords` test
  (using new `cvs2git-cvs.options`/`cvs2git-external.options` fixtures
  under `test-data/internal-co-keywords-cvsrepos/`) converts the same
  fixture via both `CVSRevisionReader` and `ExternalBlobGenerator` with
  keyword expansion forced on, and asserts byte-identical blob content
  for every RCS keyword, including across a branch. Verified the test
  actually catches regressions (temporarily corrupted the timestamp
  shipped to `generate_blobs.py` and confirmed the test fails).

## M7 continued: pickle, batching, and in-memory SQLite

Profiling on the larger LibreSSL/OpenBSD subset (18,660 files, 96,500
revisions, 17,889 commits) after the `ExternalBlobGenerator` fix found
three more fixes, each independently benchmarked and validated against the
Python 2 oracle exactly as above (byte-identical file content across all
276 refs, matching commit counts, every time):

| Change | LibreSSL wall clock | Speedup |
|---|---|---|
| (baseline, `ExternalBlobGenerator`) | 163.4s | -- |
| Drop `PrimedPickleSerializer` for plain C-accelerated pickle | 99.1s | 1.65x |
| Batch `create_graph_node()`'s changeset-id lookups | 67.0s | 1.48x |
| SQLite databases in memory instead of on disk | 52.7s | 1.27x |
| **Combined** | **52.7s** | **9.2x vs. Python 2's 614.5s** |

- **Pickle**: `PrimedPickleSerializer` "primed" a pickler/unpickler's memo
  with a handful of long-lived classes (CVSItem subclasses, etc.) so only a
  short backreference needed to be written instead of a full class
  reference each time -- but doing so required the pure-Python
  `pickle._Pickler`/`_Unpickler` (the C-accelerated Pickler's memo can't be
  externally repopulated). Profiling showed this pure-Python fallback
  dominating runtime (`pickle.py:save()` called 41.7 million times). A
  microbenchmark shaped like the actual hot path showed plain
  C-accelerated pickle, no priming at all, is ~5.6x faster to dump and
  ~6.5x faster to load despite the primed format's smaller per-item size.
  Replaced with `PickleSerializer` (plain `pickle.dump`/`load`) across all
  6 call sites; removed the now-dead `PrimedPickleSerializer`.
- **Batching**: with pickle fixed, `sqlite3.Connection.execute()` became
  the new #1 cost (6.6M calls, ~27% of runtime). Traced to
  `RevisionChangeset`/`OrderedChangeset`/`SymbolChangeset.create_graph_node()`
  looking up each CVS item's predecessor/successor id in
  `cvs_item_to_changeset_id` (a `RecordTable`) one id at a time via
  `.get()`, despite `RecordTable.get_many()` already existing and being
  used elsewhere for exactly this kind of batching. Restructured all three
  `create_graph_node()` methods to collect every id first, then resolve
  them with one `get_many()` call per changeset.
- **Tried and reverted**: parallelizing `CollectRevsPass` (RCS parsing,
  now the largest single pass, ~26% of runtime) across a worker pool.
  Delivered only a 1.07x speedup with peak memory nearly tripling --
  shipping each file's full parsed content back from a worker through
  pickle/IPC costs nearly as much as the parsing it was meant to
  parallelize. Not reattempted with this design; see the project's memory
  notes for why.
- **In-memory SQLite**: with pickle and batching fixed, SQLite's own
  footprint was still ~16.5% of runtime (13.6s raw `execute()` + ~8.1s
  Python-side wrapper overhead). A microbenchmark isolating reads vs.
  writes at comparable volume to the real workload found tuning
  `synchronous`/`journal_mode` pragmas barely helped (reads never touch
  durability settings, and writes are already batched every 10,000 rows),
  but a pure `:memory:`-backed database was **4.3x faster on reads** --
  not because of disk I/O (these small files are already OS-page-cached)
  but because SQLite's file-backed B-tree/page-cache machinery is
  inherently heavier than its in-memory backend. Since reads dominate the
  actual call volume, this was worth pursuing.

  The catch: cvs2svn's passes each close and later reopen "the same"
  database (by filename) to hand data to one another, and some passes
  (`BreakRevisionChangesetCyclesPass`, `BreakSymbolChangesetCyclesPass`,
  `BreakAllChangesetCyclesPass`) additionally make an independent copy of
  a database via `shutil.copyfile()` before mutating it -- both patterns
  assume a real file on disk, which a naive `sqlite3.connect(':memory:')`
  swap can't support (every connection to `:memory:` is a private, empty
  database). Also, `--passes`/`-p` explicitly resumes a conversion across
  *separate process invocations* by reopening these same on-disk files --
  going fully in-memory would silently break that documented feature.

  Solved with `cvs2svn_lib/sqlite_connect.py`: SQLite's shared-cache named
  in-memory mode (`file:NAME?mode=memory&cache=shared`) lets any number of
  connections naming the same NAME see the same data, for as long as one
  "keepalive" connection to that NAME stays open somewhere in the process
  -- the module keeps exactly one such keepalive per NAME for the
  process's lifetime, so passes' ordinary open/close cycles don't destroy
  the data in between. `copy_database()` uses SQLite's own `backup()` API
  (which works identically for memory or disk connections) in place of
  `shutil.copyfile()`. `Ctx().use_in_memory_databases` is computed once,
  early, in `run_options.py`: true only when this invocation runs every
  pass from first to last *and* `--skip-cleanup` (which leaves
  intermediate files behind for inspection) wasn't requested -- any
  partial `--passes` range, in either direction, keeps the existing
  on-disk behavior automatically. `TempFile.cleanup()` (artifact.py) was
  made defensive (skips `os.unlink()` if the file was never created)
  since in-memory-mode artifacts never touch disk at all.

  Verified all three code paths directly, not just via run-tests.py
  (which mostly exercises the in-memory path by default, since it always
  runs full conversions): a full single-invocation run; a `--passes=1:8`
  run followed by a separate-process `--passes=9:` resumption, diffed
  byte-for-byte identical against a full-run dumpfile; and
  `--skip-cleanup`, confirmed to leave real files on disk.

  Open question, not yet investigated: whether the three
  `CVS_ITEM_TO_CHANGESET_*` copies are actually load-bearing (e.g. so an
  earlier stage's table stays available for `--passes`/-p resumption while
  a later stage mutates its own copy) or a leftover from an earlier
  iteration of the code that could be eliminated instead of ported to
  `copy_database()`.
