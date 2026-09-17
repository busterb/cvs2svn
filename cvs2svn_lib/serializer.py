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

"""Serializers used to persist objects to cvs2svn's intermediate files."""


import marshal
import pickle
import zlib


class Serializer:
  """An object able to serialize/deserialize some class of objects."""

  def dumpf(self, f, object):
    """Serialize OBJECT to file-like object F."""

    raise NotImplementedError()

  def dumps(self, object):
    """Return a string containing OBJECT in serialized form."""

    raise NotImplementedError()

  def loadf(self, f):
    """Return the next object deserialized from file-like object F."""

    raise NotImplementedError()

  def loads(self, s):
    """Return the object deserialized from string S."""

    raise NotImplementedError()


class MarshalSerializer(Serializer):
  """This class uses the marshal module to serialize/deserialize.

  This means that it shares the limitations of the marshal module,
  namely only being able to serialize a few simple python data types
  without reference loops."""

  def dumpf(self, f, object):
    marshal.dump(object, f)

  def dumps(self, object):
    return marshal.dumps(object)

  def loadf(self, f):
    return marshal.load(f)

  def loads(self, s):
    return marshal.loads(s)


class PickleSerializer(Serializer):
  """A Serializer that uses plain pickle, with the C accelerator.

  This module used to also have a PrimedPickleSerializer, which
  "primed" a pickler/unpickler's memo with a set of classes expected
  to recur often (e.g. the handful of CVSItem subclasses), so that
  only a short backreference needed to be written instead of a full
  class reference each time. Priming required manually assigning a
  pre-built memo dict, which only the pure-Python pickle._Pickler/
  _Unpickler support (the C implementation's memo is a proxy that
  can't be repopulated from a plain dict). Profiling a large
  conversion showed CVSItem (de)serialization dominating total
  runtime; a microbenchmark shaped like the actual hot path (one
  small object per dumpf()/loadf() call) showed plain C-accelerated
  pickle is ~5.6x faster to dump and ~6.5x faster to load than the
  primed pure-Python path, despite the primed format's smaller
  per-item size -- the C implementation resolving a class reference
  from scratch each time is still far cheaper than running the whole
  pickle protocol in pure Python. PrimedPickleSerializer was removed
  once every caller was confirmed to only ever prime with classes
  (stable for a process's whole lifetime), never instances (which
  would need care around id() reuse after garbage collection)."""

  def dumpf(self, f, object):
    pickle.dump(object, f, pickle.HIGHEST_PROTOCOL)

  def dumps(self, object):
    return pickle.dumps(object, pickle.HIGHEST_PROTOCOL)

  def loadf(self, f):
    return pickle.load(f)

  def loads(self, s):
    return pickle.loads(s)


class CompressingSerializer(Serializer):
  """This class wraps other Serializers to compress their serialized data."""

  def __init__(self, wrapee):
    """Constructor.  WRAPEE is the Serializer whose bitstream ought to be
    compressed."""

    self.wrapee = wrapee

  def dumpf(self, f, object):
    marshal.dump(zlib.compress(self.wrapee.dumps(object), 9), f)

  def dumps(self, object):
    return marshal.dumps(zlib.compress(self.wrapee.dumps(object), 9))

  def loadf(self, f):
    return self.wrapee.loads(zlib.decompress(marshal.load(f)))

  def loads(self, s):
    return self.wrapee.loads(zlib.decompress(marshal.loads(s)))


