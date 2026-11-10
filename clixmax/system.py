"""Semua yang berbeda antar sistem operasi dikumpulkan di sini, supaya modul lain tidak perlu tahu.

Windows sudah diuji. macOS dan Linux memakai jalur standar masing-masing tetapi belum diuji langsung.
"""
import os
import socket
import sys
import tempfile
import threading

WINDOWS = sys.platform == "win32"
MAC = sys.platform == "darwin"
LINUX = not (WINDOWS or MAC)

SHORTCUT = "Command" if MAC else "Control"   # tombol pintasan: Cmd di macOS, Ctrl di lainnya
MULTI_SELECT = 0x8 if MAC else 0x4           # bit modifier klik untuk memilih banyak baris (Cmd / Ctrl)
HIDDEN = 0x08000000 if WINDOWS else 0        # subprocess tanpa jendela konsol (CREATE_NO_WINDOW)
# Klik kanan: tombol 3 di Windows/Linux; di macOS Tk melaporkannya sebagai tombol 2, juga Ctrl+klik.
CONTEXT_CLICK = ("<Button-2>", "<Control-Button-1>") if MAC else ("<Button-3>",)

if WINDOWS:
    import ctypes
    from ctypes import wintypes


def data_dir():
    """Folder setelan, pustaka, dan sesi sesuai kebiasaan tiap OS."""
    if WINDOWS:
        return os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "clixmax")
    if MAC:
        return os.path.expanduser("~/Library/Application Support/ClixMax")
    return os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "clixmax")


def install_hint(tool):
    """Perintah pasang yang biasa untuk mpv atau yt-dlp di OS ini."""
    if tool == "yt-dlp":
        return "pip install -U yt-dlp"
    if WINDOWS:
        return "winget install mpv-player.mpv-CI.MSVC"
    if MAC:
        return "brew install mpv"
    return "sudo apt install mpv (atau paket mpv dari distro Anda)"


# ---------------------------------------------------------------- jalur kendali mpv

def ipc_path(name):
    """Alamat server kendali mpv: named pipe di Windows, Unix socket di macOS/Linux."""
    if WINDOWS:
        return r"\\.\pipe\%s" % name
    base = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
    return os.path.join(base, "%s-%d.sock" % (name, os.getuid()))


class _Socket:
    """Bungkus socket supaya bisa dipakai seperti berkas biner: read, write, close, with."""

    def __init__(self, sock):
        self.sock = sock

    def read(self, size):
        return self.sock.recv(size)

    def write(self, data):
        self.sock.sendall(data)

    def close(self):
        self.sock.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def ipc_connect(path):
    """Sambung ke mpv. Melempar OSError bila mpv belum (atau tidak lagi) mendengarkan."""
    if WINDOWS:
        return open(path, "r+b", buffering=0)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.connect(path)
    except OSError:
        sock.close()
        raise
    return _Socket(sock)


def ipc_cleanup(path):
    """Hapus berkas socket sisa mpv yang mati mendadak (tidak berlaku untuk pipe Windows)."""
    if not WINDOWS and os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


# ---------------------------------------------------------------- jendela

def prepare_process():
    """Dipanggil sebelum jendela dibuat: tajam di layar DPI tinggi dan ikon taskbar sendiri (Windows)."""
    if not WINDOWS:
        return
    for call in (lambda: ctypes.windll.shcore.SetProcessDpiAwareness(1),
                 lambda: ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("clixmax.player")):
        try:
            call()
        except Exception:
            pass


def ui_scale(root):
    """Pengali ukuran antarmuka. macOS sudah mengurus layar Retina sendiri, jadi selalu 1."""
    return 1.0 if MAC else root.winfo_fpixels("1i") / 96


def work_area(root):
    """(kiri, atas, kanan, bawah) layar tanpa taskbar, supaya jendela tidak tertutup di layar kecil."""
    if WINDOWS:
        area = wintypes.RECT()
        if ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(area), 0):
            return area.left, area.top, area.right, area.bottom
    top = 28 if MAC else 0  # bilah menu macOS
    return 0, top, root.winfo_screenwidth(), root.winfo_screenheight()


def animations_enabled():
    """False bila pengguna mematikan animasi di Windows (Pengaturan > Aksesibilitas > Efek animasi)."""
    if WINDOWS:
        flag = wintypes.BOOL(True)
        if ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(flag), 0):  # SPI_GETCLIENTAREAANIMATION
            return bool(flag.value)
    return True


def dark_titlebar(window):
    """Bilah judul gelap. macOS dan Linux mengikuti tema sistem/pengelola jendela."""
    if not WINDOWS:
        return
    try:
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(ctypes.c_int(1)), 4)
    except Exception:
        pass


def set_window_icon(root, ico_path, png_path):
    if WINDOWS:
        root.iconbitmap(ico_path)
    else:
        import tkinter as tk
        root.window_icon = tk.PhotoImage(file=png_path)  # simpan acuan supaya tidak dibuang
        root.iconphoto(True, root.window_icon)


def make_transparent(window):
    """Siapkan jendela tanpa bingkai yang sebagian tembus pandang.

    Mengembalikan warna latar yang dianggap tembus, atau None bila OS tidak mendukung
    (Linux): jendelanya tetap jalan, hanya sudut pilnya tampak kotak hitam.
    """
    if WINDOWS:
        key = "#010203"
        window.attributes("-transparentcolor", key)
        return key
    if MAC:
        window.attributes("-transparent", True)
        return "systemTransparent"
    return None


def hook_app_events(root, reopen, quit):
    """macOS: klik ikon di Dock memulihkan jendela, Cmd+Q menutup dengan rapi (sesi tersimpan)."""
    if MAC:
        root.createcommand("tk::mac::ReopenApplication", reopen)
        root.createcommand("tk::mac::Quit", quit)


# ---------------------------------------------------------------- proses

_instance_lock = None


def single_instance(name):
    """True bila ini satu-satunya ClixMax yang berjalan. Kuncinya dipegang sampai proses selesai."""
    global _instance_lock
    if WINDOWS:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        _instance_lock = kernel32.CreateMutexW(None, False, "%s-single-instance" % name)
        return ctypes.get_last_error() != 183  # ERROR_ALREADY_EXISTS
    import fcntl
    os.makedirs(data_dir(), exist_ok=True)
    fd = os.open(os.path.join(data_dir(), name + ".lock"), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return False
    _instance_lock = fd
    return True


def watch_media_keys(callback):
    """Panggil callback("toggle" | "next" | "prev") saat tombol media keyboard ditekan.

    Baru tersedia di Windows. Mengembalikan False di OS lain.
    """
    if not WINDOWS:
        return False

    def loop():
        user32, actions = ctypes.windll.user32, {1: "toggle", 2: "next", 3: "prev"}
        for ident, vk in ((1, 0xB3), (2, 0xB0), (3, 0xB1)):
            user32.RegisterHotKey(None, ident, 0x4000, vk)  # MOD_NOREPEAT
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == 0x0312 and msg.wParam in actions:  # WM_HOTKEY
                callback(actions[msg.wParam])

    threading.Thread(target=loop, daemon=True).start()
    return True
