"""mpv sebagai mesin pemutar.

mpv dimuat sebagai pustaka (libmpv) dan yt-dlp sebagai modul Python, semuanya di dalam proses ClixMax, jadi
Task Manager atau Activity Monitor hanya menampilkan ClixMax. Bila libmpv tidak ada atau gagal dimuat, mpv
dijalankan sebagai program tanpa jendela dan dikendalikan lewat IPC JSON.
"""
import ctypes
import glob
import json
import locale
import os
import re
import shutil
import subprocess
import sys
import sysconfig
import threading
import time
import traceback

from . import config, system

# Setelan yang sama untuk program mpv dan libmpv.
OPTIONS = ["idle=yes", "vo=null", "audio-display=no", "force-window=no", "osc=no", "load-stats-overlay=no",
           "load-auto-profiles=no", "input-default-bindings=no", "prefetch-playlist=yes", "gapless-audio=yes",
           "cache=yes", "demuxer-max-bytes=24MiB", "demuxer-max-back-bytes=8MiB", "volume-max=100",
           "audio-client-name=" + config.APP]


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


def find_libmpv():
    """Lokasi libmpv, atau None. Windows dan macOS: yang ikut di folder bin versi build. Selain itu yang terpasang
    bersama mpv dari Homebrew/MacPorts atau paket distro (paket mpv selalu membawa libmpv)."""
    frozen = getattr(sys, "frozen", False)
    if system.WINDOWS:
        base = os.path.dirname(sys.executable if frozen else os.path.dirname(os.path.abspath(__file__)))
        places = [os.path.join(base, "bin", "libmpv-2.dll")]
    elif system.MAC:
        # mpv dari Homebrew/MacPorts didahulukan bila terpasang: lebih baru dan FFmpeg-nya lengkap (perataan volume,
        # geser nada). Selain itu versi build memakai libmpv bawaannya di ClixMax.app/Contents/MacOS/bin.
        places = [os.path.join(d, "libmpv.2.dylib") for d in ("/opt/homebrew/lib", "/usr/local/lib", "/opt/local/lib")]
        if frozen:
            places.append(os.path.join(os.path.dirname(sys.executable), "bin", "libmpv.dylib"))
    else:
        places = sorted(glob.glob("/usr/lib*/libmpv.so.2") + glob.glob("/usr/lib/*-linux-gnu/libmpv.so.2") +
                        glob.glob("/usr/local/lib*/libmpv.so.2"))
    return next((path for path in places if os.path.isfile(path)), None)


def start_mpv(volume):
    """Nyalakan mesin pemutar: libmpv di dalam proses ClixMax bila ada, selain itu program mpv terpisah.

    Bila libmpv ada tetapi gagal dimuat (di Linux, libmpv dari distro yang lebih baru bisa bentrok dengan pustaka
    yang dibawa versi build), ClixMax kembali memakai program mpv supaya tetap bisa memutar.
    """
    lib = find_libmpv()
    if lib:
        engine = LibMpv(lib)
        try:
            engine.start(volume)
            return engine
        except Exception:
            config.log_error("libmpv %s tidak bisa dipakai, memakai program mpv:\n%s" % (lib, traceback.format_exc()))
            engine.stop()
    engine = Mpv()
    try:
        engine.start(volume)
    except Exception:
        engine.stop()
        raise
    return engine


class _Quiet:
    """Penampung pesan yt-dlp: versi build tidak punya konsol, dan galatnya tetap sampai lewat exception."""

    def debug(self, msg):
        pass

    info = warning = error = debug


def ytdl(**options):
    """yt-dlp sebagai modul Python. Dimuat saat pertama dipakai supaya ClixMax tetap cepat terbuka.

    yt-dlp tidak boleh menjalankan program lain yang kebetulan ada di PATH (menambah proses di Task Manager):
    js_runtimes kosong mematikan deno/node (audio YouTube tetap didapat tanpanya), dan ffmpeg_location ke folder
    yang tidak ada mematikan pengecekan ffmpeg (ClixMax tidak mengunduh atau menggabung berkas).
    """
    import yt_dlp
    return yt_dlp.YoutubeDL(dict({"quiet": True, "no_warnings": True, "noprogress": True, "socket_timeout": 30,
                                  "js_runtimes": {}, "ffmpeg_location": os.path.join(config.DATA, "tanpa-ffmpeg"),
                                  "logger": _Quiet()}, **options))


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
        args = ([exe, "--no-config", "--no-video", "--no-terminal"] + ["--" + opt for opt in OPTIONS] +
                ["--input-ipc-server=" + config.PIPE, "--ytdl=yes", "--ytdl-format=bestaudio/best",
                 "--volume=%d" % volume] + list(self.extra))
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


# ---------------------------------------------------------------- libmpv (client.h, API 2.x)

_STRING, _FLAG, _INT64, _DOUBLE, _NODE, _ARRAY, _MAP = 1, 3, 4, 5, 6, 7, 8
_EVENT_SHUTDOWN, _EVENT_HOOK = 1, 25
_ERROR_OPTION_NOT_FOUND = -5


class _Node(ctypes.Structure):
    pass


class _NodeList(ctypes.Structure):
    _fields_ = [("num", ctypes.c_int), ("values", ctypes.POINTER(_Node)), ("keys", ctypes.POINTER(ctypes.c_char_p))]


class _Value(ctypes.Union):
    _fields_ = [("string", ctypes.c_char_p), ("flag", ctypes.c_int), ("int64", ctypes.c_int64),
                ("double", ctypes.c_double), ("list", ctypes.POINTER(_NodeList)), ("ba", ctypes.c_void_p)]


_Node._fields_ = [("u", _Value), ("format", ctypes.c_int)]


class _Event(ctypes.Structure):
    _fields_ = [("event_id", ctypes.c_int), ("error", ctypes.c_int), ("reply_userdata", ctypes.c_uint64),
                ("data", ctypes.c_void_p)]


class _Hook(ctypes.Structure):
    _fields_ = [("name", ctypes.c_char_p), ("id", ctypes.c_uint64)]


def _dlopen_lazy(path, flags=0):
    """Muat pustaka dengan RTLD_LAZY. libmpv yang ikut di versi macOS (media-kit) dibangun tanpa libass: simbolnya
    sengaja dibiarkan tak terhubung dan tidak pernah dipanggil. ctypes selalu memakai RTLD_NOW yang menolak simbol
    tak terhubung, jadi dlopen dipanggil sendiri, seperti cara media-kit memuatnya."""
    libc = ctypes.CDLL(None)
    libc.dlopen.restype, libc.dlopen.argtypes = ctypes.c_void_p, [ctypes.c_char_p, ctypes.c_int]
    libc.dlerror.restype = ctypes.c_char_p
    handle = libc.dlopen(os.fsencode(path), os.RTLD_LAZY | os.RTLD_LOCAL | flags)
    if not handle:
        raise OSError((libc.dlerror() or b"dlopen gagal").decode("utf-8", "replace"))
    return ctypes.CDLL(path, handle=handle)


def _load(path):
    lib = _dlopen_lazy(path) if system.MAC else ctypes.CDLL(path)
    handle, node = ctypes.c_void_p, ctypes.POINTER(_Node)
    for name, result, args in (
            ("mpv_create", handle, []),
            ("mpv_initialize", ctypes.c_int, [handle]),
            ("mpv_set_option_string", ctypes.c_int, [handle, ctypes.c_char_p, ctypes.c_char_p]),
            ("mpv_command_node", ctypes.c_int, [handle, node, node]),
            ("mpv_get_property", ctypes.c_int, [handle, ctypes.c_char_p, ctypes.c_int, ctypes.c_void_p]),
            ("mpv_set_property", ctypes.c_int, [handle, ctypes.c_char_p, ctypes.c_int, ctypes.c_void_p]),
            ("mpv_free_node_contents", None, [node]),
            ("mpv_error_string", ctypes.c_char_p, [ctypes.c_int]),
            ("mpv_wait_event", ctypes.POINTER(_Event), [handle, ctypes.c_double]),
            ("mpv_hook_add", ctypes.c_int, [handle, ctypes.c_uint64, ctypes.c_char_p, ctypes.c_int]),
            ("mpv_hook_continue", ctypes.c_int, [handle, ctypes.c_uint64]),
            ("mpv_terminate_destroy", None, [handle])):
        func = getattr(lib, name)
        func.restype, func.argtypes = result, args
    return lib


def _to_node(value, keep):
    """Nilai Python ke mpv_node. keep menampung buffer yang harus tetap hidup selama node dipakai."""
    node = _Node()
    if isinstance(value, bool):
        node.format, node.u.flag = _FLAG, int(value)
    elif isinstance(value, int):
        node.format, node.u.int64 = _INT64, value
    elif isinstance(value, float):
        node.format, node.u.double = _DOUBLE, value
    elif isinstance(value, (list, tuple)):
        items = (_Node * len(value))(*[_to_node(item, keep) for item in value])
        values = _NodeList(len(value), items, None)
        keep += [items, values]
        node.format, node.u.list = _ARRAY, ctypes.pointer(values)
    else:
        data = str(value).encode("utf-8")
        keep.append(data)
        node.format, node.u.string = _STRING, data
    return node


def _from_node(node):
    if node.format == _STRING:
        return (node.u.string or b"").decode("utf-8", "replace")
    if node.format == _FLAG:
        return bool(node.u.flag)
    if node.format == _INT64:
        return node.u.int64
    if node.format == _DOUBLE:
        return node.u.double
    if node.format in (_ARRAY, _MAP):
        found = node.u.list.contents
        values = [_from_node(found.values[i]) for i in range(found.num)]
        if node.format == _ARRAY:
            return values
        return {found.keys[i].decode("utf-8", "replace"): values[i] for i in range(found.num)}
    return None


class LibMpv(Mpv):
    """mpv sebagai pustaka di dalam proses ClixMax, dengan perintah dan jawaban yang sama seperti versi IPC.

    Link (YouTube dan situs lain) dibuka lewat hook on_load: sebelum mpv membuka lagu, alamatnya diganti dengan
    alamat audio dari yt-dlp, seperti yang dikerjakan skrip ytdl_hook bawaan mpv tetapi tanpa menjalankan program
    yt-dlp. Hook ditangani di thread event sendiri; perintah lain tetap dari satu thread pemakai.
    """

    def __init__(self, path):
        super().__init__()
        self.path = path
        self.lib = self.ctx = self.events = self.ydl = self.has_filter = None

    def start(self, volume):
        self.lib = _load(self.path)
        # libmpv menolak dibuat bila LC_NUMERIC bukan "C", dan ytmusicapi mengganti locale setiap kali YTMusic
        # dibuat (bisa bersamaan dari thread lain), jadi dikembalikan dulu, dan dicoba lagi bila kalah cepat.
        for _ in range(3):
            locale.setlocale(locale.LC_NUMERIC, "C")
            self.ctx = self.lib.mpv_create()
            if self.ctx:
                break
        else:
            raise RuntimeError("libmpv gagal dibuat (locale %s)" % locale.setlocale(locale.LC_NUMERIC))
        # input-media-keys=no: tombol media dan panel media OS diurus ClixMax sendiri (media.py), bukan mpv.
        # sid=no, sub-auto=no: ClixMax tidak menampilkan subtitle, dan libmpv macOS tidak punya libass, jadi berkas
        # .lrc di sebelah lagu tidak boleh dimuat mpv sebagai subtitle.
        own = OPTIONS + ["vid=no", "sid=no", "sub-auto=no", "ytdl=no", "input-media-keys=no", "volume=%d" % volume]
        options = own + [opt.lstrip("-") for opt in self.extra]
        for i, (name, _, value) in enumerate(opt.partition("=") for opt in options):
            code = self.lib.mpv_set_option_string(self.ctx, name.encode(), value.encode())
            # osc, ytdl, dan sejenisnya hanya ada bila libmpv dibangun dengan Lua (libmpv yang ikut di versi macOS
            # tidak). Gunanya mematikan skrip Lua, jadi bila tidak ada, dilewati. Opsi dari pengguna tetap diperiksa.
            if not (code == _ERROR_OPTION_NOT_FOUND and i < len(own)):
                self.check(code, name)
        self.check(self.lib.mpv_initialize(self.ctx), "initialize")
        self.has_filter = self.filter_check()
        self.check(self.lib.mpv_hook_add(self.ctx, 0, b"on_load", 10), "hook on_load")
        self.events = threading.Thread(target=self.event_loop, name="libmpv-events", daemon=True)
        self.events.start()

    def check(self, code, what):
        if code < 0:
            raise RuntimeError("libmpv %s: %s" % (what, self.lib.mpv_error_string(code).decode()))

    def filter_check(self):
        """Pemeriksa nama filter FFmpeg, atau None bila semuanya dianggap ada. Hanya libmpv macOS bawaan (media-kit)
        yang FFmpeg-nya dipangkas: filternya cuma equalizer dan overlay."""
        avfilter = os.path.join(os.path.dirname(self.path), "libavfilter.dylib")
        if not (system.MAC and os.path.exists(avfilter)):
            return None
        try:
            lib = _dlopen_lazy(avfilter, os.RTLD_NOLOAD)  # sudah dimuat bersama libmpv
            lib.avfilter_get_by_name.restype, lib.avfilter_get_by_name.argtypes = ctypes.c_void_p, [ctypes.c_char_p]
        except (OSError, AttributeError):
            config.log_error("libavfilter tidak bisa diperiksa, efek suara dimatikan:\n" + traceback.format_exc())
            return lambda name: False
        return lambda name: bool(lib.avfilter_get_by_name(name.encode()))

    def usable_filters(self, chain):
        """Rantai af tanpa bagian lavfi yang filternya tidak ada. Filter yang gagal dibuat membuat mpv mematikan
        audio sehingga lagu tidak berbunyi sama sekali; lebih baik efeknya saja yang hilang."""
        parts = re.findall(r"lavfi=\[[^\]]*\]|[^,]+", chain)
        keep = [part for part in parts if not part.startswith("lavfi=[") or
                all(self.has_filter(f.split("=", 1)[0]) for f in part[7:-1].split(","))]
        if len(keep) < len(parts):
            config.log_error("Efek suara tidak tersedia di libmpv ini, dilewati: %s"
                             % ", ".join(p for p in parts if p not in keep))
        return ",".join(keep)

    def cmd(self, *args):
        keep = []
        if args[0] == "set_property":  # perintah khusus IPC; di libmpv fungsinya sendiri
            if args[1] == "af" and self.has_filter:
                args = (args[0], args[1], self.usable_filters(args[2]))
            value = _to_node(args[2], keep)
            code = self.lib.mpv_set_property(self.ctx, args[1].encode(), _NODE, ctypes.byref(value))
            return {"error": self.lib.mpv_error_string(code).decode()}
        if args[0] == "get_property":
            return {"error": "success", "data": self.get(args[1])}
        node, result = _to_node(list(args), keep), _Node()
        code = self.lib.mpv_command_node(self.ctx, ctypes.byref(node), ctypes.byref(result))
        reply = {"error": self.lib.mpv_error_string(code).decode()}
        if code >= 0:
            reply["data"] = _from_node(result)
            self.lib.mpv_free_node_contents(ctypes.byref(result))
        return reply

    def get(self, prop):
        node = _Node()
        if self.lib.mpv_get_property(self.ctx, prop.encode(), _NODE, ctypes.byref(node)) < 0:
            return None
        try:
            return _from_node(node)
        finally:
            self.lib.mpv_free_node_contents(ctypes.byref(node))

    def event_loop(self):
        while True:
            event = self.lib.mpv_wait_event(self.ctx, -1).contents
            if event.event_id == _EVENT_SHUTDOWN:
                return
            if event.event_id == _EVENT_HOOK:
                hook = ctypes.cast(event.data, ctypes.POINTER(_Hook)).contents.id
                try:
                    self.open_link()
                except Exception:
                    config.log_error(traceback.format_exc())
                finally:
                    self.lib.mpv_hook_continue(self.ctx, hook)

    def open_link(self):
        """Ganti link halaman dengan alamat audionya. Bila yt-dlp gagal, link dibiarkan dan mpv mencobanya
        sendiri (link langsung ke berkas audio tetap bisa diputar)."""
        url = self.get("stream-open-filename") or ""
        if not url.startswith(("http://", "https://")):
            return
        if self.ydl is None:
            self.ydl = ytdl(format="bestaudio/best", noplaylist=True)
        try:
            info = self.ydl.extract_info(url, download=False)
        except Exception as exc:
            config.log_error("yt-dlp gagal membuka %s: %s" % (url, exc))
            return
        if not info.get("url"):
            return
        keep = []

        def put(prop, value):
            self.lib.mpv_set_property(self.ctx, prop.encode(), _NODE, ctypes.byref(_to_node(value, keep)))

        # Sama dengan ytdl_hook: judul untuk media-title, lalu User-Agent dan header yang dibutuhkan situsnya.
        put("file-local-options/force-media-title", info.get("title") or url)
        headers = info.get("http_headers") or {}
        if headers.get("User-Agent"):
            put("file-local-options/user-agent", headers["User-Agent"])
        fields = ["%s: %s" % (key, headers[key]) for key in ("Cookie", "Referer", "X-Forwarded-For")
                  if headers.get(key)]
        if fields:
            put("file-local-options/http-header-fields", fields)
        put("stream-open-filename", info["url"])

    def stop(self):
        if not self.ctx:
            return
        if self.events:
            try:
                self.cmd("quit")
            except Exception:
                pass
            self.events.join(3)
            if self.events.is_alive():  # masih menunggu yt-dlp; prosesnya toh sedang ditutup
                return
        self.lib.mpv_terminate_destroy(self.ctx)
        self.ctx = None
