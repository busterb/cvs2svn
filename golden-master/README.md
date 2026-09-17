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
