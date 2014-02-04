import getpass
import Queue
import logging
import sys
import time

from client import HttpServer
from conf import settings
from gdm import PlexGDM
from timeline import timelineManager

__author__ = "Weston Nielson <wnielson@github>"
__version__ = "0.2"
__prog__ = "omplex"

HTTP_PORT   = 3000

log = logging.getLogger('')

logging.getLogger('requests').setLevel(logging.CRITICAL)

def main():
    logging.basicConfig(level=logging.DEBUG, stream=sys.stdout, format="%(asctime)s [%(levelname)8s] %(message)s")

    settings.load("settings.dat")
    if not settings.myplex_token:
        while True:
            username = raw_input("MyPlex Username: ")
            password = getpass.getpass("MyPlex Password: ")
            if settings.login_myplex(username, password):
                print "Logged in!"
                break
            print "Error logging in..."

    gdm = PlexGDM()
    gdm.clientDetails(settings.client_uuid, __prog__, HTTP_PORT, __prog__, __version__)
    gdm.start_all()

    log.info("Started GDM service")

    queue = Queue.Queue()

    while not gdm.discovery_complete:
        time.sleep(1)

    gdm.discover()

    server = HttpServer(queue, HTTP_PORT)
    server.start()

    timelineManager.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print ""
        log.info("Stopping services...")
    finally:
        server.stop()
        timelineManager.stop()
        gdm.stop_all()

if __name__ == "__main__":
    main()
