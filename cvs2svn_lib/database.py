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

from cvs2svn_lib.common import DB_OPEN_NEW


class Database:
  """A key-value database that uses a Serializer to store objects.

  The serializer is stored in the database under self.serializer_key.
  (This implies that self.serializer_key may not be used as a key for
  normal entries.)

  The backing store is a single SQLite database file, opened in
  autocommit-free mode: writes accumulate in the current transaction
  and are made durable by close() (or periodically, to bound how much
  uncommitted data a single pass can accumulate)."""

  serializer_key = '_.%$1\t;_ '

  # How many writes to allow before an intermediate commit, so that a
  # single pass's transaction doesn't grow unboundedly for very large
  # repositories:
  _COMMIT_INTERVAL = 10000

  def __init__(self, filename, mode, serializer=None):
    """Constructor.

    The database stores its Serializer, so none needs to be supplied
    when opening an existing database."""

    self.filename = filename
    self.mode = mode
    self._pending_writes = 0

    if mode == DB_OPEN_NEW:
      if os.path.exists(filename):
        os.unlink(filename)
      self.db = sqlite3.connect(filename)
      self.db.execute(
          'CREATE TABLE kv (key BLOB PRIMARY KEY, value BLOB)'
          )
      self.serializer = serializer
      self.db.execute(
          'INSERT INTO kv (key, value) VALUES (?, ?)',
          (self.serializer_key, pickle.dumps(self.serializer, -1)),
          )
      self.db.commit()
    else:
      self.db = sqlite3.connect(filename)
      row = self.db.execute(
          'SELECT value FROM kv WHERE key = ?', (self.serializer_key,)
          ).fetchone()
      self.serializer = pickle.loads(row[0])

  def _maybe_commit(self):
    self._pending_writes += 1
    if self._pending_writes >= self._COMMIT_INTERVAL:
      self.db.commit()
      self._pending_writes = 0

  def __getitem__(self, key):
    row = self.db.execute(
        'SELECT value FROM kv WHERE key = ?', (key,)
        ).fetchone()
    if row is None:
      raise KeyError(key)
    return self.serializer.loads(row[0])

  def __setitem__(self, key, value):
    self.db.execute(
        'INSERT OR REPLACE INTO kv (key, value) VALUES (?, ?)',
        (key, self.serializer.dumps(value)),
        )
    self._maybe_commit()

  def __delitem__(self, key):
    cursor = self.db.execute('DELETE FROM kv WHERE key = ?', (key,))
    if cursor.rowcount == 0:
      raise KeyError(key)
    self._maybe_commit()

  def keys(self):
    return [
        row[0]
        for row in self.db.execute(
            'SELECT key FROM kv WHERE key != ?', (self.serializer_key,)
            )
        ]

  def __iter__(self):
    for key in self.keys():
      yield key

  def has_key(self, key):
    row = self.db.execute(
        'SELECT 1 FROM kv WHERE key = ?', (key,)
        ).fetchone()
    return row is not None

  def __contains__(self, key):
    return self.has_key(key)

  def iterkeys(self):
    return self.__iter__()

  def clear(self):
    self.db.execute('DELETE FROM kv WHERE key != ?', (self.serializer_key,))
    self._maybe_commit()

  def items(self):
    return [(key, self[key],) for key in self.keys()]

  def values(self):
    return [self[key] for key in self.keys()]

  def get(self, key, default=None):
    try:
      return self[key]
    except KeyError:
      return default

  def close(self):
    self.db.commit()
    self.db.close()
    self.db = None
