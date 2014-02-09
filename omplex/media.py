import logging
import urllib
import urlparse

from __init__ import __version__

try:
    import xml.etree.cElementTree as et
except:
    import xml.etree.ElementTree as et

from conf import settings
from utils import get_plex_url, safe_urlopen

log = logging.getLogger('media')

# http://192.168.0.12:32400/photo/:/transcode?url=http%3A%2F%2F127.0.0.1%3A32400%2F%3A%2Fresources%2Fvideo.png&width=75&height=75

class MediaItem(object):
    pass

class Video(object):
    def __init__(self, node, parent, media=0, part=0):
        self.parent        = parent
        self.node          = node
        self.played        = False
        self._media        = 0
        self._media_node   = None
        self._part         = 0
        self._part_node    = None

        if media:
            self.select_media(media, part)

        if not self._media_node:
            self.select_best_media(part)

    def select_best_media(self, part=0):
        """
        Nodes are accessed via XPath, which is technically 1-indexed, while
        Plex is 0-indexed.
        """
        # Select the best media based on resolution
        highest_res = 0
        best_node   = 0
        for i, node in enumerate(self.node.findall('./Media')):
            res = int(node.get('height', 0))*int(node.get('height', 0))
            if res > highest_res:
                highest_res = res
                best_node   = i

        log.debug("Video::select_best_media selected media %s" % best_node)

        self.select_media(best_node)

    def select_media(self, media, part=0):
        node = self.node.find('./Media[%s]' % (media+1))
        if node:
            self._media      = media
            self._media_node = node
            if self.select_part(part):
                log.debug("Video::select_media selected media %d" % media)
                return True

        log.error("Video::select_media error selecting media %d" % media)
        return False

    def select_part(self, part):
        if self._media_node is None:
            return False

        node = self._media_node.find('./Part[%s]' % (part+1))
        if node:
            self._part      = part
            self._part_node = node
            return True

        log.error("Video::select_media error selecting part %s" % part)
        return False

    def is_multipart(self):
        if not self._media_node:
            return False
        return len(self._media_node.findall("./Part",[])) > 1

    def get_proper_title(self):
        if not hasattr(self, "_title"):
            media_type = self.node.get('type')

            if self.parent.tree.find(".").get("identifier") != "com.plexapp.plugins.library":
                # Plugin?
                title =  self.node.get('sourceTitle') or ""
                if title:
                    title += " - "
                title += self.node.get('title') or ""
            else:
                # Assume local media
                if media_type == "movie":
                    title = self.node.get("title")
                    year  = self.node.get("year")
                    if year is not None:
                        title = "%s (%s)" % (title, year)
                elif media_type == "episode":
                    episode_name   = self.node.get("title")
                    episode_number = int(self.node.get("index"))
                    season_number  = int(self.node.get("parentIndex"))
                    series_name    = self.node.get("grandparentTitle")
                    title = "%s - %dx%.2d - %s" % (series_name, season_number, episode_number, episode_name)
                else:
                    # "clip", ...
                    title = self.node.get("title")
            setattr(self, "_title", title)
        return getattr(self, "_title")

    def get_playback_url(self, direct_play=True, 
                         video_height=1080,     video_width=1920,
                         video_bitrate=20000,   video_quality=100):
        """
        Returns the URL to use for the trancoded file.
        """
        if direct_play:
            if not self._part_node:
                return
            url  = urlparse.urljoin(self.parent.server_url, self._part_node.get("key", ""))
            return get_plex_url(url)

        url = "/video/:/transcode/universal/start.m3u8"
        args = {
            "path":             self.node.get("key"),
            "session":          settings.client_uuid,
            "protocol":         "hls",
            "directPlay":       "0",
            "directStream":     "1",
            "fastSeek":         "1",
            "maxVideoBitrate":  str(video_bitrate),
            "videoQuality":     str(video_quality),
            "videoResolution":  "%sx%s" % (video_width,video_height),
            "mediaIndex":       self._media or 0,
            "partIndex":        self._part or 0,
            #"skipSubtitles":    "1",
        }

        audio_formats = []
        protocols = "protocols=shoutcast,http-video;videoDecoders=h264{profile:high&resolution:1080&level:51};audioDecoders=mp3,aac"
        if settings.audio_ac3passthrough:
            audio_formats.append("add-transcode-target-audio-codec(type=videoProfile&context=streaming&protocol=hls&audioCodec=ac3)")
            audio_formats.append("add-transcode-target-audio-codec(type=videoProfile&context=streaming&protocol=hls&audioCodec=eac3)")
            protocols += ",ac3{bitrate:800000&channels:8}"
        if settings.audio_dtspassthrough:
            audio_formats.append("add-transcode-target-audio-codec(type=videoProfile&context=streaming&protocol=hls&audioCodec=dca)")
            protocols += ",dts{bitrate:800000&channels:8}"

        if audio_formats:
            args["X-Plex-Client-Profile-Extra"] = "+".join(audio_formats)
            args["X-Plex-Client-Capabilities"]  = protocols 

        return get_plex_url(urlparse.urljoin(self.parent.server_url, url), args)

    def get_audio_idx(self):
        """
        Returns the index of the selected stream
        """
        if not self._part_node:
            return

        match = False
        for index, stream in enumerate(self._part_node.findall("./Stream[@streamType='2']") or []):
            if stream.get('selected') == "1":
                match = True
                break

        if match:
            return index+1

    def get_subtitle_idx(self):
        if not self._part_node:
            return

        match = False
        for index, sub in enumerate(self._part_node.findall("./Stream[@streamType='3']") or []):
            if sub.get('selected') == "1":
                match = True
                break

        if match:
            return index+1

    def get_duration(self):
        return self.node.get("duration")

    def get_rating_key(self):
        return self.node.get("ratingKey")

    def get_video_attr(self, attr, default=None):
        return self.node.get(attr, default)

    def update_position(self, ms):
        """
        Sets the state of the media as "playing" with a progress of ``ms`` milliseconds.
        """
        rating_key = self.get_rating_key()

        if rating_key is None:
            log.error("No 'ratingKey' could be found in XML from URL '%s'" % (self.parent.path.geturl()))
            return False

        url  = urlparse.urljoin(self.parent.server_url, '/:/progress')
        data = {
            "key":          rating_key,
            "time":         int(ms),
            "identifier":   "com.plexapp.plugins.library",
            "state":        "playing"
        }
        
        return safe_urlopen(url, data)

    def set_played(self):
        rating_key = self.get_rating_key()

        if rating_key is None:
            log.error("No 'ratingKey' could be found in XML from URL '%s'" % (self.parent.path.geturl()))
            return False

        url  = urlparse.urljoin(self.parent.server_url, '/:/scrobble')
        data = {
            "key":          rating_key,
            "identifier":   "com.plexapp.plugins.library"
        }

        self.played = safe_urlopen(url, data)
        return self.played

class Media(object):
    def __init__(self, url):
        """
        ``url`` should be a URL to the Plex XML media item.
        """
        self.path       = urlparse.urlparse(url)
        self.server_url = self.path.scheme + "://" + self.path.netloc
        self.tree       = et.parse(urllib.urlopen(get_plex_url(url)))

    def __str__(self):
        return self.path.path

    def get_video(self, index, media=0, part=0):
        video = self.tree.find('./Video[%s]' % (index+1))
        if video:
            return Video(video, self, media, part)

        log.error("Media::get_video couldn't find video at index %s" % video)

    def get_machine_identifier(self):
        if not hasattr(self, "_machine_identifier"):
            doc = urllib.urlopen(get_plex_url(self.server_url))
            tree = et.parse(doc)
            setattr(self, "_machine_identifier", tree.find('.').get("machineIdentifier"))
        return getattr(self, "_machine_identifier", None)
