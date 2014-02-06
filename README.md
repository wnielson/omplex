# OMPlex

OMPlex is a Plex-based interface to OMXPlayer on the RaspberryPi.  Using a Plex
device, such as a smartphone or tablet, one can connect to OMPlex and playback
videos on their RaspberryPi.

OMPlex is still quite rough around the edges, but it is useable, with the
following exceptions:

1. No transcoder support
2. No channel support (haven't tested)
3. No support for the web-based remote at plex.tv/web
4. Only videos are supported (no picture or music support)
5. No subtitle support
6. No audio stream selection

All of these things are on the TODO list.

A simple OSD built ontop of OpenVG is also included.  The ultimate goal is to
be able to use it to switch subtitles and audio streams.  For now it simply
displays basic inforation about the currenly playing video.  It mimicks the
look and feel of Plex Home Theater's OSD, with some minor differences.  Below
is an example of what the OSD looks like:

![OSD](https://github.com/wnielson/omplex/raw/master/osd/screenshots/example1.jpg "OSD Screenshot")

Much of this work is based off of the (now defunct) PyPlex project, with the
main difference being that OMPlex uses the (undocumented) "Timelines API".
Support for this API was basically reverse engineered from Plex HT and Plex
for Roku sources as well as some Wireshark snooping.  The other main piece
comes from the PlexGDM project.

## Installation

OMPlex is written mainly in Python, so you will need a relatively recent
2.x version--2.6 or 2.7 should work just fine.  The following Python libraries
are also required:

* [Requests](https://pypi.python.org/pypi/requests/)
* [pexpect](https://pypi.python.org/pypi/pexpect/)

You'll also need OMXPlayer.  You can find new builds for Debian-based distros
here: http://omxplayer.sconde.net/

This will be packaged up more cleanly once it matures, but in the meantime,
just run:

    python cmdline.py

You'll be prompted for you MyPlex username and password.  You should now see
"omplex" as a player from your Plex remote.

### OSD

I'm still working on better integration of the OSD, but for now you need to build it by hand.
You'll need to install ``libjpeg`` and make sure you have the ``GLESv2`` library ``/opt/vc/lib/``.
Go into the ``osd`` directory and type ``make``.  If everything goes well, you should now have
a file ``libosd.so``.

## Configuration

The first time you launch ``OMPLex`` it'll ask for your MyPlex credentials.  This will change
in the near future and all configuration will be done via a web browser.  Currently, you can access
the configuration page, once you've started ``OMPLex`` at ``http://127.0.0.1:3000/``.  Replace the
IP address with your Pi's actual IP address.  You should get a page like this:

![Web Config](https://github.com/wnielson/omplex/raw/master/web.png "Web Config")

## Alternatives

* [PyPlex](https://github.com/dalehamel/pyplex) - This doesn't work with the new Plex app on iOS, at least for me.  It also seems to be dead.
* [RasPlex](http://rasplex.com/) - Some of the devs from PyPlex seem to have jumped ship and are now trying to get Plex HT to run on the RaspberryPi.

RasPlex is really the ideal solution--a full HTPC interface for Plex, awesome.
In reality though, I have my doubts that Plex HT will ever run satisfactorily
on the Pi.  OMPlex player is to be lightweight and simple.  Browse your Plex
catalog on your phone and playback videos through the RaspberryPi.
