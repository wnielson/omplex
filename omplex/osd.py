import ctypes
import logging
import Queue
import threading

log = logging.getLogger('osd')

class OSD(threading.Thread):
    def __init__(self):
        self.halt = False
        self.queue = Queue.Queue()

        try:
            self.__lib = ctypes.cdll.LoadLibrary("./libosd.so")
        except:
            log.info("Unable to load libosd")
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
