"""
From: https://github.com/filmor/pyomxplayer
"""
import logging
import math
import os
import pexpect
import re

from threading import Thread, RLock
from time import sleep

from conf import settings
from display import display
from osd import osd
from utils import synchronous, Timer

# Scrobble progress to Plex server at most every 5 seconds
SCROBBLE_INTERVAL = 5

# Mark the item as watch when it is at 95% 
COMPLETE_PERCENT  = 0.95

log = logging.getLogger('player')

class PlayerManager(object):
    """
    Manages the relationship between a ``Player`` instance and a ``Media``
    item.  This is designed to be used as a singleton via the ``playerManager``
    instance in this module.  All communication between a caller and either the
    current ``player`` or ``media`` instance should be done through this class
    for thread safety reasons as all methods that access the ``player`` or
    ``media`` are thread safe.
    """
    def __init__(self):
        self._player      = None
        self._video       = None
        self._lock        = RLock()
        self.last_update = Timer()

        self.__part      = 1

    @synchronous('_lock')
    def update(self):
        if self._video and self._player:
            # Check to see if we need to turn the display on
            if not display.is_on:
                log.debug("PlayerManager::update display is off, turning on")
                self._player.pause()
                display.power_on()

            if self.last_update.elapsed() > SCROBBLE_INTERVAL and not self.is_paused():
                if not self._video.played:
                    position = self._player.position * 1e3   # In ms
                    duration = self._video.get_duration()
                    if float(position)/float(duration)  >= COMPLETE_PERCENT:
                        log.info("PlayerManager::update setting media as watched")
                        self._video.set_played()
                    else:
                        log.info("PlayerManager::update updating media position")
                        self._video.update_position(position)
                self.last_update.restart()

    @synchronous('_lock')
    def play(self, video, offset=0):
        self.stop()

        args = []
        if offset > 0:
            args.extend(("-l", str(offset)))

        audio_idx = video.get_audio_idx()
        if audio_idx is not None:
            log.debug("PlayerManager::play selecting audio stream index=%s" % audio_idx)
            args.extend(["-n", audio_idx])

        sub_idx = video.get_subtitle_idx()
        if sub_idx is not None:
            log.debug("PlayerManager::play selecting subtitle index=%s" % sub_idx)
            args.extend(["-t", sub_idx])
        else:
            # No subtitles -- this is pretty hacky
            log.debug("PlayerManager::play disabling subtitles")
            args.extend(["--subtitles", "/dev/null"])

        # TODO: Check settings for transcode settings...
        url = video.get_playback_url()
        if not url:
            log.error("PlayerManager::play no URL found")
            return
            
        self._player = Player(mediafile=url, args=args, start_playback=True, finished_callback=self.finished_callback)
        self._video  = video

    @synchronous('_lock')
    def stop(self):
        if not self._video or not self._player:
            return

        log.debug("PlayerManager::stop stopping playback of %s" % self._video)

        osd.hide()

        self._player.stop()

        self._player = None
        self._video  = None

    @synchronous('_lock')
    def get_volume(self, percent=False):
        if self._player:
            if not percent:
                return self._player._volume
            return self._player._VOLUME_STEPS.index(self._player._volume)/float(len(self._player._VOLUME_STEPS))

    @synchronous('_lock')
    def toggle_pause(self):
        if self._player:
            self._player.toggle_pause()
            if self.is_paused() and self._video:
                log.debug("PlayerManager::toggle_pause showing OSD")
                try:
                    duration = int(int(self._video.get_duration())*1e-3)
                except:
                    duration = 0
                osd.show(int(self._player.position), duration, self._video.get_proper_title())
            else:
                log.debug("PlayerManager::toggle_pause hiding OSD")
                osd.hide()

    @synchronous('_lock')
    def seek(self, offset):
        """
        Seek to ``offset`` seconds
        """
        if self._player:
            osd.hide()
            self._player.seek(offset)

    @synchronous('_lock')
    def set_volume(self, pct):
        if self._player:
            self._player.set_volume(pct)

    @synchronous('_lock')
    def get_state(self):
        if not self._player:
            return "stopped"

        if self._player._paused:
            return "paused"

        return "playing"
    
    @synchronous('_lock')
    def is_paused(self):
        if self._player:
            return self._player._paused
        return False

    @synchronous('_lock')
    def finished_callback(self):
        if not self._video:
            return
        
        if self._video.is_multipart():
            log.debug("PlayerManager::finished_callback media is multi-part, checking for next part")
            # Try to select the next part
            next_part = self.__part+1
            if self._video.select_part(next_part):
                self.__part = next_part
                log.debug("PlayerManager::finished_callback starting next part")
                self.play(self._video)

            log.debug("PlayerManager::finished_callback no more parts found")

    @synchronous('_lock')
    def get_video_attr(self, attr, default=None):
        if self._video:
            return self._video.get_video_attr(attr, default)
        return default


_OMXPLAYER_EXECUTABLE = "/usr/bin/omxplayer"

def is_omxplayer_available():
    """
    :rtype: boolean
    """
    return os.access(_OMXPLAYER_EXECUTABLE, os.X_OK)

def omxplayer_parameter_exists(parameter_string):
    return bool(re.search(b"\s%s\s" % parameter_string.strip(), os.popen("/usr/bin/omxplayer").read()))

class Player(object):

    _FILEPROP_REXP = re.compile(r".*audio streams (\d+) video streams (\d+) chapters (\d+) subtitles (\d+).*")
    _VIDEOPROP_REXP = re.compile(r".*Video codec ([\w-]+) width (\d+) height (\d+) profile (-?\d+) fps ([\d.]+).*", flags=re.MULTILINE)
    _AUDIOPROP_REXP = re.compile(r".*Audio codec (\w+) channels (\d+) samplerate (\d+) bitspersample (\d+).*", flags=re.MULTILINE)
    _STATUS_REXP = re.compile(r"(M:|V :)\s*([\d.]+).*")
    _DONE_REXP = re.compile(r"have a nice day.*")

    _LAUNCH_CMD = _OMXPLAYER_EXECUTABLE + " -s %s \"%s\""

    _PAUSE_CMD = 'p'
    _TOGGLE_SUB_CMD = 's'
    _QUIT_CMD = 'q'
    _DECREASE_VOLUME_CMD = '-'
    _INCREASE_VOLUME_CMD = '+'
    _DECREASE_SPEED_CMD = '1'
    _INCREASE_SPEED_CMD = '2'
    _SEEK_BACKWARD_30_CMD = "\033[D" # key left
    _SEEK_FORWARD_30_CMD = "\033[C" # key right
    _SEEK_BACKWARD_600_CMD = "\033[B" # key down
    _SEEK_FORWARD_600_CMD = "\033[A" # key up

    _VOLUME_INCREMENT   = 3.0 # Volume increment used by OMXPlayer in dB
    _VOLUME_MAX         = 21
    _VOLUME_MIN         = -39
    _VOLUME_STEPS       = range(_VOLUME_MIN,_VOLUME_MAX, int(_VOLUME_INCREMENT))

    # Supported speeds.
    # OMXPlayer supports a small number of different speeds.
    SLOW_SPEED = -1
    NORMAL_SPEED = 0
    FAST_SPEED = 1
    VFAST_SPEED = 2

    def __init__(self, mediafile, args=[], start_playback=False, fullscreen=True, finished_callback=None):
        self.mediafile = mediafile

        if fullscreen and "-r" not in args:
            args.append("-r")

        if "--no-osd" not in args:
            args.append("--no-osd")

        if "-o" not in args and "--adev" not in args:
            adev = settings.audio_output
            if adev in ["hdmi", "local", "both"]:
                args.extend(["-o", adev])

        
        self.finished_callback = finished_callback
        self.args = args
            
        cmd = self._LAUNCH_CMD % (" ".join([str(s) for s in self.args]), mediafile)
        log.debug("Player::__init__ launch command: %s" % cmd)
        
        self._process = pexpect.spawn(cmd)

        self._paused = False
        self._subtitles_visible = True
        self._volume = 0 # dB
        self._speed = self.NORMAL_SPEED
        self.position = 0.0
        
        self.video = dict()
        self.audio = dict()

        headers = b""
        while b"Video" not in headers or b"Audio" not in headers:
            headers += self._process.readline()

        # Get video properties
        video_props = self._VIDEOPROP_REXP.search(headers).groups()
        self.video['decoder'] = video_props[0]
        self.video['dimensions'] = tuple(int(x) for x in video_props[1:3])
        self.video['profile'] = int(video_props[3])
        self.video['fps'] = float(video_props[4])

        # Get audio properties
        audio_props = self._AUDIOPROP_REXP.search(headers).groups()
        self.audio['decoder'] = audio_props[0]
        (self.audio['channels'], self.audio['rate'],
         self.audio['bps']) = [int(x) for x in audio_props[1:]]

        # Get file properties
        #file_props = self._FILEPROP_REXP.match(self._process.readline()).groups()
        #(self.audio['streams'], self.video['streams'],
        # self.chapters, self.subtitles) = [int(x) for x in file_props]

        #if self.audio['streams'] > 0:
        #    self.current_audio_stream = 1
        #    self.current_volume = 0.0

        self.finished = False
        self.stopped  = False
        self.position = 0

        self._position_thread = Thread(target=self._get_position)
        self._position_thread.start()

        if start_playback:
            self.play()
        #self.toggle_subtitles()
        

    def _get_position(self):
        
        while not self.finished or not self.stopped:            
            index = self._process.expect([
                self._STATUS_REXP,
                pexpect.TIMEOUT,
                pexpect.EOF,
                self._DONE_REXP
            ])
            
            if index == 1: # on timeout, keep going
                continue
            elif index in (2, 3): # EOF or finished
                if not self.stopped:
                    log.debug("Player::_get_position player reached end of video")
                    self.finished = True
                    if callable(self.finished_callback):
                        # Only fire the callback if the video ended normally and
                        # was **not** stopped
                        log.debug("Player::_get_position firing callback")
                        self.finished_callback()
                break
            elif index == 0:
                self.position = float(self._process.match.group(2).strip()) / 1000000
        
            sleep(0.1)
            
            # print "POS: %0.2f" % self.position

    def pause(self):
        if not self._paused:
            self.toggle_pause()

    def play(self):
        if self._paused:
            self.toggle_pause()

    def toggle_pause(self):
        if self._process.send(self._PAUSE_CMD):
            self._paused = not self._paused

    def toggle_subtitles(self):
        if self._process.send(self._TOGGLE_SUB_CMD):
            self._subtitles_visible = not self._subtitles_visible

    def stop(self):
        self._process.send(self._QUIT_CMD)
        self._process.terminate(force=True)
        self.stopped = True

    def decrease_speed(self):
        """
        Decrease speed by one unit.
        """
        self._process.send(self._DECREASE_SPEED_CMD)

    def increase_speed(self):
        """
        Increase speed by one unit.
        """
        self._process.send(self._INCREASE_SPEED_CMD)

    def set_speed(self, speed):
        """
        Set speed to one of the supported speed levels.

        OMXPlayer does not support granular speed changes.
        """
        log.info("Setting speed = %s" % speed)

        assert speed in (self.SLOW_SPEED, self.NORMAL_SPEED, self.FAST_SPEED, self.VFAST_SPEED)

        changes = speed - self._speed
        if changes > 0:
            for i in range(1,changes):
                self.increase_speed()
        else:
            for i in range(1,-changes):
                self.decrease_speed()
        self._speed = speed

    def set_audiochannel(self, channel_idx):
        raise NotImplementedError

    def set_subtitles(self, sub_idx):
        raise NotImplementedError

    def set_chapter(self, chapter_idx):
        raise NotImplementedError

    def set_volume(self, pct):
        """
        Set volume to ``pct`` which should be a percentage:
            0 = _VOLUME_MIN
            1 = _VOLUME_MAX
        """
        pct = float(pct)
        if pct > 1 or pct < 0:
            log.error("Invalid volume; must be between 0 and 1")
            return

        volume_range   = self._VOLUME_MAX - self._VOLUME_MIN
        target_volume  = volume_range * pct
        target_volume -= target_volume % 3
        target_volume += self._VOLUME_MIN
        volume_index   = self._VOLUME_STEPS.index(self._volume)

        if target_volume == self._volume:
            return

        log.info("Setting volume to %.2f%% (%d dB)" % (pct, target_volume))

        if target_volume > self._volume:
            for i in self._VOLUME_STEPS[volume_index+1:]:
                if i > target_volume:
                    break
                self.increase_volume()
        else:
            for i in reversed(self._VOLUME_STEPS[:volume_index]):
                if i < target_volume:
                    break
                self.decrease_volume()
        log.info("Volume set to %s dB" % self._volume)

    def seek(self, offset):
        """
        mountainpenguin's hack:
        stop player, and restart at a specific point using the -l flag (position)
        """
        log.info("Stopping omxplayer")
        self.stop()

        offset = str(offset)

        # Look to see if the "start position" argument was provided previously
        for pos, arg in enumerate(self.args):
            if arg in ("-l", "--pos"):
                break

        if pos < len(self.args)-1:
            # Start position argument is already provided, so let's change it
            self.args[pos+1] = offset
        else:
            # Start position argument wasn't provided before, so we'll add it
            self.args.extend(("-l", offset))

        log.info("Restarting at offset %s" % offset)
        self.__init__(mediafile=self.mediafile, args=self.args)
        return
    
    @classmethod
    def _calculate_num_seeks(cls, curr_offset, target_offset):
        """
        Returns the number of 600s, and 30s seeks to get to the time nearest to target_offset.
        """

        # Need to determine the nearest time to target_offset, one of:
        #
        # curr_offset - 30*n (some multiple of the lowest granularity in the past)
        # curr_offset (simply don't seek)
        # curr_offset + 30*n (some multiple of the lowest granularity in the future)
        #
        # More precisely:
        #
        # n = argmin | curr_offset + i*30 - target_offset |
        #        i
        #
        # For some i,
        #
        # curr_offset + i*30 <= target_offset <= curr_offset + (i+1)*30
        # i*30 <= target_offset - curr_offset <= (i+1)*30
        # i <= (offset - curr_offset) / 30 <= (i+1)
        # i = floor( (offset - curr_offset) / 30 )

        diff = target_offset - curr_offset
        large_seeks = int(math.floor(diff / 600.0))
        diff -= large_seeks*600
        small_seeks = int(math.floor(diff / 30.0))
        return large_seeks, small_seeks

    def seek_forward_30(self):
        """
        Seeks forward by 30 seconds.
        """
        self._process.send(self._SEEK_FORWARD_30_CMD)

    def seek_forward_600(self):
        """
        Seeks forward by 600 seconds.
        """
        self._process.send(self._SEEK_FORWARD_600_CMD)

    def seek_backward_30(self):
        """
        Seeks backward by 30 seconds.
        """
        self._process.send(self._SEEK_BACKWARD_30_CMD)

    def seek_backward_600(self):
        """
        Seeks backward by 600 seconds.
        """
        self._process.send(self._SEEK_BACKWARD_600_CMD)

    def decrease_volume(self):
        """
        Decrease volume by one unit. See `_VOLUME_INCREMENT`.
        """
        self._volume -= self._VOLUME_INCREMENT
        self._process.send(self._DECREASE_VOLUME_CMD)

    def increase_volume(self):
        """
        Increase volume by one unit. See `_VOLUME_INCREMENT`.
        """
        self._volume += self._VOLUME_INCREMENT
        self._process.send(self._INCREASE_VOLUME_CMD)

playerManager = PlayerManager()

