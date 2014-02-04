"""
player.py - A python interface to omxplayer on the RaspberryPi.

Originally from https://github.com/jbaiter/pyomxplayer.git, updated by
Weston Nielson <wnielson@github>
"""
import logging
import pexpect
import re

from threading import Thread, RLock
from time import sleep
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
        self.player      = None
        self.media       = None
        self.lock        = RLock()
        self.last_update = Timer()

    @synchronous('lock')
    def update(self):
        if self.media and self.player:
            if self.last_update.elapsed() > SCROBBLE_INTERVAL:
                if not self.media.played:
                    position = self.player.position * 1e3   # In ms
                    duration = self.media.get_duration()
                    if float(position)/float(duration)  >= COMPLETE_PERCENT:
                        log.info("PlayerManager::update setting media as watched")
                        self.media.set_played()
                    else:
                        log.info("PlayerManager::update updating media position")
                        self.media.update_position(position)
                self.last_update.restart()

    @synchronous('lock')
    def play(self, media, offset=0):
        self.stop()

        args = []
        if offset > 0:
            args.append("-l %s" % offset)

        self.player = Player(mediafile=media.get_media_url(), args=" ".join(args), start_playback=True)
        self.media  = media

    @synchronous('lock')
    def stop(self):
        if not self.media or not self.player:
            return

        log.debug("PlayerManager::stop stopping playback of %s" % self.media)

        self.player.stop()

        self.player = None
        self.media  = None

    @synchronous('lock')
    def toggle_pause(self):
        if self.player:
            self.player.toggle_pause()

    @synchronous('lock')
    def get_state(self):
        if not self.player:
            return "stopped"

        if self.player.paused:
            return "paused"

        return "playing"


class Player(object):

    _FILEPROP_REXP  = re.compile(r".*audio streams (\d+) video streams (\d+) chapters (\d+) subtitles (\d+).*")
    _VIDEOPROP_REXP = re.compile(r".*Video codec ([\w-]+) width (\d+) height (\d+) profile (\d+) fps ([\d.]+).*")
    _AUDIOPROP_REXP = re.compile(r"Audio codec (\w+) channels (\d+) samplerate (\d+) bitspersample (\d+).*")
    _STATUS_REXP    = re.compile(r"M:\s*([\d.]+).*")
    _DONE_REXP      = re.compile(r"have a nice day.*")

    _LAUNCH_CMD     = '/usr/bin/omxplayer -s %s %s'
    _PAUSE_CMD      = 'p'
    _TOGGLE_SUB_CMD = 't'
    _QUIT_CMD       = 'q'
    _INCREASE_SPEED = '2'
    _DECREASE_SPEED = '1'
    _FAST_FORWARD   = '>'
    _REWIND         = '<'
    _JUMP_600_REV   = '\x1b[B'
    _JUMP_600_FWD   = '\x1b[A'
    _JUMP_30_FWD    = '\x1b[C'
    _JUMP_30_REV    = '\x1b[D'

    paused              = False
    subtitles_visible   = False

    def __init__(self, mediafile, args="", start_playback=False):
        self.position = 0

        cmd = self._LAUNCH_CMD % (mediafile, args)

        self._process = None

        try:
            self._process = pexpect.spawn(cmd)
        except:
            log.error("No OMXPLAYER")
        
        # Set defaults, just in case we dont get them
        self.video = {
            'decoder':      "unknown",
            'dimensions':   (0,0),
            'profile':      0,
            'fps':          0,
            'streams':      0
        }

        self.audio = {
            'decoder':      "unknown",
            'channels':     0,
            'rate':         0,
            'bps':          0,
            'streams':      0
        }

        self.chapters   = 0
        self.subtitles  = 0
        prop_matches    = 0
        self.finished   = False

        if not self._process:
            return

        for i in range (0, 6):
            line = self._process.readline()
            file_props_match = self._FILEPROP_REXP.match(line)
            video_props_match = self._VIDEOPROP_REXP.match(line)
            audio_props_match = self._AUDIOPROP_REXP.match(line)
            status_match = self._STATUS_REXP.match(line)

            if(file_props_match):
                # Get file properties
                file_props = file_props_match.groups()
                (self.audio['streams'], self.video['streams'],
                 self.chapters, self.subtitles) = [int(x) for x in file_props]
                prop_matches += 1
            
            if(video_props_match):
                # Get video properties
                video_props = video_props_match.groups()
                self.video['decoder'] = video_props[0]
                self.video['dimensions'] = tuple(int(x) for x in video_props[1:3])
                self.video['profile'] = int(video_props[3])
                self.video['fps'] = float(video_props[4])
                prop_matches += 1
            
            if(audio_props_match):
                # Get audio properties
                audio_props = audio_props_match.groups()
                self.audio['decoder'] = audio_props[0]
                (self.audio['channels'], self.audio['rate'],
                 self.audio['bps']) = [int(x) for x in audio_props[1:]]
                prop_matches += 1
            
            if(prop_matches >= 3):
                break

        if self.audio['streams'] > 0:
            self.current_audio_stream = 1
            self.current_volume = 0.0

        self._position_thread = Thread(target=self._get_position)
        self._position_thread.setDaemon(True)
        self._position_thread.start()

        if not start_playback:
            self.toggle_pause()

        self.toggle_subtitles()
        self._playback_speed = 1

    def _get_position(self):
        while not self.finished:
            index = self._process.expect([self._STATUS_REXP,
                                            pexpect.TIMEOUT,
                                            pexpect.EOF,
                                            self._DONE_REXP])
            if index == 1:
                continue
            elif index in (2, 3):
                break
            else:
                self.position = float(self._process.match.group(1))*1e-6
            sleep(0.05)

    def toggle_pause(self):
        log.debug('Player::toggle_pause')
        if not self._process:
            return

        if self._process.send(self._PAUSE_CMD):
            self.paused = not self.paused

    def toggle_subtitles(self):
        log.debug('Player::toggle_subtitles')
        if not self._process:
            return

        if self._process.send(self._TOGGLE_SUB_CMD):
            self.subtitles_visible = not self.subtitles_visible
    
    def stop(self):
        log.debug('Player::stop')
        
        # This should kill the position thread
        self.finished = True

        if not self._process:
            return

        # Stop the player
        self._process.send(self._QUIT_CMD)
        self._process.terminate(force=True)

        # Make sure the position thread is done
        self._position_thread.join()

    def jump_fwd_30(self):
        log.debug('Player::jump_fwd_30')
        if not self._process:
            return

        self._process.send(self._JUMP_30_FWD)

    def jump_fwd_600(self):
        log.debug('Player::jump_fwd_600')
        if not self._process:
            return

        self._process.send(self._JUMP_600_FWD)

    def jump_rev_30(self):
        log.debug('Player::jump_rev_30')
        if not self._process:
            return

        self._process.send(self._JUMP_30_REV)

    def jump_rev_600(self):
        log.debug('Player::jump_rev_600')
        if not self._process:
            return

        self._process.send(self._JUMP_600_REV)

    def fast_forward(self):
        log.debug('Player::fast_forward')
        if not self._process:
            return

        self._process.send(self._FAST_FORWARD)

    def rewind(self):
        log.debug('Player::fast_forward')
        if not self._process:
            return

        self._process.send(self._REWIND)

    def increase_speed(self):
        log.debug('Player::increase_speed')
        if not self._process:
            return

        self._process.send(self._INCREASE_SPEED)
        self._playback_speed += 1

    def decrease_speed(self):
        log.debug('Player::decrease_speed')
        if not self._process:
            return

        self._process.send(self._DECREASE_SPEED)
        self._playback_speed -= 1
        if (self._playback_speed < 0):
            self._playback_speed = 0

    def set_speed(self, desired):
        if not self._process:
            return

        if((desired < 0) or (desired > 4)):
            return 0
        if (self._playback_speed > desired):
            function = self.decrease_speed
        elif (self._playback_speed == desired):
            return 0
        else:
            function = self.increase_speed
        while (self._playback_speed != desired):
            function()
        return 1

    def set_audiochannel(self, channel_idx):
        raise NotImplementedError

    def set_subtitles(self, sub_idx):
        raise NotImplementedError

    def set_chapter(self, chapter_idx):
        raise NotImplementedError

    def set_volume(self, volume):
        raise NotImplementedError

    def seek(self, minutes):
        raise NotImplementedError

playerManager = PlayerManager()
