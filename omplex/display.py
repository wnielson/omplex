import json
import logging
import os
import re
import subprocess

log = logging.getLogger("display")

class Display(object):
    _EXECUTABLE_PATHS = (
        "/opt/vc/bin/tvservice",
        "/usr/bin/tvservice",
    )

    _STATUS_RE = re.compile(r"state [\d\w]+ \[(?P<interface>[\w]+) (?P<mode>[\w]+) \((?P<code>[\d]+)\) [\w]+ [\w]+ (?P<aspect>[\d]+:[\d]+)\], (?P<resolution>[\d]+x[\d]+) @ (?P<rate>[\d]+)Hz, (?P<scan>[\w]+)")
    _AUDIO_RE  = (
        re.compile(r"Max channels: (?P<channels>[\d]+)"),
        re.compile(r"Max samplerate: (?P<samplerate>[\d]+)kHz"),
        re.compile(r"Max rate (?P<rate>[\d]+) kb/s"),
        re.compile(r"Max samplesize (?P<samplesize>[\d]+) bits"),
    )

    def __init__(self):
        self.name       = "unknown"
        self.width      = 0
        self.height     = 0
        self.rate       = 0
        self.mode       = "unknown"
        self.code       = 0
        self.scan       = "unknown"
        self.aspect     = "unknown"
        self.interface  = "unknown"
        self.is_on      = False

        self.modes  = {
            "DMT": [],
            "CEA": []
        }

        self.audio = {}

        self.__exe = None
        for path in self._EXECUTABLE_PATHS:
            if os.access(path, os.X_OK):
                self.__exe = path
                break

        self.update(full=True)

    def __str__(self):
        return "%s (%sx%s @ %sHz %s)" % (self.name, self.width, self.height, self.rate, self.interface)

    def __repr__(self):
        return "<Display: %s>" % str(self)

    def __call(self, args):
        if self.__exe is None:
            return

        args.insert(0, self.__exe)
        p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        p.wait()
        return p

    def update(self, state=False, name=False, modes=False, full=False):
        if state or full:
            self._get_state()

        if name or full:
            self._get_name()

        if modes or full:
            self._get_modes()

    def power_off(self):
        try:
            self.__call(['--off'])
            return True
        except:
            return False

    def power_on(self, mode=None, code=None):
        if mode in ["DMT", "CEA"] and code:
            if self.__call(["-e", "%s %s" % (mode, code)]):
                self.update(state=True)
            return

        # Just power on with prefered settings
        if self.__call(["-p"]):
            self.update(state=True)

    def _get_modes(self, mode=None):
        if mode == "DMT" or mode is None:
            p = self.__call(['-m', 'DMT', '-j'])
            if p:
                try:
                    dmt = json.load(p.stdout)
                    self.modes["DMT"] = dmt
                except:
                    log.info("Display::_get_modes no DMT modes found")

        if mode == "CEA" or mode is None:
            p = self.__call(['-m', 'CEA', '-j'])
            if p:
                try:
                    cea = json.load(p.stdout)
                    self.modes["CEA"] = cea
                except:
                    log.info("Display::_get_modes no CEA modes found")

    def _get_name(self):
        p = self.__call(['--name'])
        if not p:
            return

        line = p.stdout.read().strip()
        if line:
            self.name = line.split("device_name=")[-1]

    def _get_state(self):
        """
        Example return strings:

            state 0x120016 [DVI DMT (57) RGB full 16:10], 1680x1050 @ 60Hz, progressive
            state 0x12001a [HDMI CEA (4) RGB lim 16:9], 1280x720 @ 60Hz, progressive
            state 0x120002 [TV is off]
        """
        p = self.__call(['-s'])
        if not p:
            return

        status = p.stdout.read().strip()
        match  = self._STATUS_RE.match(status)
        if not match:
            if status.find("TV is off") > -1:
                self.is_on = False
                return

            log.error("Display::update couldn't determine display status")
            return

        data            = match.groupdict()
        resolution      = [int(i) for i in data.get("resolution", "0x0").split("x")]
        self.width      = resolution[0]
        self.height     = resolution[1]
        self.rate       = int(data.get("rate"))
        self.mode       = data.get("mode")
        self.code       = int(data.get("code"))
        self.aspect     = data.get("aspect")
        self.interface  = data.get("interface")
        self.scan       = data.get("scan")
        self.is_on      = True

    def _get_audio(self):
        p = self.__call(["-a"])
        if not p:
            return

        for line in p.stdout.readlines():
            try:
                name = line.strip().split(" ",1)[0]
            except:
                log.error("Display::_get_audio couldn't find audio codec name")
                continue

            data = {}
            for expr in self._AUDIO_RE:
                match = expr.search(line)
                if match:
                    data.update(match.groupdict())
            if data:
                self.audio[name] = data


display = Display()
