import Media, VideoFiles
import os.path, difflib, re

def compareFilenames(elem):
  return elem.parts[0].lower()

def Scan(dir, files, mediaList, subdirs):
  
  # Go through the files and see if any of them need to be stacked.
  stack_dict = {}
  stackDiffs = r'[\da-n]' # These are the characters we are looking for being different across stackable filenames
  stackSuffixes = r'(?:cd|dvd|part|pt|disk|disc|scene)\.?(?:\d+)?$'
  scenePrefixes = r'(?:^scene.\d+|scene.\d+$)'
  
  # Sort the mediaList by filename, so we can do our compares properly
  mediaList[:] = sorted(mediaList, key=compareFilenames)

  # group scene-based movie splits into a stack
  for mediaItem in mediaList:
    # if items were already stacked by other method, skip this attempt
    if hasattr(mediaItem, 'stacked') and mediaItem.stacked == True:
      continue

    f1 = os.path.basename(os.path.splitext(mediaItem.parts[0])[0]).lower()
    if re.match(scenePrefixes, f1):
      (name, year) = VideoFiles.CleanName(re.sub(scenePrefixes, '', f1))

      # TODO: Handle disparate multi-scene sets that are in a single root directory; 
      # this currently assumes all scenes within directory belong to same release
      root = '_scene'
      mediaItem.name = name

      stack_dict[root] = stack_dict[root] or []
      stack_dict[root].append(mediaItem)
      mediaItem.stacked = True

  # Search for prefix-based part names.
  count = 0
  for mediaItem in mediaList[:-1]:
    m1 = mediaList[count]
    m2 = mediaList[count + 1]

    # if items were already stacked by other method, skip this attempt
    if hasattr(m1, 'stacked') and m1.stacked == True:
      continue

    f1 = os.path.basename(m1.parts[0])
    f2 = os.path.basename(m2.parts[0])
    
    opcodes = difflib.SequenceMatcher(None, f1, f2).get_opcodes()
    if len(opcodes) == 3: # We only have one transform
      (tag, i1, i2, j1, j2) = opcodes[1]
      if tag == 'replace': # The transform is a replace
        if (i2-i1 == 1) and (j2-j1 == 1): # The transform is only one character
          if 1 in [c in f1[i1:i2].lower() for c in stackDiffs]: # That one character is 1-4 or a-d
            root = f1[:i1]
            xOfy = False
            if f1[i1+1:].lower().strip().startswith('of'): #check to see if this an x of y style stack, if so flag it
              xOfy = True
            #prefix = f1[:i1] + f1[i2:]
            #(root, ext) = os.path.splitext(prefix)
              
            # This is a special case for folders with multiple Volumes of a series (not a stacked movie) [e.g, Kill Bill Vol 1 / 2]
            if not root.lower().strip().endswith('vol') and not root.lower().strip().endswith('volume'): 
              
              # Strip any suffixes like CD, DVD.
              foundSuffix = False
              suffixMatch = re.search(stackSuffixes, root.lower().strip())

              if suffixMatch:
                root = root[0:-len(suffixMatch.group(0))].strip(' -')
                foundSuffix = True
              
              if foundSuffix or xOfy:
                # Replace the name, which probably had the suffix.
                (name, year) = VideoFiles.CleanName(root)
                mediaItem.name = name
                m1.stacked = True
                if stack_dict.has_key(root):
                  stack_dict[root].append(m2)
                  if count == len(mediaList) - 1:
                    m2.stacked = True
                else:
                  stack_dict[root] = [m1]
                  stack_dict[root].append(m2)
    count += 1
  
  # Now combine stacked parts
  for stack in stack_dict.keys():
    for media in stack_dict[stack][1:]:
      stack_dict[stack][0].parts.append(media.parts[0])
      mediaList.remove(media)
