import os

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
