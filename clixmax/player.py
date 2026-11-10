"""mpv sebagai mesin pemutar: dijalankan tanpa jendela dan dikendalikan lewat IPC JSON."""
import glob
import json
import os
import shutil
import subprocess
import sys
import sysconfig
import time

from . import config, system


def _script_dirs():
    """Folder program dari pip (tempat yt-dlp terpasang) untuk Python yang sedang berjalan."""
    dirs = []
    for scheme in (None, "nt_user" if system.WINDOWS else ("osx_framework_user" if system.MAC else "posix_user")):
        try:
            dirs.append(sysconfig.get_path("scripts", scheme) if scheme else sysconfig.get_path("scripts"))
        except KeyError:
            pass
    return dirs


def find_exe(name):
    """Cari program: dulu folder bin bawaan versi build, lalu PATH, lalu tempat pemasangan yang umum tapi sering
    tidak masuk PATH."""
    exe = name + (".exe" if system.WINDOWS else "")
    if getattr(sys, "frozen", False):  # versi build (PyInstaller): mpv/yt-dlp ikut di bin/ sebelah program
        bundled = os.path.join(os.path.dirname(sys.executable), "bin", exe)
        if os.path.isfile(bundled) and os.access(bundled, os.X_OK):
            return bundled
    path = shutil.which(name)
    if path:
        return path
    places = _script_dirs()
    if system.WINDOWS:  # winget memasang mpv di folder paket, tidak selalu masuk PATH
        local = os.environ.get("LOCALAPPDATA", "")
        places += glob.glob(os.path.join(local, "Microsoft", "WinGet", "Packages", "*%s*" % name))
    else:  # aplikasi yang dibuka dari Finder atau menu tidak membawa PATH dari terminal
        places += ["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", os.path.expanduser("~/.local/bin")]
    places.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin"))
    for place in places:
        candidate = os.path.join(place, exe)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


class Mpv:
    """mpv tanpa jendela, dikendalikan lewat IPC JSON. Dipakai dari satu thread saja."""
    extra = []

    def __init__(self):
        self.proc = self.pipe = None
        self.buf = b""
        self.rid = 0

    def start(self, volume):
        exe = find_exe("mpv")
        if not exe:
            raise RuntimeError("mpv tidak ditemukan. Pasang dengan: %s" % system.install_hint("mpv"))
        try:  # sisa mpv dari sesi yang mati mendadak
            with system.ipc_connect(config.PIPE) as old:
                old.write(b'{"command":["quit"]}\n')
            time.sleep(0.6)
        except OSError:
            system.ipc_cleanup(config.PIPE)
        args = [exe, "--idle=yes", "--no-config", "--no-video", "--vo=null", "--audio-display=no",
                "--no-terminal", "--force-window=no", "--osc=no", "--load-stats-overlay=no",
                "--load-auto-profiles=no", "--input-default-bindings=no",
                "--input-ipc-server=" + config.PIPE, "--ytdl=yes", "--ytdl-format=bestaudio/best",
                "--prefetch-playlist=yes", "--gapless-audio=yes", "--cache=yes", "--demuxer-max-bytes=24MiB",
                "--demuxer-max-back-bytes=8MiB", "--volume-max=100", "--volume=%d" % volume,
                "--audio-client-name=" + config.APP] + list(self.extra)
        ytdlp = find_exe("yt-dlp")
        if ytdlp:
            args.append("--script-opts=ytdl_hook-ytdl_path=" + ytdlp)
        null = subprocess.DEVNULL
        self.proc = subprocess.Popen(args, creationflags=system.HIDDEN, stdin=null, stdout=null, stderr=null)
        for _ in range(100):
            try:
                self.pipe = system.ipc_connect(config.PIPE)
                break
            except OSError:
                if self.proc.poll() is not None:
                    raise RuntimeError("mpv langsung berhenti (kode %s)" % self.proc.returncode)
                time.sleep(0.1)
        else:
            raise RuntimeError("mpv tidak merespons")
        self.cmd("disable_event", "all")

    def cmd(self, *args):
        self.rid += 1
        self.pipe.write((json.dumps({"command": list(args), "request_id": self.rid}) + "\n").encode("utf-8"))
        while True:
            while b"\n" not in self.buf:
                chunk = self.pipe.read(4096)
                if not chunk:
                    raise OSError("mpv terputus")
                self.buf += chunk
            line, self.buf = self.buf.split(b"\n", 1)
            reply = json.loads(line)
            if reply.get("request_id") == self.rid and "error" in reply:
                return reply

    def get(self, prop):
        reply = self.cmd("get_property", prop)
        return reply.get("data") if reply.get("error") == "success" else None

    def stop(self):
        try:
            self.pipe.write(b'{"command":["quit"]}\n')
            self.proc.wait(2)
        except Exception:
            if self.proc:
                self.proc.kill()
        finally:
            try:
                self.pipe.close()
            except Exception:
                pass
