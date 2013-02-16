#!/usr/bin/env python
"""
Driver application for interfacing with a filesystem image that can generate
information about the filesystem and enter an interactive shell.
"""
__license__ = "BSD"
__copyright__ = "Copyright 2013, Michael R. Falcone"

import sys
import os
from time import clock
from time import sleep
from threading import Thread
from Queue import Queue
from ext2 import *


class FilesystemNotSupportedError(Exception):
  """Thrown when the image's filesystem type is not supported."""
  pass


class WaitIndicatorThread(Thread):
  """Shows a wait indicator for the current action. If maxProgress is set then a
  percentage towards completion is shown instead."""
  done = False
  progress = 0
  maxProgress = 0
  
  def __init__(self, msg):
    Thread.__init__(self)
    self._msg = msg
  
  def run(self):
    """Prints and updates the wait indicator until done becomes True."""
    lastProgress = None
    indpos = 0
    ind = ["-", "\\", "|", "/"]
    while not self.done:
      if self.maxProgress == 0:
        sys.stdout.write("\r")
        sys.stdout.write(self._msg)
        sys.stdout.write(" ")
        sys.stdout.write(ind[indpos])
        sys.stdout.flush()
        indpos = (indpos + 1) % 4
      else:
        if self.progress != lastProgress:
          sys.stdout.write("\r")
          sys.stdout.write(self._msg)
          sys.stdout.write(" ")
          sys.stdout.write("{0:.0f}%".format(float(self.progress) / self.maxProgress * 100))
          sys.stdout.flush()
          lastProgress = self.progress
      sleep(0.03)
    sys.stdout.write("\r")
    sys.stdout.write(self._msg)
    sys.stdout.write(" Done.")
    sys.stdout.flush()
    print




# ========= DISK INFORMATION ==============================================

def printInfoPairs(pairs):
  """Prints the info strings stored in a list of pairs, justified."""
  maxLeftLen = 0
  for p in pairs:
    if len(p[0]) > maxLeftLen:
      maxLeftLen = len(p[0])
  for p in pairs:
    if p[1]:
      if isinstance(p[1], list):
        print "{0}:".format(p[0])
        for message in p[1]:
          print "- {0}".format(message)
      else:
        print "{0}{1}".format(p[0].ljust(maxLeftLen+5, "."), p[1])
    else:
      print
      print p[0]
  print



def getGeneralInfo(disk):
  """Gets general information about the disk and generates a list of information pairs."""
  pairs = []
  if disk.fsType == "EXT2":
    pairs.append( ("GENERAL INFORMATION", None) )
    pairs.append( ("Ext2 revision", "{0}".format(disk.revision)) )
    pairs.append( ("Total space", "{0:.2f} MB ({1} bytes)".format(float(disk.totalSpace) / 1048576, disk.totalSpace)) )
    pairs.append( ("Used space", "{0:.2f} MB ({1} bytes)".format(float(disk.usedSpace) / 1048576, disk.usedSpace)) )
    pairs.append( ("Block size", "{0} bytes".format(disk.blockSize)) )
    pairs.append( ("Num inodes", "{0}".format(disk.numInodes)) )
    pairs.append( ("Num block groups", "{0}".format(disk.numBlockGroups)) )
    
  else:
    raise FilesystemNotSupportedError()
  
  return pairs



def generateDetailedInfo(disk, showWaitIndicator = True):
  """Scans the disk to gather detailed information about space usage and returns
  a list of information pairs."""
  if disk.fsType == "EXT2":
    if showWaitIndicator:
      wait = WaitIndicatorThread("Scanning filesystem...")
      wait.start()
      try:
        report = disk.scanBlockGroups()
      finally:
        wait.done = True
      wait.join()
    else:
      report = disk.scanBlockGroups()
    
    pairs = []
    pairs.append( ("DETAILED STORAGE INFORMATION", None) )
    pairs.append( ("Num regular files", "{0}".format(report.numRegFiles)) )
    pairs.append( ("Num directories", "{0}".format(report.numDirs)) )
    pairs.append( ("Num symlinks", "{0}".format(report.numSymlinks)) )
    pairs.append( ("Space used for files", "{0} bytes".format("-")) )
    pairs.append( ("Space unused for files", "{0} bytes".format("-")) )
    for i,groupReport in enumerate(report.groupReports):
      groupInfo = []
      groupInfo.append("Free inodes: {0}".format(groupReport.numFreeInodes))
      groupInfo.append("Free blocks: {0}".format(groupReport.numFreeBlocks))
      pairs.append( ("Block group {0}".format(i), groupInfo) )
    
  else:
    raise FilesystemNotSupportedError()
  
  return pairs



def generateIntegrityReport(disk, showWaitIndicator = True):
  """Runs an integrity report on the disk and returns the results as a list of
  information pairs."""
  if disk.fsType == "EXT2":
    if showWaitIndicator:
      wait = WaitIndicatorThread("Checking disk integrity...")
      wait.start()
      try:
        report = disk.checkIntegrity()
      finally:
        wait.done = True
      wait.join()
    else:
      report = disk.checkIntegrity()
    
    pairs = []
    pairs.append( ("INTEGRITY REPORT", None) )
    pairs.append( ("Contains magic number", "{0}".format(report.hasMagicNumber)) )
    pairs.append( ("Num superblock copies", "{0}".format(report.numSuperblockCopies)) )
    pairs.append( ("Superblock copy locations", "Block groups {0}".format(",".join(map(str,report.copyLocations)))) )
    messages = list(report.messages)
    if len(messages) == 0:
      messages.append("Integrity check passed.")
    pairs.append( ("Diagnostic messages", messages) )
    
  else:
    raise FilesystemNotSupportedError()
  
  return pairs






# ========= SHELL COMMANDS ==============================================

def printShellHelp():
  """Prints a help screen for the shell, listing supported commands."""
  sp = 26
  rsp = 4
  print "Supported commands:"
  print "{0}{1}".format("pwd".ljust(sp), "Prints the current working directory.")
  print "{0}{1}".format("ls [-R,-a,-v]".ljust(sp), "Prints the entries in the working directory.")
  print "{0}{1}".format("".ljust(sp), "Optional flags:")
  print "{0}{1}{2}".format("".ljust(sp), "-R".ljust(rsp), "Lists entries recursively.")
  print "{0}{1}{2}".format("".ljust(sp), "-a".ljust(rsp), "Lists hidden entries.")
  print "{0}{1}{2}".format("".ljust(sp), "-v".ljust(rsp), "Verbose listing.")
  print
  print "{0}{1}".format("cd directory".ljust(sp), "Changes to the specified directory. Treats everything")
  print "{0}{1}".format("".ljust(sp), "following the command as a directory name.")
  print
  print "{0}{1}".format("mkdir name".ljust(sp), "Makes a new directory with the specified name. Treats")
  print "{0}{1}".format("".ljust(sp), "everything following the command as a directory name.")
  print
  print "{0}{1}".format("help".ljust(sp), "Prints this message.")
  print "{0}{1}".format("exit".ljust(sp), "Exits shell mode.")
  print


def printDirectory(directory, recursive = False, showAll = False, verbose = False):
  """Prints the specified directory according to the given parameters."""
  if not directory.fsType == "EXT2":
    raise FilesystemNotSupportedError()
  
  q = Queue()
  q.put(directory)
  while not q.empty():
    dir = q.get()
    if recursive:
      print "{0}:".format(dir.absolutePath)
    for f in dir.files():
      if not showAll and f.name.startswith("."):
        continue
      
      inode = "{0}".format(f.inodeNum).rjust(7)
      numLinks = "{0}".format(f.numLinks).rjust(3)
      uid = "{0}".format(f.uid).rjust(5)
      gid = "{0}".format(f.gid).rjust(5)
      size = "{0}".format(f.size).rjust(10)
      modified = f.timeModified.ljust(17)
      name = f.name
      if f.isDir and f.name != "." and f.name != "..":
        name = "{0}/".format(f.name)
        if recursive:
          q.put(f)
      
      if verbose:
        print "{0} {1} {2} {3} {4} {5} {6} {7}".format(inode, f.modeStr, numLinks,
          uid, gid, size, modified, name)
      else:
        print name
    print





def shell(disk):
  """Enters a command-line shell with commands for operating on the specified disk."""
  wd = disk.rootDir
  print "Entered shell mode. Type 'help' for shell commands."
  while True:
    input = raw_input(": '{0}' >> ".format(wd.absolutePath)).rstrip().split()
    if len(input) == 0:
      continue
    cmd = input[0]
    args = input[1:]
    if cmd == "help":
      printShellHelp()
    elif cmd == "exit":
      break
    elif cmd == "pwd":
      print wd.absolutePath
    elif cmd == "ls":
      printDirectory(wd, "-R" in args, "-a" in args, "-v" in args)
    elif cmd == "cd":
      if len(args) == 0:
        print "No path specified."
      else:
        path = " ".join(args)
        try:
          if path.startswith("/"):
            cdDir = disk.rootDir.getFileAt(path[1:])
          else:
            cdDir = wd.getFileAt(path)
          if not cdDir.isDir:
            raise Exception("Not a directory.")
          wd = cdDir
        except FileNotFoundError:
          print "The specified directory does not exist."
        except FilesystemError as e:
          print "Error! {0}".format(e)
    elif cmd == "mkdir":
      try:
        path = " ".join(args)
        if path.startswith("/"):
          disk.rootDir.makeDirectory(path[1:])
        else:
          wd.makeDirectory(path)
      except FilesystemError as e:
        print "Error! {0}".format(e)
    else:
      print "Command not recognized."






# ========= FILE TRANSFER ==============================================

def fetchFile(disk, srcFilename, destDirectory, showWaitIndicator = True):
  """Fetches the specified file from the disk image filesystem and places it in
  the local destination directory."""
  if not disk.fsType == "EXT2":
    raise FilesystemNotSupportedError()
  
  filesToFetch = []
  if srcFilename.endswith("/*"):
    directory = disk.rootDir.getFileAt(srcFilename[:-1])
    destDirectory = "{0}/{1}".format(destDirectory, directory.name)
    for f in directory.files():
      if f.isRegular:
        filesToFetch.append(f.absolutePath)
  else:
    filesToFetch.append(srcFilename)
  
  if len(filesToFetch) == 0:
    raise Exception("No files exist in the specified directory.")
  
  if not os.path.exists(destDirectory):
    print "Making directory {0}".format(destDirectory)
    os.mkdir(destDirectory)
    
  for srcFilename in filesToFetch:
    try:
      srcFile = disk.rootDir.getFileAt(srcFilename)
    except FileNotFoundError:
      raise Exception("The source file cannot be found on the filesystem image.")
    
    if not srcFile.isRegular:
      raise Exception("The source path does not point to a regular file.")
    
    try:
      outFile = open("{0}/{1}".format(destDirectory, srcFile.name), "wb")
    except:
      raise Exception("Cannot access specified destination directory.")
    
    def __read(wait = None):
      readCount = 0
      with outFile:
        for block in srcFile.blocks():
          outFile.write(block)
          readCount += len(block)
          if wait:
            wait.progress += len(block)
      return readCount
    
    if showWaitIndicator:
      wait = WaitIndicatorThread("Fetching {0}...".format(srcFilename))
      wait.maxProgress = srcFile.size
      wait.start()
      try:
        transferStart = clock()
        readCount = __read(wait)
        transferTime = clock() - transferStart
      finally:
        wait.done = True
      wait.join()
    else:
      transferStart = clock()
      readCount = __read()
      transferTime = clock() - transferStart
    
    mbps = float(readCount) / (1024*1024) / transferTime
    print "Read {0} bytes at {1:.2f} MB/sec.".format(readCount, mbps)
  print



def pushFile(disk, srcFilename, destDirectory, showWaitIndicator = True):
  """Pushes the specified local file to the specified destination directory on the disk image filesystem."""
  if not disk.fsType == "EXT2":
    raise FilesystemNotSupportedError()
  
  destFilename = "{0}/{1}".format(destDirectory, srcFilename[srcFilename.rfind("/")+1:])
  
  try:
    directory = disk.rootDir.getFileAt(destDirectory)
  except FileNotFoundError:
    raise Exception("Destination directory does not exist.")
  
  
  
  # print "Pushing {0} to {1}".format(srcFilename, destDirectory)
  # TODO create new file, read source, write bytes to file
  raise Exception("Not implemented.")
  





# ========= MAIN APPLICATION ==============================================

def printHelp():
  """Prints the help screen for the main application, with usage and command options."""
  sp = 26
  print "Usage: {0} disk_image_file options".format(sys.argv[0])
  print
  print "Options:"
  print "{0}{1}".format("-s".ljust(sp), "Enters shell mode.")
  print "{0}{1}".format("-h".ljust(sp), "Prints this message and exits.")
  print "{0}{1}".format("-f filepath [hostdir]".ljust(sp), "Fetches the specified file from the filesystem")
  print "{0}{1}".format("".ljust(sp), "into the optional host directory. If no directory")
  print "{0}{1}".format("".ljust(sp), "is specified, defaults to the current directory.")
  print
  print "{0}{1}".format("-p hostfile destpath".ljust(sp), "Pushes the specified host file into the specified")
  print "{0}{1}".format("".ljust(sp), "directory on the filesystem.")
  print
  print "{0}{1}".format("-i".ljust(sp), "Prints general information about the filesystem.")
  print "{0}{1}".format("-d".ljust(sp), "Scans the filesystem and prints detailed space")
  print "{0}{1}".format("".ljust(sp), "usage information.")
  print
  print "{0}{1}".format("-c".ljust(sp), "Checks the filesystem's integrity and prints a")
  print "{0}{1}".format("".ljust(sp), "detailed integrity report.")
  print
  print "{0}{1}".format("-w".ljust(sp), "Suppress the wait indicator that is typically")
  print "{0}{1}".format("".ljust(sp), "shown for long operations. This is useful when")
  print "{0}{1}".format("".ljust(sp), "redirecting the output of this program.")
  print


def run(args, disk):
  """Runs the program on the specified disk with the given command line arguments."""
  showHelp = ("-h" in args)
  enterShell = ("-s" in args)
  showGeneralInfo = ("-i" in args)
  showDetailedInfo = ("-d" in args)
  showIntegrityCheck = ("-c" in args)
  suppressIndicator = ("-w" in args)
  fetch = ("-f" in args)
  push = ("-p" in args)
  
  if showHelp or not (showGeneralInfo or enterShell or showDetailedInfo or showIntegrityCheck or fetch or push):
    printHelp()
    quit()
  
  else:
    info = []
    if showGeneralInfo:
      info.extend(getGeneralInfo(disk))
    if showDetailedInfo:
      info.extend(generateDetailedInfo(disk, not suppressIndicator))
    if showIntegrityCheck:
      info.extend(generateIntegrityReport(disk, not suppressIndicator))
    if len(info) > 0:
      printInfoPairs(info)
      
    if push:
      srcNameIndex = args.index("-p") + 1
      destNameIndex = srcNameIndex + 1
      if len(args) <= srcNameIndex:
        print "Error! No source file specified to push."
      elif len(args) <= destNameIndex:
        print "Error! No destination directory specified for pushed file."
      else:
        try:
          pushFile(disk, args[srcNameIndex], args[destNameIndex], not suppressIndicator)
        except FilesystemError as e:
          print "Error! {0}".format(e)
    
    if fetch:
      srcNameIndex = args.index("-f") + 1
      destNameIndex = srcNameIndex + 1
      if len(args) <= srcNameIndex:
        print "Error! No source file specified to fetch."
      else:
        if len(args) <= destNameIndex:
          destDirectory = "."
        elif args[destNameIndex][0] == "-":
          destDirectory = "."
        else:
          destDirectory = args[destNameIndex]
        try:
          fetchFile(disk, args[srcNameIndex], destDirectory, not suppressIndicator)
        except FilesystemError as e:
          print "Error! {0}".format(e)
    
    if enterShell:
      shell(disk)



def main():
  """Main entry point of the application."""
  disk = None
  args = list(sys.argv)
  if len(args) < 3:
    printHelp()
    quit()
  elif args[1][0] == "-":
    printHelp()
    quit()
  else:
    filename = args[1]
    del args[0:1]
    try:
      disk = Ext2Disk.fromImageFile(filename)
      with disk:
        run(args, disk)
    except FilesystemError as e:
      print "Error! {0}".format(e)
      print
      quit()



main()
