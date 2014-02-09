import logging
import urllib

from __init__ import __version__
from conf import settings
from datetime import datetime
from functools import wraps

log = logging.getLogger("utils")

class Timer(object):
    def __init__(self):
        self.restart()

    def restart(self):
        self.started = datetime.now()

    def elapsedMs(self):
        return  self.elapsed() * 1e3

    def elapsed(self):
        return (datetime.now()-self.started).total_seconds()

def synchronous(tlockname):
    """
    A decorator to place an instance based lock around a method.
    From: http://code.activestate.com/recipes/577105-synchronization-decorator-for-class-methods/
    """

    def _synched(func):
        @wraps(func)
        def _synchronizer(self,*args, **kwargs):
            tlock = self.__getattribute__( tlockname)
            tlock.acquire()
            try:
                return func(self, *args, **kwargs)
            finally:
                tlock.release()
        return _synchronizer
    return _synched

def get_plex_url(url, data={}):
    if settings.myplex_token:
        data.update({
            "X-Plex-Token": settings.myplex_token
        })

    data.update({
        "X-Plex-Version":           __version__,
        "X-Plex-Client-Identifier": settings.client_uuid,
        "X-Plex-Provides":          "player",
        "X-Plex-Device-Name":       settings.player_name,
        "X-Plex-Model":             "RaspberryPI",
        "X-Plex-Device":            "RaspberryPI",

        # Lies
        "X-Plex-Product":           "Popcorn Hour",
        "X-Plex-Platform":          "Popcorn Hour"
    })

    # Kinda ghetto...
    sep = "?"
    if sep in url:
        sep = "&"

    if data:
        url = "%s%s%s" % (url, sep, urllib.urlencode(data))

    log.debug("get_plex_url Created URL: %s" % url)

    return url

def safe_urlopen(url, data={}):
    """
    Opens a url and returns True if an HTTP 200 code is returned,
    otherwise returns False.
    """
    url = get_plex_url(url, data)

    try:
        page = urllib.urlopen(url)
        if page.code == 200:
            return True
        log.error("Error opening URL '%s': page returned %d" % (url,
                                                                page.code))
    except Exception, e:
        log.error("Error opening URL '%s':  %s" % (url, e))

    return False