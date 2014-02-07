import ctypes
import logging
import os
import Queue
import threading

log = logging.getLogger('osd')

class OSD(threading.Thread):
    LIB_NAME = "libosd.so"
    LIB_SEARCH_DIRS = (
        "./",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "../"),
    )

    def __init__(self):
        self.halt = False
        self.queue = Queue.Queue()
        for path in self.LIB_SEARCH_DIRS:
            try:
                self.__lib = ctypes.cdll.LoadLibrary(os.path.join(path, self.LIB_NAME))
                log.debug("OSD::__init__ loaded libosd from %s" % path)
                break
            except:
                log.info("OSD::__init__ Unable to load libosd from %s" % path)
                self.__lib = None

        threading.Thread.__init__(self)
    
    def stop(self):
        self.halt = True
        self.join()

    def run(self):
        while not self.halt:
            try:
                task = self.queue.get(True, 0.5)
                getattr(self.__lib, task[0])(*task[1])
            except Queue.Empty:
                continue
            except Exception, e:
                log.error("OSD unknown error: %s" % e)

    def show(self, played, duration, title):
        if not self.__lib:
            return
        self.queue.put(('show_osd', (played, duration, title)))

    def hide(self):
        if not self.__lib:
            return
        self.queue.put(('hide_osd', []))

osd = OSD()

