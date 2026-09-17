# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2026 CollabNet.  All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution.
#
# This software consists of voluntary contributions made by many
# individuals.  For exact contribution history, see the revision
# history and logs.
# ====================================================================

"""Open SQLite connections that can optionally live purely in memory.

cvs2svn's intermediate databases (database.py, indexed_database.py,
record_table.py) are each opened, used, closed, and later reopened
(by the same process, a later pass) potentially several times over
the course of a conversion -- that's how passes hand data to each
other, and how --passes/-p resumption works across separate process
invocations. A plain "sqlite3.connect(':memory:')" can't support
that: each connection to ':memory:' gets its own private, empty
database, so a later reopen would see nothing that an earlier one
wrote.

SQLite's shared-cache in-memory mode ("file:NAME?mode=memory&cache=
shared") solves the same-process case: any number of connections that
name the same NAME see the same data, for as long as at least one
connection to that NAME stays open somewhere in the process. This
module keeps exactly one such "keepalive" connection alive per NAME,
for the process's whole lifetime, so that ordinary open/close cycles
by callers (each getting their own, independently closeable
connection to the same NAME) don't destroy the data in between.

This can never support --passes/-p resumption across separate
process invocations (there's nothing to hand off -- the whole point
is that nothing touches disk), so callers must only request in-memory
mode when they know this invocation will run start to finish; see
Ctx().use_in_memory_databases."""


import shutil
import sqlite3
from urllib.parse import quote


# One keepalive connection per NAME, kept open for this process's
# lifetime so that the shared in-memory database it names isn't
# dropped between callers' own open/close cycles:
_keepalive_connections = {}


def connect(filename, in_memory):
  """Return a new SQLite connection for FILENAME.

  If IN_MEMORY is true, the connection is backed purely by memory
  (see the module docstring for what that guarantees); FILENAME is
  used only as the in-memory database's name, never touched on disk.
  Otherwise, this is exactly sqlite3.connect(filename)."""

  if not in_memory:
    return sqlite3.connect(filename)

  uri = 'file:' + quote(filename, safe='') + '?mode=memory&cache=shared'
  if filename not in _keepalive_connections:
    _keepalive_connections[filename] = sqlite3.connect(uri, uri=True)
  return sqlite3.connect(uri, uri=True)


def copy_database(src_filename, dst_filename, in_memory):
  """Copy the whole database at SRC_FILENAME to DST_FILENAME.

  A handful of passes need an independent copy of a database to
  mutate separately from the original (e.g. so an earlier pass's
  output stays available for --passes/-p resumption while a later
  pass works on its own copy). For on-disk databases that's a plain
  file copy; IN_MEMORY databases have no file to copy, so use
  SQLite's own backup API instead, which works the same way for
  either kind of connection. DST_FILENAME must not already name an
  existing (non-empty) database of either kind."""

  if not in_memory:
    shutil.copyfile(src_filename, dst_filename)
    return

  src_conn = connect(src_filename, True)
  dst_conn = connect(dst_filename, True)
  try:
    src_conn.backup(dst_conn)
  finally:
    src_conn.close()
    dst_conn.close()
