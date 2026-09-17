# (Be in -*- python -*- mode.)
#
# ====================================================================
# Copyright (c) 2000-2008 CollabNet.  All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution.
#
# This software consists of voluntary contributions made by many
# individuals.  For exact contribution history, see the revision
# history and logs.
# ====================================================================

"""Classes to manage simple integer-keyed, integer-valued tables.

These map small, non-negative integers to integer values.  The
backing store is SQLite, which handles integer storage/retrieval and
random access natively, so (unlike the historical fixed-width binary
record file this module used to implement) no manual packing into
fixed-length byte strings is needed.  The Packer classes are kept only
so that existing call sites -- which construct e.g.
UnsignedIntegerPacker()/SignedIntegerPacker(empty_value) and pass it
to RecordTable() -- keep working unchanged; RecordTable itself now
distinguishes "never set" from "set" via real row presence/absence in
SQLite rather than via the packer's empty_value sentinel."""


import os

from cvs2svn_lib.common import DB_OPEN_READ
from cvs2svn_lib.common import DB_OPEN_WRITE
from cvs2svn_lib.common import DB_OPEN_NEW
from cvs2svn_lib.context import Ctx
from cvs2svn_lib import sqlite_connect


class Packer(object):
  def __init__(self, empty_value=None):
    self.empty_value = empty_value

  def pack(self, v):
    raise NotImplementedError()

  def unpack(self, s):
    raise NotImplementedError()


class StructPacker(Packer):
  def __init__(self, format, empty_value=None):
    Packer.__init__(self, empty_value=empty_value)
    self.format = format

  def pack(self, v):
    return v

  def unpack(self, v):
    return v


class UnsignedIntegerPacker(StructPacker):
  def __init__(self, empty_value=0):
    StructPacker.__init__(self, '=I', empty_value)


class SignedIntegerPacker(StructPacker):
  def __init__(self, empty_value=0):
    StructPacker.__init__(self, '=i', empty_value)


class FileOffsetPacker(Packer):
  """Unused now that IndexedDatabase no longer keeps a separate offset
  index (SQLite's own B-tree replaces it); kept only in case anything
  outside this module still imports it."""

  def __init__(self):
    Packer.__init__(self, 0)

  def pack(self, v):
    return v

  def unpack(self, s):
    return s


class RecordTableAccessError(RuntimeError):
  pass


class RecordTable(object):
  """A SQLite-backed map from small non-negative integers to integers."""

  # How many writes to allow before an intermediate commit:
  _COMMIT_INTERVAL = 10000

  def __init__(self, filename, mode, packer):
    self.filename = filename
    self.mode = mode
    self.packer = packer
    self._pending_writes = 0
    self._in_memory = Ctx().use_in_memory_databases

    if self.mode == DB_OPEN_NEW:
      if not self._in_memory and os.path.exists(filename):
        os.unlink(filename)
      self.db = sqlite_connect.connect(filename, self._in_memory)
      self.db.execute(
          'CREATE TABLE records (id INTEGER PRIMARY KEY, value INTEGER)'
          )
      self.db.commit()
    elif self.mode in (DB_OPEN_WRITE, DB_OPEN_READ):
      self.db = sqlite_connect.connect(filename, self._in_memory)
    else:
      raise RuntimeError('Invalid mode %r' % self.mode)

  def __str__(self):
    return '%s(%r)' % (self.__class__.__name__, self.filename,)

  def _maybe_commit(self):
    self._pending_writes += 1
    if self._pending_writes >= self._COMMIT_INTERVAL:
      self.db.commit()
      self._pending_writes = 0

  def __setitem__(self, i, v):
    if self.mode == DB_OPEN_READ:
      raise RecordTableAccessError()
    self.db.execute(
        'INSERT OR REPLACE INTO records (id, value) VALUES (?, ?)', (i, v)
        )
    self._maybe_commit()

  def __getitem__(self, i):
    """Return the item for index I.

    Raise KeyError if that item has never been set."""

    row = self.db.execute(
        'SELECT value FROM records WHERE id = ?', (i,)
        ).fetchone()
    if row is None:
      raise KeyError(i)
    return row[0]

  def get(self, i, default=None):
    try:
      return self[i]
    except KeyError:
      return default

  def get_many(self, indexes, default=None):
    """Yield (index, item) tuples for INDEXES in arbitrary order.

    Yield (index,default) for indices for which no item is defined."""

    indexes = list(indexes)
    found = {}
    CHUNK_SIZE = 500
    for start in range(0, len(indexes), CHUNK_SIZE):
      chunk = indexes[start:start + CHUNK_SIZE]
      placeholders = ','.join('?' * len(chunk))
      for (id, value) in self.db.execute(
          'SELECT id, value FROM records WHERE id IN (%s)' % (placeholders,),
          chunk,
          ):
        found[id] = value
    for i in indexes:
      yield (i, found.get(i, default))

  def __delitem__(self, i):
    """Delete the item for index I.

    Raise KeyError if that item has never been set."""

    if self.mode == DB_OPEN_READ:
      raise RecordTableAccessError()
    cursor = self.db.execute('DELETE FROM records WHERE id = ?', (i,))
    if cursor.rowcount == 0:
      raise KeyError(i)
    self._maybe_commit()

  def iterkeys(self):
    """Yield the keys in the map in key order."""

    for row in self.db.execute('SELECT id FROM records ORDER BY id'):
      yield row[0]

  def itervalues(self):
    """Yield the values in the map in key order."""

    for row in self.db.execute('SELECT value FROM records ORDER BY id'):
      yield row[0]

  def flush(self):
    self.db.commit()
    self._pending_writes = 0

  def close(self):
    self.db.commit()
    self.db.close()
    self.db = None


# SQLite makes the mmap-vs-buffered-file distinction of the old
# implementation moot; both names now refer to the same class.
MmapRecordTable = RecordTable
