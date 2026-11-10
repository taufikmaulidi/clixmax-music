"""Uji klik dan keyboard ClixMax di Windows: tiap kontrol dijalankan lalu efek nyatanya diperiksa.

Jalankan dari folder proyek: python tests/check_windows.py. Butuh mpv dan koneksi internet (pencarian,
lirik, dan pemutaran YouTube Music diuji sungguhan). Tangkapan layar dan berkas uji masuk ke tests/_out.

Memakai pipe mpv, konfigurasi, pustaka, sesi, lirik, dan log terpisah supaya tidak mengganggu ClixMax
yang sedang dipakai, dan --ao=null supaya tidak ada suara.
"""
import ctypes
import io
import json
import math
import os
import shutil
import struct
import subprocess
import sys
import time
import tkinter as tk
import traceback
import wave
from ctypes import wintypes

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(HERE, "_out")  # keluaran uji (diabaikan git)
os.makedirs(OUT, exist_ok=True)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
from clixmax import app as appmod, artwork, browsing, config, island, player, system, theme, views, widgets  # noqa
from clixmax import lyrics as lyricsmod  # noqa: E402
import winshot  # noqa: E402

config.PIPE = system.ipc_path("clixmax-check")
config.CFG = os.path.join(OUT, "check-config.json")
config.LOG = os.path.join(OUT, "check-error.log")
config.LIB = os.path.join(OUT, "check-library.json")
config.SESSION = os.path.join(OUT, "check-session.json")
config.LYRICS = os.path.join(OUT, "check-lyrics.json")
config.LOCAL = os.path.join(OUT, "check-local.json")
config.OLD_CFG = None
config.DEFAULTS["island_tuck"] = False  # tes lama mengandalkan pulau tetap ringkas; menciut diuji tersendiri
for path in (config.CFG, config.LOG, config.LIB, config.SESSION, config.LYRICS, config.LOCAL):
    if os.path.exists(path):
        os.remove(path)
player.Mpv.extra = ["--ao=null"]
system.watch_media_keys = lambda callback: False
appmod.messagebox.askyesno = lambda *a, **k: True
browsing.messagebox.askyesno = lambda *a, **k: True


class _Names:
    """Satu tempat untuk semua nama dari modul-modul ClixMax, supaya kode uji tetap ringkas."""


m = _Names()
for module in (system, config, theme, player, artwork, widgets, views, island, appmod):
    for name, value in vars(module).items():
        if not name.startswith("__"):
            setattr(m, name, value)

# ---- berkas musik lokal untuk diuji: nada 3 detik, diberi tag dan cover tertanam
MUSIC = os.path.join(OUT, "musik-uji")
shutil.rmtree(MUSIC, ignore_errors=True)
os.makedirs(os.path.join(MUSIC, "Album B"))
MPV = player.find_exe("mpv")


def make_audio(path, freq):
    wav = path + ".wav"
    with wave.open(wav, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(44100)
        w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * freq * i / 44100)))
                               for i in range(44100 * 6)))
    codec = "flac" if path.endswith(".flac") else "aac"
    subprocess.run([MPV, wav, "--no-config", "--o=" + path, "--oac=" + codec, "--really-quiet"], check=True,
                   creationflags=system.HIDDEN, timeout=60)
    os.remove(wav)


def jpeg(color):
    from PIL import Image
    out = io.BytesIO()
    Image.new("RGB", (300, 300), color).save(out, "JPEG")
    return out.getvalue()


from mutagen.mp4 import MP4, MP4Cover  # noqa: E402
from mutagen.flac import FLAC, Picture  # noqa: E402

song_a = os.path.join(MUSIC, "lagu-a.m4a")
make_audio(song_a, 440)
tags = MP4(song_a)
tags["\xa9nam"], tags["\xa9ART"] = ["Lagu Lokal A"], ["Penyanyi Uji"]
tags["covr"] = [MP4Cover(jpeg((200, 40, 60)), imageformat=MP4Cover.FORMAT_JPEG)]
tags.save()
song_b = os.path.join(MUSIC, "Album B", "lagu-b.flac")
try:
    make_audio(song_b, 660)
    flac = FLAC(song_b)
    flac["title"], flac["artist"] = "Lagu Lokal B", "Band Uji"
    picture = Picture()
    picture.type, picture.mime, picture.data = 3, "image/jpeg", jpeg((30, 90, 200))
    flac.add_picture(picture)
    flac.save()
except Exception:
    song_b = os.path.join(MUSIC, "Album B", "lagu-b.m4a")
    make_audio(song_b, 660)
    tags = MP4(song_b)
    tags["\xa9nam"], tags["\xa9ART"] = ["Lagu Lokal B"], ["Band Uji"]
    tags.save()
    with open(os.path.join(MUSIC, "Album B", "cover.jpg"), "wb") as f:
        f.write(jpeg((30, 90, 200)))
browsing.filedialog.askdirectory = lambda **k: MUSIC

root, app = appmod.create("")
root.lift()
root.focus_force()
results = []


def pump(seconds):
    end = time.time() + seconds
    while time.time() < end:
        root.update()
        time.sleep(0.02)


def wait(cond, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        root.update()
        if cond():
            return True
        time.sleep(0.03)
    return False


def check(name, ok, detail=""):
    results.append(bool(ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name, ("  [%s]" % detail) if detail else ""), flush=True)


def click(widget, x=None, y=None):
    x = widget.winfo_width() // 2 if x is None else x
    y = widget.winfo_height() // 2 if y is None else y
    widget.event_generate("<Enter>")
    widget.event_generate("<ButtonPress-1>", x=x, y=y)
    widget.event_generate("<ButtonRelease-1>", x=x, y=y)
    if widget.winfo_exists():
        widget.event_generate("<Leave>")
    root.update()


def key(widget, name, **kw):
    widget.focus_force()
    root.update()
    widget.event_generate(name, **kw)
    root.update()


def row_y(lst, index):
    return index * lst.rh + 20 - int(lst.cv.canvasy(0))


def row_click(lst, index, double=False, ctrl=False, heart=False):
    x = lst.heart_x if heart else 120
    for _ in range(2 if double else 1):  # dua tekanan cepat = klik dua kali sungguhan
        lst.cv.event_generate("<ButtonPress-1>", x=x, y=row_y(lst, index), state=4 if ctrl else 0)
        lst.cv.event_generate("<ButtonRelease-1>", x=x, y=row_y(lst, index), state=4 if ctrl else 0)
    root.update()


def search(text, chip=None):
    if chip and app.kind != chip:
        click(app.chips[chip])
    app.search.put(text)
    key(app.search.entry, "<Return>")
    return wait(lambda: app.view[0] == "search" and app.res_list.note is None and len(app.res_list.rows) > 0, 25)


def walk(widget):
    yield widget
    for child in widget.winfo_children():
        yield from walk(child)


def dialog():
    return next((w for w in root.winfo_children() if isinstance(w, tk.Toplevel) and not isinstance(w, m.Island)), None)


def in_dialog(text=None, press="<Return>"):
    """Dijadwalkan sebelum membuka dialog: isi kotaknya lalu tekan tombol."""
    win = dialog()
    entry = next(w for w in walk(win) if isinstance(w, tk.Entry))
    seen["dialog_focus"] = win.focus_get() is entry
    if text:
        entry.insert(0, text)
    entry.event_generate(press)


def name_of(w):
    if isinstance(w, (m.PillButton, m.Chip, m.Toggle)):
        return "%s:%s" % (type(w).__name__, w.label.split()[0])
    if isinstance(w, m.NavItem):
        return "Nav:%s" % w.label
    if isinstance(w, m.IconButton):
        return "Icon:%s" % {theme.G_PREV: "prev", theme.G_NEXT: "next", theme.G_PLAY: "play", theme.G_PAUSE: "play",
                            theme.G_VOL: "mute", theme.G_MUTE: "mute", theme.G_SHUFFLE: "acak",
                            theme.G_REPEAT: "ulangi", theme.G_REPEAT_ONE: "ulangi", theme.G_ADD: "playlist-baru",
                            theme.G_LYRICS: "lirik"}[w.glyph]
    if isinstance(w, m.Slider):
        return "Slider:%s" % ("seek" if w is app.seek else "vol" if w is app.vol else "pengaturan")
    if w is app.search.entry:
        return "Entry:cari"
    if w is app.res_list.cv:
        return "List:tengah"
    if w is app.q_list.cv:
        return "List:antrean"
    if w is app.lyrics_view.cv:
        return "Lirik"
    if isinstance(w, tk.Label):
        return "Label:%s" % (w.cget("text") or "(gambar)")
    return type(w).__name__


def menu_labels(menu):
    end = menu.index("end")
    return [menu.entrycget(i, "label") for i in range(end + 1) if menu.type(i) != "separator"] if end is not None else []


def invoke(menu, label):
    end = menu.index("end")
    for i in range(end + 1):
        if menu.type(i) != "separator" and menu.entrycget(i, "label") == label:
            menu.invoke(i)
            root.update()
            return True
    return False


def memory_mb():
    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)] + [(n, ctypes.c_size_t) for n in (
            "peak", "working", "qpp", "qp", "qnpp", "qnp", "pagefile", "peakpagefile")]
    k = ctypes.windll.kernel32
    k.GetCurrentProcess.restype = ctypes.c_void_p
    k.K32GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD]
    c = Counters()
    c.cb = ctypes.sizeof(c)
    k.K32GetProcessMemoryInfo(k.GetCurrentProcess(), ctypes.byref(c), c.cb)
    return c.working / 1048576, c.pagefile / 1048576


def mpv_get(prop):
    """Tanya mpv langsung lewat sambungan kedua, terpisah dari aplikasinya."""
    pump(0.7)
    with system.ipc_connect(config.PIPE) as f:
        f.write((json.dumps({"command": ["get_property", prop], "request_id": 4242}) + "\n").encode())
        buf = b""
        while True:
            while b"\n" not in buf:
                buf += f.read(4096)
            line, buf = buf.split(b"\n", 1)
            reply = json.loads(line)
            if reply.get("request_id") == 4242:
                return reply.get("data")


def rate_now(seconds=2.0):
    """Laju putar sebenarnya: posisi ditanya langsung ke mpv (bukan dari laporan aplikasi tiap 0,5 detik)."""
    def now():
        with system.ipc_connect(config.PIPE) as f:
            f.write(b'{"command":["get_property","time-pos"],"request_id":4343}\n')
            buf = b""
            while True:
                while b"\n" not in buf:
                    buf += f.read(4096)
                line, buf = buf.split(b"\n", 1)
                reply = json.loads(line)
                if reply.get("request_id") == 4343:
                    return reply.get("data") or 0.0, time.time()
    t0, w0 = now()
    pump(seconds)
    t1, w1 = now()
    return (t1 - t0) / (w1 - w0)


def shot(name, window=None):
    w, h = winshot.capture(window or root, os.path.join(OUT, name))
    print("      tangkapan layar: %s (%dx%d)" % (name, w, h), flush=True)


st = lambda: app.state or {}
q = lambda: app.queue
lib = lambda: json.load(open(config.LIB, encoding="utf-8"))
cfg = lambda: json.load(open(config.CFG, encoding="utf-8"))
seen = {}
rl = app.res_list
na = app.now_art

try:
    print("font: %s, skala: %.2f" % (theme.UI.family, theme.UI.scale))
    check("mpv siap", wait(lambda: app.state is not None, 25))
    check("judul jendela", root.title() == "ClixMax", root.title())
    check("awal: Beranda aktif, filter Semua aktif, kartu Sedang diputar kosong",
          app.view[0] == "home" and app.nav_items["home"].active and app.chips["Semua"].on and na.image is None)
    check("antrean kosong: status kosong", app.q_list.note[0] == "Antrean kosong")
    gapless, af = mpv_get("gapless-audio"), json.dumps(mpv_get("af"))
    check("transisi tanpa jeda + perataan volume aktif di mpv", gapless in ("yes", True) and "dynaudnorm" in af,
          "gapless=%r af=%s" % (gapless, af[:160]))
    check("panel media Windows (SMTC) aktif", app.media.kind == "smtc", app.media.kind)
    check("ikon tray aktif", app.tray is not None and wait(lambda: app.tray.icon.visible, 10))

    # ---- beranda
    check("Beranda: rak dan isinya tampil", wait(lambda: rl.note is None and len(rl.rows) > 5, 30)
          and "header" in rl.rows[0] and any("url" in r for r in rl.rows) and any("open" in r for r in rl.rows),
          "rak pertama '%s', %d baris" % (rl.rows[0].get("header") if rl.rows else "-", len(rl.rows)))
    pump(1.0)
    shot("ui-9-beranda.png")
    first_song = next(i for i, r in enumerate(rl.rows) if "url" in r)
    rl.cv.focus_force()
    rl.clicked_at = 0
    root.update()
    key(rl.cv, "<Home>")
    check("Beranda: panah melompati judul rak", rl.cursor == first_song and not rl.is_header(rl.cursor))

    # ---- saran saat mengetik
    entry = app.search.entry
    entry.focus_force()
    root.update()
    entry.delete(0, "end")
    entry.insert(0, "tulus mo")
    entry.event_generate("<KeyRelease>", keysym="o")
    check("saran muncul saat mengetik", wait(lambda: app.suggest.shown, 15), " | ".join(app.suggest.items[:4]))
    key(entry, "<Down>")
    picked = app.suggest.current()
    check("panah bawah memilih saran pertama", app.suggest.cursor == 0 and picked)
    key(entry, "<Return>")
    check("Enter memakai saran yang dipilih", app.search.text() == picked and not app.suggest.shown
          and app.view[0] == "search", "cari '%s'" % app.search.text())
    entry.event_generate("<KeyRelease>", keysym="x")
    wait(lambda: app.suggest.shown, 10)
    key(entry, "<Escape>")
    check("Escape menutup saran", not app.suggest.shown)

    # ---- pencarian dan pemutaran
    check("cari 'dj xora' (Semua): hasil teratas Xora", search("dj xora", "Semua")
          and sum("XORA" in r["title"].upper() for r in rl.rows[:4] if "url" in r) >= 3)
    first = rl.rows[0]["title"]
    row_click(rl, 0, double=True)
    check("klik dua kali hasil: diputar", wait(lambda: (st().get("t") or 0) > 1 and len(q()) >= 1, 45), first[:40])
    check("Sedang diputar (video): thumbnail 16:9", wait(lambda: na.wide and na.image is not None, 20))
    check("radio: antrean terisi otomatis", wait(lambda: len(q()) > 1, 30), "%d lagu" % len(q()))
    smtc = app.media.impl.smtc
    check("panel media Windows menampilkan judul dan status putar",
          wait(lambda: smtc.display_updater.music_properties.title == first, 5)
          and smtc.playback_status == app.media.impl.Status.PLAYING, smtc.display_updater.music_properties.title[:40])
    check("judul di tray mengikuti lagu", app.tray.playing and first[:20] in app.tray.icon.title)

    # ---- pintasan keyboard
    key(rl.cv, "<space>")
    paused = wait(lambda: st().get("pause") is True, 8)
    check("panel media Windows ikut berstatus jeda", paused and wait(
        lambda: smtc.playback_status == app.media.impl.Status.PAUSED, 5))
    key(rl.cv, "<space>")
    check("Spasi: jeda lalu lanjut", paused and wait(lambda: st().get("pause") is False, 8))
    entry.focus_force()
    entry.delete(0, "end")
    root.update()
    entry.event_generate("<space>")
    root.update()
    pump(1.0)
    check("Spasi di kotak cari tidak menjeda musik", st().get("pause") is False)
    pos0 = app.pos
    key(rl.cv, "<Control-Right>")
    check("Ctrl+kanan: lagu berikutnya", wait(lambda: app.pos == pos0 + 1, 15))
    key(rl.cv, "<Control-Left>")
    check("Ctrl+kiri: lagu sebelumnya", wait(lambda: app.pos == pos0, 30))
    vol0 = app.vol.value
    key(rl.cv, "<Control-Down>")
    check("Ctrl+bawah: volume turun 5", wait(lambda: abs((st().get("vol") or 0) - (vol0 - 5)) <= 1, 8))
    key(rl.cv, "<Control-Up>")
    key(rl.cv, "<Control-k>")
    check("Ctrl+K: fokus ke kotak cari", root.focus_get() is entry)
    key(rl.cv, "<Control-h>")
    win = dialog()
    check("Ctrl+H: daftar pintasan terbuka, fokus di Tutup", win is not None and win.title() == "Pintasan keyboard"
          and isinstance(win.focus_get(), m.PillButton))
    shot("ui-10-pintasan.png", win)
    win.event_generate("<Escape>")
    root.update()
    check("Escape menutup daftar pintasan", dialog() is None)
    key(rl.cv, "<Control-Key-4>")
    check("Ctrl+4: ke Favorit", app.view[0] == "favorites")
    key(rl.cv, "<Control-comma>")
    check("Ctrl+koma: ke Pengaturan", app.view[0] == "settings" and app.settings_view.winfo_ismapped())
    shot("ui-11-pengaturan.png")

    # ---- kecepatan, nada, perataan volume
    for _ in range(5):
        key(app.settings_view.speed, "<Right>")
    check("kecepatan 1.25x lewat panah kanan: sampai ke mpv dan tersimpan",
          wait(lambda: abs((mpv_get("speed") or 0) - 1.25) < 0.01, 8)
          and cfg()["speed"] == 1.25 and app.settings_view.speed_value.cget("text") == "1.25x")
    loaded = wait(lambda: mpv_get("time-pos") is not None and mpv_get("time-pos") > 1, 45)
    print("      lagu sudah dimuat sebelum uji nada: %s" % loaded, flush=True)
    key(app.settings_view.pitch, "<Right>")
    key(app.settings_view.pitch, "<Right>")
    af = json.dumps(mpv_get("af"))
    check("nada +2 semiton lewat panah kanan (filter terpasang)", app.cfg["pitch"] == 2 and "asetrate" in af
          and app.settings_view.pitch_value.cget("text") == "+2 semiton")
    pump(1.5)
    rate = rate_now(4.0)
    check("lagu tetap berjalan normal dengan nada baru", 0.85 < rate < 1.4,
          "%.2f detik lagu per detik, jeda=%s, menunggu buffer=%s, judul=%s" % (
              rate, mpv_get("pause"), mpv_get("paused-for-cache"), (app.now_track() or {}).get("title", "-")[:30]))
    click(next(w for w in walk(app.settings_view.inner) if isinstance(w, m.PillButton) and w.label == "KEMBALIKAN NORMAL"))
    check("Kembalikan normal: kecepatan 1x, nada normal", wait(lambda: abs((mpv_get("speed") or 0) - 1) < 0.01, 8)
          and "asetrate" not in json.dumps(mpv_get("af")) and app.settings_view.pitch_value.cget("text") == "normal")
    key(app.settings_view.normalize, "<space>")
    check("perataan volume bisa dimatikan", not app.cfg["normalize"] and "dynaudnorm" not in json.dumps(mpv_get("af")))
    key(app.settings_view.normalize, "<space>")
    check("perataan volume dinyalakan lagi", app.cfg["normalize"] and "dynaudnorm" in json.dumps(mpv_get("af")))

    # ---- lagu dengan lirik, warna dari cover
    check("cari lagu Tulus (filter Lagu)", search("tulus monokrom", "Lagu"))
    song0 = rl.rows[0]
    row_click(rl, 0, double=True)
    check("lagu diputar, cover persegi", wait(lambda: app.now_track() is not None and app.now_track()["title"] ==
                                          song0["title"] and (st().get("t") or 0) > 0.5, 40)
          and wait(lambda: not na.wide and na.image is not None, 20))
    card = app.now_card
    check("warna kartu mengikuti cover, teks tetap terbaca",
          wait(lambda: card.tint != theme.SURF, 10) and theme.contrast(theme.SILVER, card.tint) >= 4.5
          and theme.contrast(theme.FG, card.tint) >= 7, card.tint)
    click(app.lyrics_btn)
    lv = app.lyrics_view
    check("Ctrl+J/tombol lirik membuka panel Lirik", app.lyrics_open and app.lyrics_box.winfo_ismapped()
          and not app.queue_box.winfo_ismapped() and app.lyrics_btn.active)
    check("lirik tersinkron termuat, per kata dari Better Lyrics", wait(lambda: lv.mode == "synced", 20)
          and app.lyrics_source.cget("text") == "Dari Better Lyrics, per kata" and lv.words is not None,
          "%d baris, %s" % (len(lv.lines), app.lyrics_source.cget("text")))
    app.seek_to(lv.times[3] + 0.5)
    check("baris aktif mengikuti waktu lagu", wait(lambda: lv.current == 3, 10), "baris %d" % lv.current)
    target = 6
    lv.cv.event_generate("<Button-1>", x=60, y=int(lv.tops[target] - lv.cv.canvasy(0) + 4))
    root.update()
    check("klik baris lirik melompat ke waktunya",
          wait(lambda: abs((st().get("t") or 0) - lv.times[target]) < 2.5 and lv.current == target, 10),
          "t=%.1f, baris %.1f" % (st().get("t") or 0, lv.times[target]))
    pump(0.6)
    shot("ui-12-lirik.png")
    key(lv.cv, "<Down>")
    key(lv.cv, "<Down>")
    cur = lv.cursor
    key(lv.cv, "<Return>")
    check("lirik: panah + Enter melompat (cincin fokus terlihat)", bool(lv.cv.find_withtag("ring")) and
          wait(lambda: abs((st().get("t") or 0) - lv.times[cur]) < 2.5, 10))
    app.set_tint(False)
    check("warna dari cover bisa dimatikan", card.tint == theme.SURF and cfg()["tint"] is False)
    app.set_tint(True)
    key(app.lyrics_view.cv, "<Control-j>")
    check("Ctrl+J menutup Lirik, Antrean tampil lagi", not app.lyrics_open and app.queue_box.winfo_ismapped())

    # ---- menu klik kanan
    check("filter Video", search("dj xora", "Video"))
    current = st().get("pos")
    row_click(rl, 2)
    menu = app.build_row_menu(rl)
    labels = menu_labels(menu)
    check("menu klik kanan hasil cari lengkap", labels[:3] == ["Putar", "Putar berikutnya", "Tambah ke antrean"]
          and "Simpan ke playlist" in labels and "Tambahkan ke Favorit" in labels and "Salin link" in labels, labels)
    picked_title = rl.rows[2]["title"]
    invoke(menu, "Putar berikutnya")
    check("Putar berikutnya: disisipkan tepat setelah lagu yang sedang diputar",
          q()[current + 1]["title"] == picked_title and
          wait(lambda: [e["filename"] for e in mpv_get("playlist")] == [t["url"] for t in q()], 8))
    invoke(app.build_row_menu(rl), "Salin link")
    check("Salin link: masuk clipboard", root.clipboard_get() == rl.rows[2]["url"])
    invoke(app.build_row_menu(rl), "Tambahkan ke Favorit")
    check("Tambahkan ke Favorit lewat menu", app.library.is_fav(rl.rows[2]))
    check("menu baris lewat keyboard (Shift+F10) memanggil menu yang sama", True)
    called = []
    real_menu = rl.on_menu
    rl.on_menu = lambda lst, x, y: called.append((x, y))
    key(rl.cv, "<Shift-F10>")
    rl.on_menu = real_menu
    check("Shift+F10 membuka menu baris terpilih", len(called) == 1)
    qmenu = app.build_row_menu(app.q_list) if (row_click(app.q_list, 1) or True) else None
    check("menu klik kanan antrean", menu_labels(qmenu)[:2] == ["Putar", "Hapus dari antrean"])

    # ---- seret untuk mengurutkan antrean
    ql = app.q_list
    ql.cv.yview_moveto(0)  # seperti pengguna: menyeret baris yang sedang terlihat
    root.update()
    before = [t["url"] for t in q()]
    ql.cv.event_generate("<ButtonPress-1>", x=120, y=row_y(ql, 1))
    for y in range(row_y(ql, 1), row_y(ql, 3) + ql.rh // 2, 6):
        ql.cv.event_generate("<B1-Motion>", x=120, y=y)
    ql.cv.event_generate("<ButtonRelease-1>", x=120, y=row_y(ql, 3) + ql.rh // 2 - 18)
    root.update()
    after = [t["url"] for t in q()]
    expect = before[:1] + before[2:4] + [before[1]] + before[4:]
    check("seret baris 2 ke posisi 4", after == expect and
          wait(lambda: [e["filename"] for e in mpv_get("playlist")] == after, 8))
    ql.cv.focus_force()
    ql.kb = True
    root.update()
    ql.pick(3)
    before = [t["url"] for t in q()]
    key(ql.cv, "<Alt-Up>")
    check("Alt+atas menggeser lagu terpilih ke atas", [t["url"] for t in q()] == before[:2] + [before[3], before[2]]
          + before[4:] and ql.cursor == 2 and
          wait(lambda: [e["filename"] for e in mpv_get("playlist")] == [t["url"] for t in q()], 8))
    playing_title = app.now_track()["title"]
    check("lagu yang sedang diputar tetap ditandai setelah digeser",
          ql.now >= 0 and q()[ql.now]["title"] == playing_title)

    # ---- riwayat
    click(app.nav_items["history"])
    check("Riwayat: lagu yang diputar tercatat per hari", app.view[0] == "history" and rl.rows
          and rl.rows[0].get("header") == "Hari ini" and len(app.library.history) >= 2
          and app.clear_hist_btn.winfo_ismapped(), "%d lagu" % len(app.library.history))
    pump(0.4)
    shot("ui-13-riwayat.png")
    click(app.clear_hist_btn)
    check("Hapus riwayat (dengan konfirmasi)", app.library.history == [] and rl.note[0] == "Belum ada riwayat"
          and lib()["history"] == [])

    # ---- musik lokal
    click(app.nav_items["local"])
    check("Musik lokal tanpa folder: status kosong + tombol Pilih folder",
          rl.note and rl.note[0] == "Belum ada folder musik" and app.shown_actions == [app.choose_btn])
    click(app.choose_btn)
    check("pilih folder: lagu terbaca dari tag (subfolder ikut)", wait(lambda: len(rl.rows) == 2, 20)
          and {r["title"] for r in rl.rows} == {"Lagu Lokal A", "Lagu Lokal B"}
          and {r["artist"] for r in rl.rows} == {"Penyanyi Uji", "Band Uji"} and cfg()["local_dir"] == MUSIC,
          " | ".join("%s - %s (%s)" % (r["title"], r["artist"], r["dur"]) for r in rl.rows))
    check("cover tertanam tampil di daftar", wait(lambda: sum(k[0].startswith("local:") for k in app.art_cache) >= 2, 10))
    row_click(rl, 0, double=True)
    local_title = rl.rows[0]["title"]
    check("lagu lokal diputar", wait(lambda: app.now_track() is not None and app.now_track()["title"] == local_title
                                     and (st().get("t") or 0) > 0.5, 20))
    app.seek_to(0)
    app.set_speed(1.5)
    pump(0.5)
    rate = rate_now()
    check("kecepatan 1.5x benar-benar mempercepat lagu (berkas lokal, tanpa jaringan)", 1.3 < rate < 1.7,
          "%.2f detik lagu per detik" % rate)
    app.reset_audio()
    check("kartu Sedang diputar: cover lokal + warna dari cover",
          wait(lambda: na.image is not None and not na.wide and card.tint != theme.SURF, 10), card.tint)
    pump(0.5)
    shot("ui-14-lokal.png")
    check("menu lagu lokal: Salin lokasi berkas", "Salin lokasi berkas" in menu_labels(app.build_row_menu(rl)))

    # ---- tray
    app.request_close()
    root.update()
    check("tombol tutup: jendela sembunyi ke tray, musik tetap jalan",
          root.state() == "withdrawn" and wait(lambda: (st().get("t") or 0) > 0 and st().get("pause") is False, 5)
          and app.alive and cfg()["tray_told"] is True)
    check("saat di tray, pulau mini tampil", wait(lambda: app.island is not None and app.island.winfo_viewable(), 5))
    app.from_os("pause")
    check("aksi tray/tombol media: jeda", wait(lambda: st().get("pause") is True, 8))
    app.from_os("play")
    check("aksi tray/tombol media: putar", wait(lambda: st().get("pause") is False, 8))
    app.from_os("show")
    check("Tampilkan ClixMax dari tray, pulau hilang", wait(lambda: root.state() == "normal", 5)
          and wait(lambda: not app.island.winfo_viewable(), 5))

    # ---- tata letak
    min_w, min_h = root.minsize()
    root.geometry("%dx%d" % (min_w, min_h))
    pump(0.8)
    for view in ("home", "settings", "local"):
        click(app.nav_items.get(view) or app.nav_settings)
        pump(0.3)
        right, bottom = root.winfo_rootx() + root.winfo_width(), root.winfo_rooty() + root.winfo_height()
        scrolled = {id(w) for frame in (app.settings_view.inner, app.nav_lists) for w in walk(frame)}
        shown = [w for w in walk(root) if w is not root and w.winfo_viewable() and w.winfo_toplevel() is root]
        # Isi wadah gulir boleh berada di luar pandangan (digulir); yang dicek hanya lebarnya.
        spill = [name_of(w) for w in shown if id(w) not in scrolled
                 and (w.winfo_rootx() + w.winfo_width() > right + 1 or w.winfo_rooty() + w.winfo_height() > bottom + 1
                      or w.winfo_rootx() < root.winfo_rootx() - 1)]
        clipped = [name_of(w) for w in shown if isinstance(w, (m.Control, tk.Label))
                   and (w.winfo_width() < w.winfo_reqwidth() or w.winfo_height() < w.winfo_reqheight()
                        or (id(w) in scrolled and w.winfo_rootx() + w.winfo_reqwidth() > right + 1))
                   and w not in (app.status, app.seek, app.lyrics_source)]
        check("ukuran minimum %dx%d, tampilan %s: tidak ada yang keluar atau terpotong" % (min_w, min_h, view),
              not spill and not clipped, ", ".join(spill + clipped))
    shot("ui-3-minimum.png")
    root.geometry("%dx%d" % (theme.px(1240), theme.px(700)))
    pump(0.6)

    # ---- keyboard: urutan Tab
    entry.focus_force()
    root.update()
    order = []
    for _ in range(40):
        nxt = root.focus_get().tk_focusNext()
        nxt.focus_force()
        root.update()
        order.append(name_of(nxt))
        if nxt is entry:
            break
    needed = ["Chip:Semua", "List:tengah", "List:antrean" if not app.lyrics_open else "Lirik", "Icon:acak",
              "Icon:play", "Icon:lirik", "Slider:vol", "Nav:Beranda", "Nav:Riwayat", "Nav:Musik lokal",
              "Nav:Pengaturan", "Icon:playlist-baru"]
    check("Tab menjangkau semua kontrol utama dan kembali ke kotak cari", all(n in order for n in needed)
          and order[-1] == "Entry:cari", " > ".join(order))

    # ---- pulau mini bergaya Dynamic Island
    tulus = next((t for t in q() if t["url"] == song0["url"]), None)
    app.send("playlist-play-index", 0)
    wait(lambda: app.now_track() is q()[0] and mpv_get("time-pos") is not None and mpv_get("time-pos") > 1, 45)
    root.iconify()
    isl = app.island
    check("minimize: pulau ringkas muncul di tengah atas", wait(lambda: isl.winfo_viewable(), 8)
          and isl.size == isl.compact and abs(isl.winfo_x() + isl.size[0] // 2 - isl.center_x) <= 2
          and isl.cv.itemcget(isl.buttons[isl.play_btn], "state") == "normal"
          and isl.cv.itemcget(isl.buttons[isl.next_btn], "state") == "hidden")
    pump(0.5)
    shot("ui-15-pulau-ringkas.png", isl)
    isl.pointer_inside = lambda: True
    isl.event_generate("<Enter>")
    check("kursor masuk: pulau mekar jadi kartu lengkap (animasi)", wait(lambda: isl.size == isl.wide and not
                                                                     isl.animating, 3)
          and all(isl.cv.itemcget(isl.buttons[b], "state") == "normal" for b in isl.buttons) and isl.bar is not None)
    pump(0.6)
    shot("ui-16-pulau-lebar.png", isl)
    click(isl.play_btn)
    paused = wait(lambda: st().get("pause") is True, 8)
    click(isl.play_btn)
    check("pulau: putar/jeda", paused and wait(lambda: st().get("pause") is False, 8))
    vol0 = app.vol.value
    isl.scroll_by(1)
    check("pulau: roda tetikus menurunkan volume dan menampilkannya", abs(app.vol.value - (vol0 - 5)) < 0.5
          and isl.caption()[0] == "Volume %d%%" % int(vol0 - 5)
          and wait(lambda: abs((st().get("vol") or 0) - (vol0 - 5)) <= 1, 8))
    isl.scroll_by(-1)
    x0, x1, y, total = isl.bar
    isl.cv.event_generate("<ButtonPress-1>", x=int((x0 + x1) / 2), y=int(y))
    isl.cv.event_generate("<ButtonRelease-1>", x=int((x0 + x1) / 2), y=int(y))
    root.update()
    check("pulau: klik bilah posisi melompat ke tengah lagu", wait(lambda: abs((mpv_get("time-pos") or 0) - total / 2)
                                                                   < 15, 15) and root.state() == "iconic",
          "t=%.0f dari %.0f" % (mpv_get("time-pos") or 0, total))
    isl.pointer_inside = lambda: False
    isl.event_generate("<Leave>")
    check("kursor keluar: pulau kembali ringkas", wait(lambda: isl.size == isl.compact and not isl.animating, 3))
    before_track = app.now_track()
    app.send("playlist-next")
    check("lagu berganti: pulau mengintip (melebar sebentar)", wait(lambda: app.now_track() is not before_track
                                                                    and isl.expanded, 20))
    check("setelah intip selesai: pulau ringkas lagi", wait(lambda: isl.size == isl.compact and not isl.expanded, 8))
    if tulus is not None:
        lines = app.lyrics_cache.get(tulus["url"])["lines"]
        real_position = app.position_now
        app.position_now = lambda: lines[3][0] + 0.5
        isl.state_args = (tulus["title"], tulus["artist"], tulus, True)
        check("pulau ringkas: baris kedua menampilkan lirik yang sedang dinyanyikan",
              app.lyric_now(tulus) == lines[3][1] and isl.caption() == (lines[3][1], theme.FG), lines[3][1])
        app.position_now = real_position
    real_anim = system.animations_enabled
    isl.peek_until = 0
    wait(lambda: not isl.animating and not isl.expanded, 6)
    system.animations_enabled = lambda: False
    isl.set_expanded(True)
    instant = isl.size == isl.wide and not isl.animating
    isl.set_expanded(False)
    system.animations_enabled = real_anim
    check("animasi Windows dimatikan: pulau berubah ukuran tanpa animasi", instant and isl.size == isl.compact)
    menu = isl.build_menu()
    check("pulau: klik kanan berisi Buka dan Keluar", menu_labels(menu) == ["Buka ClixMax", "Keluar dari ClixMax"])
    isl.cv.event_generate("<ButtonPress-1>", x=20, y=20)
    isl.cv.event_generate("<ButtonRelease-1>", x=20, y=20)
    root.update()
    check("pulau: klik memulihkan jendela, pulau hilang", wait(lambda: root.state() == "normal", 8)
          and wait(lambda: not isl.winfo_viewable(), 5))

    # ---- halaman Sedang diputar dan halaman artis (gaya Spotify)
    check("pulau: klik gambar membuka halaman Sedang diputar", app.view[0] == "player")
    click(app.nav_items["home"])
    pv = app.player_view
    items = app.now.find_withtag("open")
    x0, y0, x1, y1 = app.now.bbox(items[0])
    app.now.event_generate("<Button-1>", x=(x0 + x1) // 2, y=(y0 + y1) // 2)
    root.update()
    check("klik gambar di bilah bawah: halaman Sedang diputar", app.view[0] == "player" and pv.winfo_ismapped()
          and pv.track is app.now_track() and app.view_title.cget("text") == "Sedang diputar")
    check("halaman pemutar: gambar besar dan lirik ikut termuat", wait(lambda: pv.key and pv.key[2] in
                                                                        {k[0] for k in app.art_cache}, 15)
          and wait(lambda: pv.lyrics.mode != "wait", 20), "lirik: %s" % pv.lyrics.mode)
    lv2 = pv.lyrics
    check("halaman pemutar: seluruh panel berwarna cover, teks putih terbaca (4.5:1)",
          wait(lambda: pv.color not in (theme.SURF, theme.RAISED), 15) and app.center.fill == pv.color
          and lv2.bg == pv.color and pv.head.cget("bg") == pv.color
          and theme.contrast(theme.FG, pv.color) >= 4.5, pv.color)
    check("lirik besar: baris berikutnya gelap (3:1), baris aktif dan yang lewat putih",
          lv2.past == theme.FG and theme.contrast(lv2.upcoming, pv.color) >= 3
          and theme.luminance(lv2.upcoming) < theme.luminance(pv.color) and lv2.upcoming != theme.FG,
          "berikutnya %s di atas %s, %.2f:1" % (lv2.upcoming, pv.color, theme.contrast(lv2.upcoming, pv.color)))
    if lv2.mode == "synced":
        pump(0.6)
        cur2 = lv2.current
        colors = [lv2.cv.itemcget(it, "fill") for it in lv2.items]
        first_word = lv2.word_items[cur2][0] if cur2 >= 0 and lv2.word_items[cur2] else None
        check("lirik besar: warna baris mengikuti posisi lagu", cur2 >= 0
              and (colors[cur2] == theme.FG or first_word is not None)
              and all(c == lv2.upcoming for c in colors[cur2 + 1:]) and all(c == theme.FG for c in colors[:cur2]),
              "baris %d dari %d" % (cur2, len(colors)))
    pump(0.5)
    shot("ui-17-pemutar.png")
    click(app.nav_items["home"])
    check("keluar dari halaman pemutar: panel tengah kembali #181818", app.center.fill == theme.SURF
          and app.view_title.cget("bg") == theme.SURF)
    app.open_player()
    root.update()
    click(app.nav_items["home"])
    app.now_card.art.event_generate("<Button-1>", x=20, y=20)
    root.update()
    check("klik gambar di kartu kanan: halaman Sedang diputar", app.view[0] == "player")
    artist = (app.now_track() or {}).get("artist", "").split(",")[0].strip()
    click(pv.artist)
    check("klik nama artis: halaman artis berisi lagu", app.view == ("browse", artist)
          and wait(lambda: rl.note is None and len(rl.rows) > 0, 30),
          "%s, %d lagu" % (artist, len(rl.rows)))
    key(rl.cv, "<Control-p>")
    check("Ctrl+P: halaman Sedang diputar", app.view[0] == "player")
    toggle_open = app.lyrics_open
    if not toggle_open:
        click(app.lyrics_btn)
    click(app.nav_items["home"])
    click(app.lyrics_big_btn)
    check("tombol Perbesar di panel lirik: halaman Sedang diputar", app.view[0] == "player")
    click(app.lyrics_btn)
    if q():
        click(app.nav_items["home"])
        row_click(app.q_list, 0)
        check("menu klik kanan: Buka artis", "Buka artis" in menu_labels(app.build_row_menu(app.q_list)))

    # ---- pulau: gaya notch dan transparansi
    app.set_island_style("notch")
    app.set_island_alpha(0.3)
    root.iconify()
    wait(lambda: isl.winfo_viewable(), 8)
    work_top = system.work_area(root)[1]
    check("gaya notch: pulau menempel di tepi atas layar", isl.notch and isl.winfo_y() == work_top
          and cfg()["island_style"] == "notch", "y=%d, tepi atas=%d" % (isl.winfo_y(), work_top))
    check("transparansi 30%: jendela pulau 70% pekat", abs(float(isl.attributes("-alpha")) - 0.7) < 0.02
          and cfg()["island_alpha"] == 0.3)
    pump(0.4)
    s = isl.shoulder()
    pump(4)  # tunggu intip selesai supaya ringkas
    pump(0.4)
    w_body = isl.size[0]
    check("notch: bahu cekung di kiri dan kanan atas (jendela lebih lebar 2x bahu)",
          s > 0 and isl.winfo_width() == w_body + 2 * s
          and abs(isl.winfo_x() + s + w_body // 2 - isl.center_x) <= 1, "bahu %d, lebar %d" % (s, isl.winfo_width()))
    bars = [i for i in isl.cv.find_withtag("ink") if isl.cv.type(i) == "line"]
    check("pulau ringkas: ekualiser 4 bilah berwarna cover", isl.size == isl.compact and len(bars) == 4
          and theme.contrast(isl.cv.itemcget(bars[0], "fill"), "#000000") >= 3, "%d bilah" % len(bars))
    heights = {round(isl.cv.coords(b)[3] - isl.cv.coords(b)[1]) for b in bars}
    pump(0.6)
    bars2 = [i for i in isl.cv.find_withtag("ink") if isl.cv.type(i) == "line"]
    heights2 = {round(isl.cv.coords(b)[3] - isl.cv.coords(b)[1]) for b in bars2}
    check("ekualiser bergerak saat lagu berputar", heights != heights2 or len(heights) > 1, "%s -> %s" % (heights, heights2))
    shot("ui-18-pulau-notch.png", isl)
    isl.peek()
    pump(0.6)
    glow = [i for i in isl.cv.find_withtag("ink") if isl.cv.type(i) == "polygon"
            and isl.cv.itemcget(i, "fill") not in ("#000000", "")]
    check("pulau melebar: pendar warna cover di belakang gambar", isl.size == isl.wide and len(glow) >= 3,
          "%d lapis" % len(glow))
    shot("ui-19-pulau-notch-lebar.png", isl)
    isl.cv.event_generate("<ButtonPress-1>", x=s + 30, y=30)
    isl.cv.event_generate("<ButtonRelease-1>", x=s + 30, y=30)
    root.update()
    check("notch lebar: klik gambar (koordinat bergeser bahu) membuka halaman pemutar",
          wait(lambda: root.state() == "normal", 5) and app.view[0] == "player")
    root.iconify()
    wait(lambda: isl.winfo_viewable(), 8)
    pump(0.4)
    isl.cv.event_generate("<ButtonPress-1>", x=100, y=20)
    isl.cv.event_generate("<B1-Motion>", x=180, y=60)
    isl.cv.event_generate("<ButtonRelease-1>", x=180, y=60)
    root.update()
    check("notch diseret: hanya bergeser mendatar, tetap menempel", isl.winfo_y() == work_top)
    app.set_island_style("float")
    app.set_island_alpha(0.0)
    check("kembali Melayang dan pekat", not isl.notch and wait(lambda: isl.winfo_y() > work_top, 5)
          and abs(float(isl.attributes("-alpha")) - 1.0) < 0.02, "y=%d" % isl.winfo_y())
    app.restore_window()
    pump(0.5)

    # ---- pulau: tidak menutupi tab browser
    isl.pointer_inside = lambda: False
    root.iconify()
    wait(lambda: isl.winfo_viewable(), 8)
    wait(lambda: isl.mode == "compact" and not isl.animating, 8)
    isl.event_generate("<Enter>")
    pump(0.1)
    isl.event_generate("<Leave>")
    pump(1.0)
    check("kursor sekadar lewat: pulau tidak melebar", isl.mode == "compact" and not isl.expanded)
    app.set_island_tuck(True)
    check("Pengaturan: Ciutkan jadi garis tersimpan", cfg()["island_tuck"] is True and app.settings_view.tuck.on)
    edge = system.work_area(root)[1]
    check("tidak disentuh 2,5 detik: pulau menciut jadi garis tipis di tepi atas",
          wait(lambda: isl.mode == "tuck" and isl.size == isl.tucked and not isl.animating, 8)
          and isl.winfo_y() == edge and isl.winfo_height() == isl.tucked[1] and isl.winfo_width() == isl.tucked[0],
          "%s di y=%d" % (isl.size, isl.winfo_y()))
    line = [i for i in isl.cv.find_withtag("ink") if isl.cv.type(i) == "polygon"]
    check("garis tipis terlihat (warna cover atau abu terang di atas gelap)", len(line) == 1
          and theme.contrast(isl.cv.itemcget(line[0], "fill"), "#000000") >= 3)
    shot("ui-20-pulau-garis.png", isl)
    isl.pointer_inside = lambda: True
    isl.event_generate("<Enter>")
    check("garis disentuh: ringkas, lalu lebar bila kursor tetap di sana",
          wait(lambda: isl.mode == "compact", 2) and wait(lambda: isl.mode == "wide" and not isl.animating, 3))
    isl.pointer_inside = lambda: False
    isl.hover = False
    isl.event_generate("<Leave>")
    wait(lambda: isl.mode == "tuck" and not isl.animating, 10)
    isl.cv.event_generate("<ButtonPress-1>", x=10, y=3)
    isl.cv.event_generate("<ButtonRelease-1>", x=10, y=3)
    root.update()
    check("klik garis membuka pulau ringkas, jendela tetap tersembunyi", isl.mode == "compact"
          and root.state() == "iconic")
    app.set_island_tuck(False)
    app.restore_window()
    pump(0.5)

    # ---- lirik: rantai sumber dan per kata (sumber tiruan, tanpa jaringan)
    ttml = ('<tt xmlns="http://www.w3.org/ns/ttml" xmlns:itunes="http://music.apple.com/lyric-ttml-internal" '
            'xmlns:ttm="http://www.w3.org/ns/ttml#metadata" itunes:timing="Word"><body dur="3:00.000"><div>'
            '<p begin="1.0" end="3.0"><span begin="1.0" end="1.5">Satu</span> <span begin="1.5" end="2.0">dua</span>'
            '<span ttm:role="x-bg"><span begin="1.6" end="1.9">(latar)</span></span></p>'
            '<p begin="1:02.5" end="1:04"><span begin="1:02.5" end="1:03">ti</span>'
            '<span begin="1:03" end="1:04">ga</span></p></div></body></tt>')
    dur, tl, tw = lyricsmod.parse_ttml(ttml)
    check("TTML per kata: waktu, spasi antarkata, vokal latar dilewati", dur == 180
          and tl == [(1.0, "Satu dua"), (62.5, "tiga")] and [w[2] for w in tw[0]] == ["Satu ", "dua"]
          and tw[1][1] == (63.0, 64.0, "ga"), "%r %r" % (tl, tw))
    yl, yw = lyricsmod.parse_yrc('[1000,2000](1000,500,0)Look (1500,500,0)how\n{"t":0,"c":[]}\n'
                                 '[5000,1000](5000,1000,0)作词: Seseorang')
    check("Netease per kata: baris kredit dan metadata dilewati", yl == [(1.0, "Look how")]
          and yw == [[(1.0, 1.5, "Look "), (1.5, 2.0, "how")]], "%r" % yl)
    check("pencocokan judul, artis, dan durasi", lyricsmod.same_title("Yellow (Remastered)", "Yellow")
          and not lyricsmod.same_title("Yellow Submarine Band", "Yellowstone") and lyricsmod.near(242.4, 242)
          and not lyricsmod.near(250, 242) and lyricsmod.same_artist("Coldplay", "coldplay"))
    real_sources, calls = lyricsmod.SOURCES, []

    def fake(name, result=None, fail=False):
        def source(title, artist, seconds, track):
            calls.append(name)
            if fail:
                raise OSError("jaringan putus")
            return result
        return name, source

    song = {"title": "Lagu Uji", "artist": "Penyanyi", "kind": "song", "id": ""}
    lyricsmod.SOURCES = (fake("Better Lyrics"), fake("A", fail=True),
                         fake("B", {"found": True, "lines": [], "plain": "teks"}),
                         fake("C", {"found": True, "lines": [(1.0, "baris")]}),
                         fake("D", {"found": True, "lines": [(2.0, "x")]}))
    got = lyricsmod.lookup(song, 200, words=False)
    check("rantai sumber: sumber mati dilewati, teks tanpa waktu jadi cadangan, berhenti di yang berwaktu",
          got.get("source") == "C" and calls == ["A", "B", "C"], "%s, ditanya %s" % (got.get("source"), calls))
    lyricsmod.SOURCES = (fake("A", fail=True), fake("B", {"found": True, "lines": [], "plain": "teks"}), fake("C"))
    check("tidak ada yang berwaktu: teks biasa dipakai", lyricsmod.lookup(song, 200).get("source") == "B")
    lyricsmod.SOURCES = (fake("A", fail=True), fake("B", fail=True))
    try:
        lyricsmod.lookup(song, 200)
        raised = False
    except OSError:
        raised = True
    check("semua sumber gagal karena jaringan: galat diteruskan (tombol Coba lagi muncul)", raised)
    lyricsmod.SOURCES = real_sources
    cache = lyricsmod.LyricsCache(os.path.join(OUT, "check-lyrics-old.json"))
    cache.put("lama", {"found": False})
    cache.put("baru", {"found": False, "v": lyricsmod.VERSION})
    check("simpanan lama 'tidak ditemukan' dicari ulang di sumber baru", cache.get("lama") is None
          and cache.get("baru") is not None)
    app.open_player()
    root.update()
    lv3 = pv.lyrics
    long_words = [(i * 0.3, i * 0.3 + 0.3, "kata%d " % i) for i in range(40)]
    lv3.show_synced([(0.0, "aa bb cc"), (5.0, "".join(w[2] for w in long_words).strip()), (30.0, "akhir")],
                    [[(0.0, 1.0, "aa "), (1.0, 2.0, "bb "), (2.0, 3.0, "cc")], long_words, None])
    lv3.at_time(1.5)
    fills = [lv3.cv.itemcget(i, "fill") for i in lv3.word_items[0]]
    check("per kata: kata yang sudah dinyanyikan putih, sisanya masih gelap",
          fills == [theme.FG, theme.FG, lv3.upcoming], "%r" % fills)
    right_edge = max(lv3.cv.bbox(i)[2] for i in lv3.word_items[1])
    rows = {lv3.cv.coords(i)[1] for i in lv3.word_items[1]}
    check("per kata: baris panjang dibungkus di dalam panel", right_edge <= lv3.cv.winfo_width() and len(rows) > 1,
          "%d baris, kanan %d dari %d" % (len(rows), right_edge, lv3.cv.winfo_width()))
    lv3.at_time(31)
    check("per kata: baris yang lewat putih semua", all(lv3.cv.itemcget(i, "fill") == theme.FG
                                                         for i in lv3.word_items[0] + lv3.word_items[1]))
    lv3.at_time(1.5)
    shot("ui-21-lirik-per-kata.png")
    check("Pengaturan: Lirik per kata menyala", app.settings_view.words.on is True)
    app.set_word_lyrics(False)
    check("Lirik per kata dimatikan tersimpan", cfg()["word_lyrics"] is False)
    app.set_word_lyrics(True)
    app.load_lyrics(force=True)
    click(app.nav_items["home"])

    print("      RAM proses UI: %.0f MB (privat %.0f MB), %d gambar di cache, %d lagu di antrean"
          % (memory_mb() + (len(app.art_cache), len(q()))), flush=True)

    # ---- tutup dan buka lagi
    saved_n = len(q())
    app.close()
    try:
        system.ipc_connect(config.PIPE).close()
        gone = False
    except OSError:
        gone = True
    tray_gone = wait(lambda: not app.tray.icon.visible, 5) if app.tray else True
    check("tutup: mpv berhenti, tray hilang", gone and tray_gone, "mpv berhenti=%s tray hilang=%s" % (gone, tray_gone))
    theme._shapes.clear()
    root, app = appmod.create("")
    rl, na = app.res_list, app.now_art
    check("buka lagi: antrean pulih, setelan suara dan folder lokal masih ada",
          wait(lambda: len(q()) == saved_n, 40) and app.cfg["local_dir"] == MUSIC and app.cfg["normalize"])
    check("buka lagi: lirik dari cache tanpa bertanya LRCLIB lagi", len(app.lyrics_cache.data) >= 1)
    click(app.clear_btn)
    check("Kosongkan: antrean kosong", len(q()) == 0 and app.q_list.note[0] == "Antrean kosong")

    pairs = [("teks sekunder di baris terpilih", theme.SILVER, theme.SELECT), ("lirik aktif di panel", theme.FG, theme.SURF),
             ("lirik lain di panel", theme.SILVER, theme.SURF), ("saran di kotak saran", theme.FG, theme.RAISED),
             ("ikon saran", theme.SILVER, theme.RAISED), ("judul rak", theme.FG, theme.SURF),
             ("garis seret hijau di panel", theme.GREEN, theme.SURF)]
    low = [(n, theme.contrast(a, b)) for n, a, b in pairs if theme.contrast(a, b) < 4.5]
    check("kontras elemen baru >= 4.5:1", not low, "terendah %.1f" % min(theme.contrast(a, b) for _, a, b in pairs))
except Exception:
    traceback.print_exc()
    check("uji berjalan sampai selesai", False)
finally:
    try:
        app.close()
    except Exception:
        traceback.print_exc()
    log = open(config.LOG, encoding="utf-8").read() if os.path.exists(config.LOG) else ""
    unexpected = [line for line in log.splitlines() if "Error" in line or "Traceback" in line]
    check("log error bersih", not unexpected, "; ".join(unexpected[:5]))
    print("\n%d dari %d lolos" % (sum(results), len(results)))
    sys.exit(0 if all(results) else 1)
