"""Nama aplikasi, lokasi berkas, teks tetap, dan utilitas kecil yang dipakai semua modul."""
import json
import os
import time
import traceback

from . import system

APP = "ClixMax"
TITLE = "ClixMax"

DATA = system.data_dir()
CFG = os.path.join(DATA, "config.json")       # setelan, lihat DEFAULTS
LIB = os.path.join(DATA, "library.json")      # {"favorites": [lagu], "playlists": [{"name", "tracks"}], "history": [lagu + "at"]}
SESSION = os.path.join(DATA, "session.json")  # {"queue": [lagu], "pos": indeks, "t": detik}
LYRICS = os.path.join(DATA, "lyrics.json")    # {url: {"found", "lines": [[detik, teks]], "plain", "instrumental"}}
LOCAL = os.path.join(DATA, "local.json")      # {"folder", "files": {path: [mtime, judul, artis, detik]}}
LOG = os.path.join(DATA, "error.log")
ICON = os.path.join(DATA, "clixmax.ico")
ICON_PNG = os.path.join(DATA, "clixmax.png")
PIPE = system.ipc_path("clixmax-mpv")
# Setelan dari nama lama aplikasi ini (YTM Lite) hanya pernah ada di Windows.
OLD_CFG = os.path.join(os.path.dirname(DATA), "ytm-lite", "config.json") if system.WINDOWS else None

DEFAULTS = {
    "volume": 70,          # 0-100
    "radio": True,         # lanjut otomatis dengan lagu sejenis
    "normalize": True,     # ratakan volume antar lagu
    "speed": 1.0,          # 0.5-2.0
    "pitch": 0,            # semiton, -6 sampai +6
    "tint": True,          # warna panel Sedang diputar mengikuti cover
    "tray_close": True,    # tombol tutup menyembunyikan ke tray, musik tetap jalan
    "island": True,        # pulau mini saat jendela di-minimize atau disembunyikan ke tray
    "island_style": "float",  # "float" melayang sedikit di bawah tepi atas, "notch" menempel ke tepi atas
    "island_alpha": 0.0,   # transparansi pulau, 0 (pekat) sampai 0.6
    "island_tuck": True,   # pulau menciut jadi garis tipis saat tidak dipakai (tidak menutupi tab browser)
    "word_lyrics": True,   # tanya Better Lyrics dulu untuk lirik per kata (judul lagu dikirim ke layanan itu)
    "local_dir": "",       # folder musik lokal
    "tray_told": False,    # pemberitahuan "masih jalan di tray" sudah pernah ditampilkan
}

# "Semua" (tanpa filter) jadi bawaan: YouTube Music menaruh hasil paling cocok di atas, apa pun jenisnya.
KINDS = (("Semua", None), ("Lagu", "songs"), ("Video", "videos"), ("Playlist", "playlists"))
PLACEHOLDER = "Mau dengar apa? Ketik judul atau tempel link YouTube"
LOADING = "(memuat judul…)"


def log_error(text):
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + text.rstrip() + "\n")
    except OSError:
        pass


def read_json(path, fallback):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, type(fallback)) else fallback
    except (OSError, ValueError):
        return fallback


def write_json(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(path + ".tmp", path)  # tulis ke berkas sementara dulu supaya tidak pernah setengah jadi
    except OSError:
        log_error(traceback.format_exc())


def fmt_time(sec):
    if sec is None:
        return "-:--"
    sec = int(sec)
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    return "%d:%02d:%02d" % (h, m, s) if h else "%d:%02d" % (m, s)


def seconds_of(text):
    """"3:35" atau "1:00:25" menjadi detik; None bila bukan format waktu."""
    parts = str(text or "").split(":")
    if len(parts) < 2 or not all(p.isdigit() for p in parts):
        return None
    total = 0
    for part in parts:
        total = total * 60 + int(part)
    return total


def slim(track):
    """Bentuk lagu yang disimpan ke berkas: hanya kolom yang perlu."""
    return {key: track.get(key) for key in ("id", "title", "artist", "artist_id", "dur", "art", "kind", "url")}
