import logging
import requests
import threading
import time

try:
    from xml.etree import cElementTree as et
except:
    from xml.etree import ElementTree as et

try:
    from cStringIO import cStringIO
except:
    from StringIO import StringIO

from conf import settings
from player import playerManager
from subscribers import remoteSubscriberManager
from utils import Timer

log = logging.getLogger("timeline")

class TimelineManager(threading.Thread):
    def __init__(self):
        self.currentItems   = {}
        self.currentStates  = {}
        self.subTimer       = Timer()
        self.serverTimer    = Timer()
        self.stopped        = False
        self.halt           = False

        threading.Thread.__init__(self)

    def stop(self):
        self.halt = True
        self.join()

    def run(self):
        while not self.halt:
            if playerManager.player and playerManager.media and not playerManager.is_paused():
                self.SendTimelineToSubscribers()
                playerManager.update()
            time.sleep(1)

    def SendTimelineToSubscribers(self):
        log.debug("TimelineManager::SendTimelineToSubscribers updating all subscribers")
        for sub in remoteSubscriberManager.subscribers.values():
            self.SendTimelineToSubscriber(sub)

    def SendTimelineToSubscriber(self, subscriber):
        timelineXML = self.GetCurrentTimeLinesXML(subscriber)
        url = "%s/:/timeline" % subscriber.url

        log.debug("TimelineManager::SendTimelineToSubscriber sending timeline to %s" % url)

        tree = et.ElementTree(timelineXML)
        tmp  = StringIO()
        tree.write(tmp, encoding="utf-8", xml_declaration=True)

        tmp.seek(0)
        xmlData = tmp.read()

        # TODO: Abstract this into a utility function and add other X-Plex-XXX fields
        requests.post(url, data=xmlData, headers={
            "Content-Type":             "application/x-www-form-urlencoded",
            "Connection":               "keep-alive",
            "Content-Range":            "bytes 0-/-1",
            "X-Plex-Client-Identifier": settings.client_uuid
        })

    def WaitForTimeline(self, subscriber):
        log.info("TimelineManager::WaitForTimeline not implemented...")

    def GetCurrentTimeLinesXML(self, subscriber):
        tlines = self.GetCurrentTimeline()

        #
        # Only "video" is supported right now
        #
        mediaContainer = et.Element("MediaContainer")
        if subscriber.commandID is not None:
            mediaContainer.set("commandID", str(subscriber.commandID))
        mediaContainer.set("location", tlines["location"])

        lineEl = et.Element("Timeline")
        for key, value in tlines.items():
            lineEl.set(key, str(value))
        mediaContainer.append(lineEl)

        return mediaContainer

    def GetCurrentTimeline(self):
        # https://github.com/plexinc/plex-home-theater-public/blob/pht-frodo/plex/Client/PlexTimelineManager.cpp#L142
        options = {
            "location": "navigation",
            "state":    playerManager.get_state(),
            "type":     "video"
        }
        controllable = []

        if playerManager.media and playerManager.player:
            options["location"]          = "fullScreenVideo"

            options["time"]              = playerManager.player.position * 1e3
            
            options["ratingKey"]         = playerManager.media.get_video_attr("ratingKey")
            options["key"]               = playerManager.media.get_video_attr("key")
            options["containerKey"]      = playerManager.media.get_video_attr("key")
            options["guid"]              = playerManager.media.get_video_attr("guid")
            options["duration"]          = playerManager.media.get_video_attr("duration")
            options["address"]           = playerManager.media.path.hostname
            options["protocol"]          = playerManager.media.path.scheme
            options["port"]              = playerManager.media.path.port
            options["machineIdentifier"] = playerManager.media.get_machine_identifier()
            options["seekRange"]         = "0-%s" % options["duration"]

            controllable.append("playPause")
            controllable.append("stop")
            controllable.append("stepBack")
            controllable.append("stepForward")
            controllable.append("subtitleStream")
            controllable.append("audioStream")
            controllable.append("seekTo")

            # TODO: Only is player output is 'local' not 'hdmi'
            controllable.append("volume")
            options["volume"] = str(playerManager.get_volume() or 0)

            options["controllable"] = ",".join(controllable)
        else:
            options["time"] = 0

        return options


timelineManager = TimelineManager()
