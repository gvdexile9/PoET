#   Copyright 2012 J.C. Moyer
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

import struct
import io

class File:
  """
  Represents a GGPK file.
  """
  def __init__(self):
    self.fd = None

  def __init__(self, filename):
    self.fd     = open(filename, 'rb')
    self.header = FileHeader.read(self.fd)
    self.__read_fs()

  def __enter__(self):
    return self

  def __exit__(self, type, value, traceback):
    self.fd.close()

  def __read_fs(self):
    self.fd.seek(self.header.rootoffs)
    self.__root_dir = _read_entry(self.fd)

  def root(self):
    return self.__root_dir

  def extract(self, file):
    self.fd.seek(file.where[0])
    return self.fd.read(file.where[1])

class FileHeader:
  """
  Contains information regarding a GGPK archive file.
  """
  # Version U32 | Identifier 'GGPK' | Unknown U32 | Root offset U64 | Unknown U64
  __struct = struct.Struct('<I4sIQQ')

  def __init__(self, version, identifier, rootoffs):
    self.version    = version
    self.identifier = identifier
    self.rootoffs   = rootoffs

  @staticmethod
  def read(f):
    buf = f.read(FileHeader.__struct.size)
    version, identifier, _, rootoffs, _ = FileHeader.__struct.unpack_from(buf)
    return FileHeader(version, identifier, rootoffs)

class ChildPointer:
  def __init__(self, fd, where):
    self.fd    = fd
    self.where = where

  def read(self):
    self.fd.seek(self.where)
    return _read_entry(self.fd)

class DirectoryEntry:
  """
  Represents a virtual directory in a GGPK archive file.
  """
  def __init__(self, name, children):
    self.name     = name
    self.children = children

  def __iter__(self):
    for child in self.children:
      yield child.read()

class FileEntry:
  """
  Represents a virtual file entry in a GGPK archive file.
  """
  def __init__(self, name, where):
    """
    Creates a FileEntry given a name and pointer to the actual file data.

    where must be a 2-tuple containing (offset, size).
    """
    self.name  = name
    self.where = where

def _decode_str(s):
  return s.decode('utf16')

def _read_struct(fd, s):
  buf = fd.read(s.size)
  return s.unpack_from(buf)

# Struct that represents PDIR data.
# Name length U32 | Child count U32
_pdir_info_struct = struct.Struct('<iI')
# Struct that points to PDIR children.
# Checksum U32    | Child offset U64
_pdir_child_struct = struct.Struct('<IQ')
def _read_pdir(fd):
  namesize, childcount = _read_struct(fd, _pdir_info_struct)
  # 0x20 bytes that I don't know, but they seem unimportant
  fd.seek(0x20, 1)
  # Read name
  name = fd.read(namesize * 2)
  name = _decode_str(name).rstrip('\x00')
  # Read children
  children = []
  for n in range(childcount):
    _, childoffs = _read_struct(fd, _pdir_child_struct)
    nextpos = fd.tell()
    # Read the child right now
    fd.seek(childoffs)
    # Layer of indirection to implement laziness
    children.append(ChildPointer(fd, childoffs))
    fd.seek(nextpos)
  return DirectoryEntry(name, children)

# Struct that describes the filename length.
# Name length U32
_file_info_struct = struct.Struct('<i')
def _read_file(fd, nextoffs):
  namesize = _read_struct(fd, _file_info_struct)[0]
  # 0x20 unknown bytes
  fd.seek(0x20, 1)
  name = fd.read(namesize * 2)
  name = _decode_str(name).rstrip('\x00')
  # Everything from here to the next offset is file data.
  offs = fd.tell()
  size = nextoffs - offs
  return FileEntry(name, (offs, size))

# Entry header struct
# Next offset U32 | Type String 32
_entry_struct = struct.Struct('<I4s')
def _read_entry(fd):
  curoffs = fd.tell()
  nextoffs, ent_type = _read_struct(fd, _entry_struct)
  if ent_type == b'PDIR':
    return _read_pdir(fd)
  elif ent_type == b'FILE':
    return _read_file(fd, curoffs + nextoffs)
  elif ent_type == b'FREE':
    return None

