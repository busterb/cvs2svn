# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2000-2009 CollabNet.  All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution.
#
# This software consists of voluntary contributions made by many
# individuals.  For exact contribution history, see the revision
# history and logs.
# ====================================================================

"""This module contains database facilities used by cvs2svn."""


import os
import sqlite3
import pickle

from cvs2svn_lib.common import DB_OPEN_READ
from cvs2svn_lib.common import DB_OPEN_WRITE
from cvs2svn_lib.common import DB_OPEN_NEW


class IndexedDatabase:
  """A store of objects indexed by small non-negative integers.

  This is a SQLite-backed replacement for the historical two-file
  design (a sequential pickle stream plus a hand-rolled offset-index
  file): SQLite's own B-tree already gives O(log n) random access by
  integer id, so the separate offset index is unnecessary, and one
  file replaces two.

  INDEX_FILENAME is accepted for compatibility with callers built
  around the old two-file layout (and so that artifact-manager's
  unconditional cleanup unlink() of that filename still succeeds); it
  is not otherwise used -- all data lives in the SQLite file at
  FILENAME."""

  # How many writes to allow before an intermediate commit, so that a
  # single pass's transaction doesn't grow unboundedly for very large
  # repositories:
  _COMMIT_INTERVAL = 10000

  def __init__(self, filename, index_filename, mode, serializer=None):
    self.filename = filename
    self.index_filename = index_filename
    self.mode = mode
    self._pending_writes = 0

    # index_filename is a vestige of the pre-SQLite two-file layout;
    # keep an (empty) marker file there so that artifact-manager's
    # cleanup, which unconditionally unlinks it, doesn't fail.
    if not os.path.exists(index_filename):
      open(index_filename, 'wb').close()

    if self.mode == DB_OPEN_NEW:
      if os.path.exists(self.filename):
        os.unlink(self.filename)
      self.db = sqlite3.connect(self.filename)
      self.db.execute(
          'CREATE TABLE items (id INTEGER PRIMARY KEY, data BLOB)'
          )
      self.db.execute(
          'CREATE TABLE meta (key TEXT PRIMARY KEY, value BLOB)'
          )
      assert serializer is not None
      self.serializer = serializer
      self.db.execute(
          'INSERT INTO meta (key, value) VALUES (?, ?)',
          ('serializer', pickle.dumps(self.serializer, -1)),
          )
      self.db.commit()
    elif self.mode in (DB_OPEN_WRITE, DB_OPEN_READ):
      self.db = sqlite3.connect(self.filename)
      row = self.db.execute(
          'SELECT value FROM meta WHERE key = ?', ('serializer',)
          ).fetchone()
      self.serializer = pickle.loads(row[0])
    else:
      raise RuntimeError('Invalid mode %r' % self.mode)

  def _maybe_commit(self):
    self._pending_writes += 1
    if self._pending_writes >= self._COMMIT_INTERVAL:
      self.db.commit()
      self._pending_writes = 0

  def __setitem__(self, index, item):
    """Write ITEM into the database indexed by INDEX."""

    self.db.execute(
        'INSERT OR REPLACE INTO items (id, data) VALUES (?, ?)',
        (index, self.serializer.dumps(item)),
        )
    self._maybe_commit()

  def _fetch(self, data):
    return self.serializer.loads(data)

  def iterkeys(self):
    for row in self.db.execute('SELECT id FROM items ORDER BY id'):
      yield row[0]

  def itervalues(self):
    for row in self.db.execute('SELECT data FROM items ORDER BY id'):
      yield self._fetch(row[0])

  def __getitem__(self, index):
    row = self.db.execute(
        'SELECT data FROM items WHERE id = ?', (index,)
        ).fetchone()
    if row is None:
      raise KeyError(index)
    return self._fetch(row[0])

  def get(self, item, default=None):
    try:
      return self[item]
    except KeyError:
      return default

  def get_many(self, indexes, default=None):
    """Yield (index,item) tuples for INDEXES, in arbitrary order.

    Yield (index,default) for indexes with no defined values."""

    indexes = list(indexes)
    found = {}
    # Chunk to stay under SQLite's default bound on the number of
    # parameters in a single statement:
    CHUNK_SIZE = 500
    for start in range(0, len(indexes), CHUNK_SIZE):
      chunk = indexes[start:start + CHUNK_SIZE]
      placeholders = ','.join('?' * len(chunk))
      for (id, data) in self.db.execute(
          'SELECT id, data FROM items WHERE id IN (%s)' % (placeholders,),
          chunk,
          ):
        found[id] = data

    for index in indexes:
      if index in found:
        yield (index, self._fetch(found[index]))
      else:
        yield (index, default)

  def __delitem__(self, index):
    cursor = self.db.execute('DELETE FROM items WHERE id = ?', (index,))
    if cursor.rowcount == 0:
      raise KeyError(index)
    self._maybe_commit()

  def close(self):
    self.db.commit()
    self.db.close()
    self.db = None

  def __str__(self):
    return 'IndexedDatabase(%r)' % (self.filename,)


class IndexedStore(IndexedDatabase):
  """A file of items that is written sequentially and read randomly.

  This is just like IndexedDatabase, except that it has an additional
  add() method which assumes that the object to be written to the
  database has an 'id' member, which is used as its database index.
  See IndexedDatabase for more information."""

  def add(self, item):
    """Write ITEM into the database indexed by ITEM.id."""

    self[item.id] = item
