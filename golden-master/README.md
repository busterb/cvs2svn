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
