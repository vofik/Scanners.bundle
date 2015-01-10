import os, re, string
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

# Log to PMS log.
def Log(message, level=3, source='Scanners.bundle'):
  args = urlencode({'message' : UnicodeHelper.toBytes(message), 'level' : level, 'source' : source})
  res = urlopen('http://127.0.0.1:32400/log?%s' % args)
  
# Cleanup string.
def CleanUpString(s):
  s = unicode(s)

  # Ands.
  s = s.replace('&', 'and')

  # Pre-process the string a bit to remove punctuation.
  s = re.sub('[' + string.punctuation + ']', '', s)
  
  # Lowercase it.
  s = s.lower()
  
  # Strip leading "the/a"
  s = re.sub('^(the|a) ', '', s)
  
  # Spaces.
  s = re.sub('[ ]+', ' ', s).strip()
    
  return s
  
# Compute Levenshtein distance.
def LevenshteinDistance(first, second):
  first = CleanUpString(first)
  second = CleanUpString(second)
  
  if len(first) > len(second):
    first, second = second, first
  if len(second) == 0:
    return len(first)
  first_length = len(first) + 1
  second_length = len(second) + 1
  distance_matrix = [[0] * second_length for x in range(first_length)]
  for i in range(first_length):
    distance_matrix[i][0] = i
  for j in range(second_length):
    distance_matrix[0][j]=j
  for i in xrange(1, first_length):
    for j in range(1, second_length):
      deletion = distance_matrix[i-1][j] + 1
      insertion = distance_matrix[i][j-1] + 1
      substitution = distance_matrix[i-1][j-1]
      if first[i-1] != second[j-1]:
        substitution = substitution + 1
      distance_matrix[i][j] = min(insertion, deletion, substitution)
  return distance_matrix[first_length-1][second_length-1]

# Levenshtein ratio.
def LevenshteinRatio(first, second):
  return 1 - (LevenshteinDistance(first, second) / float(max(len(first), len(second))))
