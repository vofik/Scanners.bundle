import os
from urllib import urlopen, urlencode
import UnicodeHelper

# Platform-safe function to split a path into a list of path elements.
def SplitPath(path, maxdepth=20):
    (head, tail) = os.path.split(path)
    if maxdepth and head and head != path:
        return SplitPath(head, maxdepth - 1) + [tail]
    else:
        return [head or tail]

# Check for a given filename in a list of full paths.
def ContainsFile(files, file):
  for i in files:
    if os.path.basename(i).lower() == file.lower():
      return i
  return None

# Sparse list allows setting/accessing arbitrary indices.
class SparseList(list):
  def __setitem__(self, index, value):
    missing = index - len(self) + 1
    if missing > 0:
      self.extend([None] * missing)
    list.__setitem__(self, index, value)
  def __getitem__(self, index):
    try: return list.__getitem__(self, index)
    except IndexError: return None

# Log to PMS log.
def Log(message, level=3, source='Scanners.bundle'):
  args = urlencode({'message' : UnicodeHelper.toBytes(message), 'level' : level, 'source' : source})
  res = urlopen('http://127.0.0.1:32400/log?%s' % args)