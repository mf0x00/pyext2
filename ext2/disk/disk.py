#!/usr/bin/env python
"""
Defines the disk class used by the ext2 module.
"""
__license__ = "BSD"
__copyright__ = "Copyright 2013, Michael R. Falcone"


import re
import inspect
from Queue import Queue
from struct import unpack, unpack_from
from os import fsync
from ..error import *
from ..file import Ext2File
from .superblock import _Superblock
from .bgdt import _BGDT


class InformationReport(object):
  """Structure used to return information about the filesystem."""
  pass


class Ext2Disk(object):
  """Models a disk image file formatted to the Ext2 filesystem."""
  
  
  class __Inode:
    pass
  
  
  # PROPERTIES -------------------------------------------------
  
  @property
  def fsType(self):
    """Gets a string representing the filesystem type. Always EXT2."""
    return "EXT2"
  
  @property
  def revision(self):
    """Gets the filesystem revision string formatted as MAJOR.MINOR."""
    assert self.isValid, "Filesystem is not valid."
    return "{0}.{1}".format(self._superblock.revisionMajor, self._superblock.revisionMinor)
  
  @property
  def totalSpace(self):
    """Gets the total filesystem size in bytes."""
    assert self.isValid, "Filesystem is not valid."
    return self._superblock.blockSize * self._superblock.numBlocks
  
  @property
  def freeSpace(self):
    """Gets the number of free bytes."""
    assert self.isValid, "Filesystem is not valid."
    return self._superblock.blockSize * self._superblock.numFreeBlocks
  
  @property
  def usedSpace(self):
    """Gets the number of used bytes."""
    assert self.isValid, "Filesystem is not valid."
    return self.totalSpace - self.freeSpace
  
  @property
  def blockSize(self):
    """Gets the block size in bytes."""
    assert self.isValid, "Filesystem is not valid."
    return self._superblock.blockSize
  
  @property
  def numBlockGroups(self):
    """Gets the number of block groups."""
    assert self.isValid, "Filesystem is not valid."
    return len(self._bgroupDescTable.entries)
  
  @property
  def numInodes(self):
    """Gets the total number of inodes."""
    assert self.isValid, "Filesystem is not valid."
    return self._superblock.numInodes
  
  @property
  def rootDir(self):
    """Gets the file object representing the root directory."""
    assert self.isValid, "Filesystem is not valid."
    return self._rootDir

  @property
  def isValid(self):
    """Gets whether the disk's filesystem is valid and mounted."""
    return self._isValid
  
  
  
  
  # LIFECYCLE METHODS ------------------------------------
  
  def __init__(self, imageFilename):
    """Constructs a new Ext2 disk from the specified image filename."""
    self._imageFile = None
    self._imageFilename = imageFilename
    self._isValid = False
  
  def __del__(self):
    """Destructor that unmounts the filesystem if it has not been unmounted."""
    if self._imageFile:
      self.unmount()
  
  def __enter__ (self):
    """Mounts the filesystem and returns the root directory."""
    self.mount()
    return self.rootDir

  def __exit__ (self, type, value, tb):
    """Unmounts the filesystem and re-raises any exception that occurred."""
    self.unmount()
  
  
  
  def mount(self):
    """Mounts the Ext2 disk for reading and writing and reads the root directory. Raises an
    InvalidImageFormatError if the root directory cannot be read."""
    self._imageFile = open(self._imageFilename, "r+b")
    try:
      self._superblock = _Superblock.read(1024, self._imageFile)
      self._bgroupDescTable = _BGDT.read(0, self._superblock, self._imageFile)
      self._isValid = True
      self._rootDir = Ext2File("", None, 2, self)
    except:
      if self._imageFile:
        self._imageFile.close()
      self._imageFile = None
      self._isValid = False
      raise InvalidImageFormatError()
  
  
  
  def unmount(self):
    """Unmounts the Ext2 disk so that reading and writing may no longer occur, and closes
    access to the disk image file."""
    if self._imageFile:
      self._imageFile.flush()
      fsync(self._imageFile.fileno())
      self._imageFile.close()
    self._imageFile = None
    self._isValid = False
  
  
  
  
  
  # PUBLIC METHODS ------------------------------------
  
  
  def getFile(self, absolutePath):
    """Looks up and returns the file specified by the absolute path. Raises a
    FileNotFoundError if the file object cannot be found."""
    assert self.isValid, "Filesystem is not valid."
    
    pathParts = re.compile("/+").split(absolutePath)
    if len(pathParts) == 0:
      raise FileNotFoundError()
    if not pathParts[0] == "":
      raise FileNotFoundError()
    
    if len(pathParts) > 1 and pathParts[-1] == "":
      del pathParts[-1]
    localName = pathParts[-1]
    fileObject = self._rootDir
    del pathParts[0]
    for localPath in pathParts:
      if not fileObject.isDir:
        break
      for f in fileObject.listContents():
        if f.name == localPath:
          fileObject = f
          break
    
    if not fileObject.name == localName:
      raise FileNotFoundError()
    
    return fileObject
  
  
  
  def makeDirFile(self, absolutePath):
    """Creates a new directory on the filesystem and returns its file object."""
    assert self.isValid, "Filesystem is not valid."
    
    # make sure destination does not already exist
    destExists = True
    try:
      self.getFile(absolutePath)
    except FileNotFoundError:
      destExists = False
    if destExists:
      raise FileAlreadyExistsError()
    
    # find parent directory and add an entry for the file
    pathParts = re.compile("/+").split(absolutePath)
    if len(pathParts) == 0:
      raise FileNotFoundError()
    if not pathParts[0] == "":
      raise FileNotFoundError()
    if len(pathParts) > 1 and pathParts[-1] == "":
      del pathParts[-1]
    
    fileName = pathParts[-1]
    parentPath = "/{0}".format("/".join(pathParts[:-1]))
    parentDir = self.getFile(parentPath)
    
    
    # TODO allocate inode
    print parentDir.absolutePath
    print fileName
  
  
  
  def makeRegularFile(self, absolutePath):
    """Creates a new regular file on the filesystem and returns its file object."""
    assert self.isValid, "Filesystem is not valid."
    pass
  
  
  
  def makeLink(self, absolutePath, linkedFile, isSymbolic):
    """Creates a new link to the specified file object and returns the link file object."""
    assert self.isValid, "Filesystem is not valid."
    pass
  
  
  
  def scanBlockGroups(self):
    """Scans all block groups and returns an information report about them."""
    assert self.isValid, "Filesystem is not valid."
    
    report = InformationReport()
    
    # count files and directories
    report.numRegFiles = 0
    report.numSymlinks = 0
    report.numDirs = 1 # initialize with root directory
    q = Queue()
    q.put(self.rootDir)
    while not q.empty():
      dir = q.get()
      for f in dir.listContents():
        if f.name == "." or f.name == "..":
          continue
        if f.isDir:
          report.numDirs += 1
          q.put(f)
        elif f.isRegular:
          report.numRegFiles += 1
        elif f.isSymlink:
          report.numSymlinks += 1
    
    # report block group information
    report.groupReports = []
    for i,entry in enumerate(self._bgroupDescTable.entries):
      groupReport = InformationReport()
      groupReport.numFreeBlocks = entry.numFreeBlocks
      groupReport.numFreeInodes = entry.numFreeInodes
      report.groupReports.append(groupReport)
    
    return report
  
  
  
  
  def checkIntegrity(self):
    """Evaluates the integrity of the filesystem and returns an information report."""
    assert self.isValid, "Filesystem is not valid."
    
    report = InformationReport()
    
    # basic integrity checks
    report.hasMagicNumber = self._superblock.isValidExt2
    report.numSuperblockCopies = len(self._superblock.copyLocations)
    report.copyLocations = list(self._superblock.copyLocations)
    report.messages = []
    
    
    # check consistency across superblock/group table copies
    sbMembers = dict(inspect.getmembers(self._superblock))
    bgtMembersEntries = map(dict, map(inspect.getmembers, self._bgroupDescTable.entries))
    for groupId in self._superblock.copyLocations:
      if groupId == 0:
        continue
      
      # evaluate superblock copy consistency
      try:
        startPos = 1024 + groupId * self._superblock.numBlocksPerGroup * self._superblock.blockSize
        sbCopy = _Superblock.read(startPos, self._imageFile)
        sbCopyMembers = dict(inspect.getmembers(sbCopy))
      except:
        report.messages.append("Superblock at block group {0} could not be read.".format(groupId))
        continue
      for m in sbMembers:
        if m.startswith("_"):
          continue
        if not m in sbCopyMembers:
          report.messages.append("Superblock at block group {0} has missing field '{1}'.".format(groupId, m))
        elif not sbCopyMembers[m] == sbMembers[m]:
          report.messages.append("Superblock at block group {0} has inconsistent field '{1}' with value '{2}' (primary value is '{3}').".format(groupId, m, sbCopyMembers[m], sbMembers[m]))
      
      # evaluate block group descriptor table consistency
      try:
        bgtCopy = _BGDT.read(groupId, self._superblock, self._imageFile)
        bgtCopyMembersEntries = map(dict, map(inspect.getmembers, bgtCopy.entries))
      except:
        report.messages.append("Block group descriptor table at block group {0} could not be read.".format(groupId))
        continue
      if len(bgtCopyMembersEntries) != len(bgtMembersEntries):
        report.messages.append("Block group descriptor table at block group {0} has {1} entries while primary has {2}.".format(groupId, len(bgtCopyMembersEntries), len(bgtMembersEntries)))
        continue
      for entryNum in range(len(bgtMembersEntries)):
        bgtPrimaryEntryMembers = bgtMembersEntries[entryNum]
        bgtCopyEntryMembers = bgtCopyMembersEntries[entryNum]
        for m in bgtPrimaryEntryMembers:
          if m.startswith("_"):
            continue
          if not m in bgtCopyEntryMembers:
            report.messages.append("Block group descriptor table entry {0} at block group {1} has missing field '{2}'.".format(entryNum, groupId, m))
          elif not bgtCopyEntryMembers[m] == bgtPrimaryEntryMembers[m]:
            report.messages.append("Block group descriptor table entry {0} at block group {1} has inconsistent field '{2}' with value '{3}' (primary value is '{4}').".format(entryNum, groupId, m, bgtCopyEntryMembers[m], bgtPrimaryEntryMembers[m]))
    
    
    # validate inode and block references
    inodes = self.__getUsedInodes()
    inodesReachable = dict(zip(inodes, [False] * len(inodes)))
    blocks = self.__getUsedBlocks()
    blocksAccessedBy = dict(zip(blocks, [None] * len(blocks)))
    
    q = Queue()
    q.put(self.rootDir)
    while not q.empty():
      dir = q.get()
      for f in dir.listContents():
        if f.name == "." or f.name == "..":
          continue
        if f.isDir:
          q.put(f)
        
        # check inode references
        if not (f.isValid and f.inodeNum in inodesReachable):
          report.messages.append("The filesystem contains an entry for {0} but its inode is not marked as used (inode number {1}).".format(f.absolutePath, f.inodeNum))
        else:
          inodesReachable[f.inodeNum] = True
        
        # check block references
        for bid in f._getUsedBlocks():
          if not bid in blocksAccessedBy:
            report.messages.append("The file {0} is referencing a block that is not marked as used by the filesystem (block id: {1})".format(f.absolutePath, bid))
          elif blocksAccessedBy[bid]:
            report.messages.append("Block id {0} is being referenced by both {1} and {2}.".format(bid, blocksAccessedBy[bid], f.absolutePath))
          else:
            blocksAccessedBy[bid] = f.absolutePath
    
    for inodeNum in inodesReachable:
      if not inodesReachable[inodeNum]:
        report.messages.append("Inode number {0} is marked as used but is not reachable from a directory entry.".format(inodeNum))
    
    return report
  
  
  
  
  # PRIVATE METHODS ------------------------------------
  
  def __getUsedInodes(self):
    """Returns a list of all used inode numbers, excluding those reserved by the
    filesystem."""
    used = []
    bitmaps = []
    for bgroupDescEntry in self._bgroupDescTable.entries:
      bitmapStartPos = bgroupDescEntry.inodeBitmapLocation * self._superblock.blockSize
      bitmapSize = self._superblock.numInodesPerGroup / 8
      self._imageFile.seek(bitmapStartPos)
      bitmapBytes = self._imageFile.read(bitmapSize)
      if len(bitmapBytes) < bitmapSize:
        raise Exception("Invalid inode bitmap.")
      bitmaps.append(unpack("{0}B".format(bitmapSize), bitmapBytes))
    
    for groupNum,bitmap in enumerate(bitmaps):
      for byteIndex, byte in enumerate(bitmap):
        if byte != 0:
          for i in range(8):
            if (1 << i) & byte != 0:
              inum = (groupNum * self._superblock.numInodesPerGroup) + (byteIndex * 8) + i + 1
              if inum >= self._superblock.firstInode:
                used.append(inum)
    
    return used
  
  
  
  
  def _readInode(self, inodeNum):
    """Reads the specified inode."""
    bgroupNum = (inodeNum - 1) / self._superblock.numInodesPerGroup
    bgroupIndex = (inodeNum - 1) % self._superblock.numInodesPerGroup
    bgroupDescEntry = self._bgroupDescTable.entries[bgroupNum]
    
    bitmapStartPos = bgroupDescEntry.inodeBitmapLocation * self._superblock.blockSize
    bitmapByteIndex = bgroupIndex / 8
    usedTest = 1 << (bgroupIndex % 8)
    
    tableStartPos = bgroupDescEntry.inodeTableLocation * self._superblock.blockSize
    inodeStartPos = tableStartPos + (bgroupIndex * self._superblock.inodeSize)

    self._imageFile.seek(bitmapStartPos + bitmapByteIndex)
    bitmapByte = unpack("B", self._imageFile.read(1))[0]
    self._imageFile.seek(inodeStartPos)
    inodeBytes = self._imageFile.read(self._superblock.inodeSize)
    if len(inodeBytes) < self._superblock.inodeSize:
      raise Exception("Invalid inode.")
    
    if self._superblock.revisionMajor == 0:
      fields = unpack_from("<2Hi4IHh4xI4x15I", inodeBytes)
    else:
      fields = unpack_from("<2H5IHh4xI4x15I8xI", inodeBytes)
    
    if self._superblock.creatorOS == "LINUX":
      osFields = unpack_from("<4x2H", inodeBytes, 116)
    elif self._superblock.creatorOS == "HURD":
      osFields = unpack_from("<2x3H", inodeBytes, 116)
    
    inode = self.__Inode()
    inode.num = inodeNum
    inode.used = (bitmapByte & usedTest != 0)
    inode.mode = fields[0]
    inode.uid = fields[1]
    inode.size = fields[2]
    inode.time_accessed = fields[3]
    inode.time_created = fields[4]
    inode.time_modified = fields[5]
    inode.time_deleted = fields[6]
    inode.gid = fields[7]
    inode.num_links = fields[8]
    inode.flags = fields[9]
    inode.blocks = []
    for i in range(15):
      inode.blocks.append(fields[10+i])
    if self._superblock.revisionMajor > 0:
      inode.size |= (fields[25] << 32)
    if self._superblock.creatorOS == "LINUX":
      inode.uid |= (osFields[0] << 16)
      inode.gid |= (osFields[1] << 16)
    elif self._superblock.creatorOS == "HURD":
      inode.mode |= (osFields[0] << 16)
      inode.uid |= (osFields[1] << 16)
      inode.gid |= (osFields[2] << 16)
    
    return inode
  
  
  
  
  
  def __getUsedBlocks(self):
    """Returns a list off all block ids currently in use by the filesystem."""
    used = []
    bitmaps = []
    for bgroupDescEntry in self._bgroupDescTable.entries:
      bitmapStartPos = bgroupDescEntry.blockBitmapLocation * self._superblock.blockSize
      bitmapSize = self._superblock.numBlocksPerGroup / 8
      self._imageFile.seek(bitmapStartPos)
      bitmapBytes = self._imageFile.read(bitmapSize)
      if len(bitmapBytes) < bitmapSize:
        raise Exception("Invalid block bitmap.")
      bitmaps.append(unpack("{0}B".format(bitmapSize), bitmapBytes))
        
    for groupNum,bitmap in enumerate(bitmaps):
      for byteIndex, byte in enumerate(bitmap):
        if byte != 0:
          for i in range(8):
            if (1 << i) & byte != 0:
              bid = (groupNum * self._superblock.numBlocksPerGroup) + (byteIndex * 8) + i + 1
              used.append(bid)
    
    return used
    
  
  
  
  
  def _readBlock(self, blockId):
    """Reads the entire block specified by the given block id."""
    self._imageFile.seek(blockId * self._superblock.blockSize)
    bytes = self._imageFile.read(self._superblock.blockSize)
    if len(bytes) < self._superblock.blockSize:
      raise Exception("Invalid block.")
    return bytes
  
  
  
  
  def _allocateInode(self, isForDirectory):
    """Finds the first free inode, marks it as used, and returns the inode number."""
    bitmapStartPos = None
    bgroupNum = 0
    bitmapSize = self._superblock.numInodesPerGroup / 8
    
    for bgroupNum, bgroupDescEntry in enumerate(self._bgroupDescTable.entries):
      if bgroupDescEntry.num_free_inodes > 0:
        bitmapStartPos = bgroupDescEntry.inodeBitmapLocation * self._superblock.blockSize
        break
    if bitmapStartPos is None:
      raise Exception("No free inodes.")

    self._imageFile.seek(bitmapStartPos)
    bitmapBytes = self._imageFile.read(bitmapSize)
    if len(bitmapBytes) < bitmapSize:
      raise Exception("Invalid inode bitmap.")
    
    bitmap = unpack("{0}B".format(bitmapSize), bitmapBytes)
    for byteIndex, byte in enumerate(bitmap):
      if byte != 255:
        for i in range(8):
          if (1 << i) & byte == 0:
            inum = (bgroupNum * self._superblock.numInodesPerGroup) + (byteIndex * 8) + i + 1
            self._imageFile.seek(bitmapStartPos + byteIndex)
            self._imageFile.write(byte | (1 << i))
            # TODO mark as used, update bgdt, superblock
  



