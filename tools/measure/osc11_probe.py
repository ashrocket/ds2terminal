"""osc11_probe.py - asks the terminal for its background color (OSC 11) and writes the reply to a file.

usage: python3 -I osc11_probe.py OUT_FILE
Claude Code's `auto` theme uses this reply to select dark or light. No reply in 2 s: it writes "none".
"""
import os
import select
import sys
import termios
import time
import tty

time.sleep(2.5)   # the driver sets the profile first
fd = sys.stdin.fileno()
old = termios.tcgetattr(fd)
reply = b""
try:
    tty.setraw(fd)
    os.write(sys.stdout.fileno(), b"\033]11;?\007")
    end = time.time() + 2.0
    while time.time() < end:
        r, _w, _x = select.select([fd], [], [], 0.2)
        if r:
            reply += os.read(fd, 64)
            if reply.endswith(b"\007") or reply.endswith(b"\033\\"):
                break
finally:
    termios.tcsetattr(fd, termios.TCSADRAIN, old)
with open(sys.argv[1], "w") as f:
    f.write(repr(reply.decode("latin1")) if reply else "none")
    f.write("\nCOLORFGBG=%s\n" % os.environ.get("COLORFGBG"))
