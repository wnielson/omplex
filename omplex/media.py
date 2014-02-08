import logging
import urllib
import urlparse

from __init__ import __version__

try:
    import xml.etree.cElementTree as et
except:
    import xml.etree.ElementTree as et

from conf import settings

import pdb

log = logging.getLogger('media')

# http://192.168.0.12:32400/photo/:/transcode?url=http%3A%2F%2F127.0.0.1%3A32400%2F%3A%2Fresources%2Fvideo.png&width=75&height=75

class Media(object):
    def __init__(self, url):
        """
        ``url`` should be a URL to the Plex XML media item.
        """
        self.path       = urlparse.urlparse(url)
        self.server_url = self.path.scheme + "://" + self.path.netloc
        self.played     = False
        
        url = urlparse.urljoin(self.server_url, self.path.path)
        qs  = urlparse.parse_qs(self.path.query)
        for k, v in qs.items():
            qs[k] = v[0]
        self.tree = et.parse(urllib.urlopen(self._get_plex_url(url, qs)))

    def __str__(self):
        return self.path.path

    def get_proper_title(self):
        if not hasattr(self, "_title"):
            media_type = self.tree.find('.Video').get('type')

            if self.tree.find('.').get("identifier") != "com.plexapp.plugins.library":
                # Plugin?
                title =  self.tree.find('./Video').get('sourceTitle') or ""
                if title:
                    title += " - "
                title += self.tree.find('./Video').get('title') or ""
            else:
                # Assume local media
                if media_type == "movie":
                    title = self.tree.find('.Video').get("title")
                    year  = self.tree.find('.Video').get("year")
                    if year is not None:
                        title = "%s (%s)" % (title, year)
                elif media_type == "episode":
                    episode_name   = self.tree.find('.Video').get("title")
                    episode_number = int(self.tree.find('.Video').get("index"))
                    season_number  = int(self.tree.find('.Video').get("parentIndex"))
                    series_name    = self.tree.find('.Video').get("grandparentTitle")
                    title = "%s - %dx%.2d - %s" % (series_name, season_number, episode_number, episode_name)
                else:
                    title = self.tree.find('.Video').get("title")
            setattr(self, "_title", title)
        return getattr(self, "_title")

    def is_multipart(self):
        media_count = 0
        part_count = 0
        for media in self.tree.findall('./Video/Media'):
            media_count += 1
            for part in media.findall('./Part'):
                part_count += 1

        # If there is one "part" for every "media", then this isn't
        # a multi-part item
        return media_count != part_count

    def _get_attribute(self, path, attr, default=None):
        el = self.tree.find(path)
        if el:
            return el.get(attr, None)
        return default

    def _get_media_key(self):
        if not hasattr(self, "_media_key"):
            video_tag = self.tree.find('./Video')
            media_key = video_tag.get('ratingKey', None)
            setattr(self, '_media_key', media_key)
        return self._media_key

    def _get_plex_url(self, url, data={}):
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
            "X-Plex-Product":           "Plex Home Theater",
            "X-Plex-Platform":          "Plex Home Theater"
        })

        # Kinda ghetto...
        sep = "?"
        if sep in url:
            sep = "&"

        if data:
            url = "%s%s%s" % (url, sep, urllib.urlencode(data))

        log.debug("Created URL: %s" % url)

        return url

    def _safe_urlopen(self, url, data={}):
        url = self._get_plex_url(url, data)

        try:
            page = urllib.urlopen(url)
            if page.code == 200:
                return True
            log.error("Error opening URL '%s': page returned %d" % (url,
                                                                    page.code))
        except Exception, e:
            log.error("Error opening URL '%s':  %s" % (url, e))

        return False

    def get_machine_identifier(self):
        if not hasattr(self, "_machine_identifier"):
            doc = urllib.urlopen(self._get_plex_url(self.server_url))
            tree = et.parse(doc)
            setattr(self, "_machine_identifier", tree.find('.').get("machineIdentifier"))
        return getattr(self, "_machine_identifier", None)


    def get_media_url(self, part_num=1):
        """
        Returns the URL to the original file.  If transcoding is required, this
        URL should not be used;  see ``get_transcode_url`` instead.
        """
        if part_num < 1:
            part_num = 1

        part = self.tree.find('./Video/Media[1]/Part[%d]' % int(part_num))
        if part is not None:
            url  = urlparse.urljoin(self.server_url, part.get('key'))
            return self._get_plex_url(url)

    def get_transcode_url(self, extension='mkv',    format='matroska',
                          video_codec='libx264',    audio_codec=None,
                          continue_play=False,      continue_time=None,
                          video_width='1920',       video_height='1080',
                          video_bitrate="20000",    video_quality=100,
                          direct_play=True):
        """
        Returns the URL to use for the trancoded file.
        """
        if direct_play:
            return self.get_media_url()

        url = "/video/:/transcode/universal/start.m3u8"
        args = {
            "path":             self._get_attribute('./Video', 'key'),
            "session":          settings.client_uuid,
            "protocol":         "hls",
            "directPlay":       "0",
            "directStream":     "1",
            "fastSeek":         "1",
            "maxVideoBitrate":  str(video_bitrate),
            "videoQuality":     str(video_quality),
            "videoResolution":  "%sx%s" % (video_width,video_height),
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

        return self._get_plex_url(urlparse.urljoin(self.server_url, url), args)

    def get_audio_idx(self):
        """
        Returns the index of the selected stream
        """
        match = False
        for index, stream in enumerate(self.tree.findall("./Video/Media/Part/Stream[@streamType='2']") or []):
            if stream.get('selected') == "1":
                match = True
                break

        if match:
            return index+1

    def get_subtitle_idx(self):
        match = False
        for index, sub in enumerate(self.tree.findall("./Video/Media/Part/Stream[@streamType='3']") or []):
            if sub.get('selected') == "1":
                match = True
                break

        if match:
            return index+1

    def get_duration(self):
        return self._get_attribute('./Video', 'duration')

    def get_rating_key(self):
        return self._get_attribute('./Video', 'ratingKey')

    def get_video_attr(self, attr, default=None):
        return self._get_attribute('./Video', attr, default)

    def update_position(self, ms):
        """
        Sets the state of the media as "playing" with a progress of ``ms`` milliseconds.
        """
        media_key = self._get_media_key()

        if media_key is None:
            log.error("No 'ratingKey' could be found in XML from URL '%s'" % (self.path.geturl()))
            return False

        url  = urlparse.urljoin(self.server_url, '/:/progress')
        data = {
            "key":          media_key,
            "time":         int(ms),
            "identifier":   "com.plexapp.plugins.library",
            "state":        "playing"
        }
        
        return self._safe_urlopen(url, data)

    def set_played(self):
        media_key = self._get_media_key()

        if media_key is None:
            log.error("No 'ratingKey' could be found in XML from URL '%s'" % (self.path.geturl()))
            return False

        url  = urlparse.urljoin(self.server_url, '/:/scrobble')
        data = {
            "key":          media_key,
            "identifier":   "com.plexapp.plugins.library"
        }

        self.played = self._safe_urlopen(url, data)
        return self.played

