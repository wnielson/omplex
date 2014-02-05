import datetime
import json
import logging
import os
import threading
import requests
import urlparse
import SocketServer

from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
from SocketServer import ThreadingMixIn

try:
    from xml.etree import cElementTree as et
except:
    from xml.etree import ElementTree as et

try:
    from cStringIO import cStringIO
except:
    from StringIO import StringIO

from conf import settings
from media import Media
from player import playerManager
from subscribers import remoteSubscriberManager, RemoteSubscriber
from timeline import timelineManager

log = logging.getLogger("client")

class HttpHandler(BaseHTTPRequestHandler):
    xmlOutput   = None
    completed   = False
    
    handlers    = (
        (("/resources",),                       "resources"),
        (("/player/playback/playMedia",
          "/player/application/playMedia",),    "playMedia"),
        (("/player/playback/stepForward",
          "/player/playback/stepBack",),        "stepFunction"),
        (("/player/playback/skipNext",),        "skipNext"),
        (("/player/playback/skipPrevious",),    "skipPrevious"),
        (("/player/playback/stop",),            "stop"),
        (("/player/playback/seekTo",),          "seekTo"),
        (("/player/playback/skipTo",),          "skipTo"),
        (("/player/playback/setParameters",),   "set"),
        (("/player/playback/setStreams",),      "setStreams"),
        (("/player/playback/pause",
          "/player/playback/play",),            "pausePlay"),
        (("/player/timeline/subscribe",),       "subscribe"),
        (("/player/timeline/unsubscribe",),     "unsubscribe"),
        (("/player/timeline/poll",),            "poll"),
        (("/player/application/setText",
          "/player/application/sendString",),   "sendString"),
        (("/player/application/sendVirtualKey",
          "/player/application/sendKey",),      "sendVKey"),
        (("/player/playback/bigStepForward",
          "/player/playback/bigStepBack",),     "stepFunction"),
    )

    def log_request(self, *args, **kwargs):
        pass

    def setStandardResponse(self, code=200, status="OK"):
        el = et.Element("Response")
        el.set("code",      str(code))
        el.set("status",    str(status))

        if self.xmlOutput:
            self.xmlOutput.append(el)
        else:
            self.xmlOutput = el

    def getSubFromRequest(self, arguments):
        uuid = self.headers.get("X-Plex-Client-Identifier", None)
        name = self.headers.get("X-Plex-Device-Name",  None)

        if not uuid:
            log.warn("HttpHandler::getSubFromRequest subscriber didn't set X-Plex-Client-Identifier")
            self.setStandardResponse(500, "subscriber didn't set X-Plex-Client-Identifier")
            return

        if not name:
            log.warn("HttpHandler::getSubFromRequest subscriber didn't set X-Plex-Device-Name")
            self.setStandardResponse(500, "subscriber didn't set X-Plex-Device-Name")
            return

        port        = int(arguments.get("port", 32400))
        commandID   = int(arguments.get("commandID", -1))
        protocol    = arguments.get("protocol", "http")
        ipaddress   = self.client_address[0]

        return RemoteSubscriber(uuid, commandID, ipaddress, port, protocol, name)

    def get_querydict(self, query):
        querydict = {}
        for key, value in urlparse.parse_qsl(query):
            querydict[key] = value
        return querydict

    def updateCommandID(self, arguments):
        if not arguments.has_key("commandID"):
            if self.path.find("unsubscribe") < 0:
                log.warn("HttpHandler::updateCommandID no commandID sent to this request!")
            return

        commandID = -1
        try:
            commandID = int(arguments["commandID"])
        except:
            log.error("HttpHandler::updateCommandID invalid commandID: %s" % arguments["commandID"])
            return

        uuid = self.headers.get("X-Plex-Client-Identifier", None)
        if not uuid:
            log.warn("HttpHandler::updateCommandID subscriber didn't set X-Plex-Client-Identifier")
            self.setStandardResponse(500, "When commandID is set you also need to specify X-Plex-Client-Identifier")
            return

        sub = remoteSubscriberManager.findSubscriberByUUID(uuid)
        if sub:
            sub.commandID = commandID

    def handle_request(self, method):
        if self.headers.has_key('X-Plex-Device-Name'):
            log.debug("HttpHandler::handle_request request from '%s' to '%s'" % (self.headers["X-Plex-Device-Name"], self.path))
        else:
            log.debug("HttpHandler::handle_request request to '%s'" % self.path)

        path  = urlparse.urlparse(self.path)
        query = self.get_querydict(path.query)

        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("X-Plex-Client-Identifier",    settings.client_uuid)

        if method == "OPTIONS" and self.headers.has_key("Access-Control-Request-Method"):
            # TODO: This isn't working...

            #self.protocol_version = "HTTP/1.1"

            self.send_header("Content-Type", "text/plain")
            self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS, DELETE, PUT, HEAD")
            self.send_header("Access-Control-Max-Age", "1209600")
            self.send_header("Connection", "close")

            if self.headers.has_key("Access-Control-Request-Headers"):
                self.send_header("Access-Control-Allow-Headers", self.headers["Access-Control-Request-Headers"])

            self.end_headers()
            self.send_response(200)
            self.wfile.flush()

            return

        self.send_header("Content-type", "text/xml")
        self.setStandardResponse()

        self.updateCommandID(query)

        match = False
        for paths, handler in self.handlers:
            if path.path in paths:
                match = True
                getattr(self, handler)(path, query)
                break

        if not match:
            if path.path.startswith("/player/navigation"):
                navigation(path, query)
            else:
                self.setStandardResponse(500, "Nope, not implemented, sorry!")

        self.send_end()

    def do_OPTIONS(self):
        self.handle_request("OPTIONS")

    def do_GET(self):
        self.handle_request("GET")
    
    def send_end(self):
        if self.completed:
            return

        response = StringIO()
        tree     = et.ElementTree(self.xmlOutput)
        tree.write(response, encoding="utf-8", xml_declaration=True)
        response.seek(0)

        xmlData = response.read()

        self.send_response(200)

        self.send_header("Date", datetime.datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT"))
        self.send_header("Content-Length", str(len(xmlData)))
        #self.send_header("Connection", 'Close')
        
        self.end_headers()

        self.wfile.write(xmlData)
        self.wfile.flush()
        self.wfile.close()

        self.completed = True

    #--------------------------------------------------------------------------
    #   URL Handlers
    #--------------------------------------------------------------------------
    def subscribe(self, path, arguments):
        sub = self.getSubFromRequest(arguments)
        if sub:
            remoteSubscriberManager.addSubscriber(sub)
            
            self.send_end()

            timelineManager.SendTimelineToSubscriber(sub)

    def unsubscribe(self, path, arguments):
        remoteSubscriberManager.removeSubscriber(self.getSubFromRequest(arguments))

    def poll(self, path, arguments):
        uuid = self.headers.get("X-Plex-Client-Identifier", None)
        name = self.headers.get("X-Plex-Device-Name", "")

        commandID = -1
        try:
            commandID = int(arguments.get("commandID", -1))
        except:
            pass

        if commandID == -1 or not uuid:
            log.warn("HttpHandler::poll the poller needs to set both X-Plex-Client-Identifier header and commandID arguments.")
            self.setStandardResponse(500, "You need to specify both x-Plex-Client-Identifier as a header and commandID as a argument")
            return

        pollSubscriber = RemoteSubscriber(uuid, commandID, name=name)
        remoteSubscriberManager.addSubscriber(pollSubscriber)

        if arguments.has_key("wait") and arguments["wait"] in ("1", "true"):
            self.xmlOutput = timelineManager.WaitForTimeline(pollSubscriber)
        else:
            self.xmlOutput = timelineManager.GetCurrentTimeLinesXML(pollSubscriber)

        self.send_header("Access-Control-Expose-Headers", "X-Plex-Client-Identifier")

    def resources(self, path, arguments):
        pass

    def playMedia(self, path, arguments):
        address     = arguments.get("address",      None)
        protocol    = arguments.get("protocol",     "http")
        port        = arguments.get("port",         "32400")
        key         = arguments.get("key",          None)
        offset      = int(int(arguments.get("offset",   0))/1e3)
        url         = urlparse.urljoin("%s://%s:%s" % (protocol, address, port), key)
        media       = Media(url)

        log.debug("HttpHandler::playMedia %s" % media)

        playerManager.play(media, offset)

        timelineManager.SendTimelineToSubscribers()

    def stop(self, path, arguments):
        playerManager.stop()

        timelineManager.SendTimelineToSubscribers()

    def pausePlay(self, path, arguments):
        playerManager.toggle_pause()

    def stepFunction(self, path, arguments):
        log.info("HttpHandler::stepFunction not implemented yet")

    def seekTo(self, path, arguments):
        offset = int(int(arguments.get("offset", 0))*1e-3)
        log.debug("HttpHandler::seekTo offset %ss" % offset)
        playerManager.seek(offset)


class HttpSocketServer(ThreadingMixIn, HTTPServer):
    allow_reuse_address = True

class HttpServer(threading.Thread):
    def __init__(self, queue, port):
        super(HttpServer, self).__init__(name="HTTP Server")

        self.daemon         = True
        self.port           = port
        self.queue          = queue
        self.server         = HttpSocketServer(("", self.port), HttpHandler)
        self.server.queue   = queue

    def run(self):
        log.info("Started HTTP server")
        self.server.serve_forever()

    def stop(self):
        log.info("Stopping HTTP server...")
        self.server.shutdown()
