import json
import logging
import re
import subprocess

log = logging.getLogger("display")

_TVSERVICE_EXECUTABLE = "/usr/bin/tvservice"

class Display(object):

    _STATUS_RE = re.compile(r"state [\d\w]+ \[(?P<interface>[\w]+) (?P<mode>[\w]+) \((?P<code>[\d]+)\) [\w]+ [\w]+ (?P<aspect>[\d]+:[\d]+)\], (?P<resolution>[\d]+x[\d]+) @ (?P<rate>[\d]+)Hz, (?P<scan>[\w]+)")

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

        self.update(full=True)

    def __str__(self):
        return "%s (%sx%s @ %sHz %s)" % (self.name, self.width, self.height, self.rate, self.interface)

    def __repr__(self):
        return "<Display: %s>" % str(self)

    def update(self, state=False, name=False, modes=False, full=False):
        if state or full:
            self._get_state()

        if name or full:
            self._get_name()

        if modes or full:
            self._get_modes()

    def power_off(self):
        try:
            subprocess.check_call([_TVSERVICE_EXECUTABLE, '--off'])
            return True
        except:
            return False

    def power_on(self, mode=None, code=None):
        if mode in ["DMT", "CEA"] and code:
            try:
                subprocess.check_call([_TVSERVICE_EXECUTABLE, "-e", "%s %s" % (mode, code)])
                self.update(state=True)
                return True
            except:
                return False

        # Just power on with prefered settings
        try:
            subprocess.check_call([_TVSERVICE_EXECUTABLE, "-p"])
            self.update(state=True)
            return True
        except:
            return False

    def _get_modes(self, mode=None):
        if mode == "DMT" or mode is None:
            p = subprocess.Popen([_TVSERVICE_EXECUTABLE, '-m', 'DMT', '-j'], stdout=subprocess.PIPE)
            p.wait()
            try:
                dmt = json.load(p.stdout)
                self.modes["DMT"] = dmt
            except:
                log.info("Display::_get_modes no DMT modes found")

        if mode == "CEA" or mode is None:
            p = subprocess.Popen([_TVSERVICE_EXECUTABLE, '-m', 'CEA', '-j'], stdout=subprocess.PIPE)
            p.wait()
            try:
                cea = json.load(p.stdout)
                self.modes["CEA"] = cea
            except:
                log.info("Display::_get_modes no CEA modes found")

    def _get_name(self):
        p = subprocess.Popen([_TVSERVICE_EXECUTABLE, '--name'], stdout=subprocess.PIPE)
        p.wait()
        line = p.stdout.read().strip()
        if line:
            self.name = line.split("device_name=")[-1]

    def _get_state(self):
        """
        Example return string:

            state 0x120016 [DVI DMT (57) RGB full 16:10], 1680x1050 @ 60Hz, progressive
        """
        p = subprocess.Popen([_TVSERVICE_EXECUTABLE, '-s'], stdout=subprocess.PIPE)
        p.wait()
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

display = Display()
