"""Tangkapan layar untuk README, dibuat dari lagu, cover, dan lirik contoh buatan sendiri.

Semua isinya karangan skrip ini (nada sederhana, cover gradasi, lirik pendek), jadi tangkapan layarnya
bebas dari cover album atau lirik berhak cipta milik orang lain. Memakai pipe mpv, setelan, dan data
terpisah supaya tidak mengganggu ClixMax yang sedang dipakai, dan --ao=null supaya tidak ada suara.

Jalankan dari folder proyek (Windows, butuh mpv): python tests/screenshots.py
Hasilnya ditulis ke docs/screenshots/.
"""
import io
import math
import os
import shutil
import struct
import subprocess
import sys
import time
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from clixmax import app as appmod, browsing, config, lyrics, player, system, theme  # noqa: E402
import winshot  # noqa: E402

WORK = os.path.join(HERE, "_out", "demo")
SHOTS = os.path.join(ROOT, "docs", "screenshots")
shutil.rmtree(WORK, ignore_errors=True)
os.makedirs(WORK)
os.makedirs(SHOTS, exist_ok=True)
config.PIPE = system.ipc_path("clixmax-demo")
for name in ("CFG", "LOG", "LIB", "SESSION", "LYRICS", "LOCAL"):
    setattr(config, name, os.path.join(WORK, os.path.basename(getattr(config, name))))
config.OLD_CFG = None
config.DEFAULTS["island_tuck"] = False  # pulau dipotret dalam keadaan ringkas dan lebar
player.Mpv.extra = ["--ao=null"]
system.watch_media_keys = lambda callback: False

SONGS = (  # judul, artis, dua warna cover, nada (Hz)
    ("Senja di Pelabuhan", "Arunika", (214, 72, 112), (120, 30, 90), 392),
    ("Lampu Kota", "Arunika", (52, 120, 226), (20, 40, 120), 440),
    ("Kopi Pagi", "Sorai", (232, 150, 52), (150, 60, 20), 494),
    ("Langit Ungu", "Nala", (136, 84, 222), (50, 20, 110), 523),
    ("Jalan Pulang", "Sorai", (38, 170, 120), (10, 70, 60), 587),
)
LYRICS = (
    "Matahari turun pelan di pelabuhan",
    "Kapal-kapal pulang membawa cerita",
    "Aku menunggu di ujung dermaga",
    "Lampu pertama menyala di kejauhan",
    "Angin laut menyebut namamu",
    "Dan senja tahu jalan pulang",
    "Ombak kecil menghapus jejak kita",
    "Tapi tidak dengan yang kuingat",
    "Tunggu aku di sini besok sore",
    "Saat langit berwarna jingga lagi",
)
LINE_SECONDS = 4.0
MPV = player.find_exe("mpv")


def make_audio(path, freq, seconds=50):
    wav = path + ".wav"
    with wave.open(wav, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(b"".join(struct.pack("<h", int(4000 * math.sin(2 * math.pi * freq * i / 22050)))
                               for i in range(22050 * seconds)))
    subprocess.run([MPV, wav, "--no-config", "--o=" + path, "--oac=aac", "--really-quiet"], check=True,
                   creationflags=system.HIDDEN, timeout=120)
    os.remove(wav)


def cover(top, bottom):
    """Cover gradasi dengan lingkaran terang, sebagai JPEG."""
    from PIL import Image, ImageDraw
    image = Image.new("RGB", (400, 400))
    draw = ImageDraw.Draw(image)
    for y in range(400):
        k = y / 399
        draw.line([(0, y), (400, y)], fill=tuple(int(a + (b - a) * k) for a, b in zip(top, bottom)))
    draw.ellipse([120, 90, 280, 250], fill=tuple(min(255, c + 70) for c in top))
    out = io.BytesIO()
    image.save(out, "JPEG", quality=92)
    return out.getvalue()


def timed_lyrics():
    """Lirik contoh dengan waktu per baris dan per kata (kata dibagi rata di 85% durasi barisnya)."""
    lines, words = [], []
    for i, text in enumerate(LYRICS):
        start = 2.0 + i * LINE_SECONDS
        parts = text.split(" ")
        step = LINE_SECONDS * 0.85 / len(parts)
        lines.append((start, text))
        words.append([(start + j * step, start + (j + 1) * step, part + (" " if j < len(parts) - 1 else ""))
                      for j, part in enumerate(parts)])
    return lines, words


def main():
    from mutagen.mp4 import MP4, MP4Cover
    music = os.path.join(WORK, "musik")
    os.makedirs(music)
    for i, (title, artist, top, bottom, freq) in enumerate(SONGS):
        path = os.path.join(music, "%02d.m4a" % (i + 1))
        make_audio(path, freq)
        tags = MP4(path)
        tags["\xa9nam"], tags["\xa9ART"], tags["\xa9alb"] = [title], [artist], ["Contoh"]
        tags["trkn"] = [(i + 1, len(SONGS))]
        tags["covr"] = [MP4Cover(cover(top, bottom), imageformat=MP4Cover.FORMAT_JPEG)]
        tags.save()
    browsing.filedialog.askdirectory = lambda **k: music
    lines, words = timed_lyrics()
    demo = {"found": True, "source": "Better Lyrics", "lines": lines, "words": words, "v": lyrics.VERSION}
    # Lirik contoh untuk lagu pertama, tanpa bertanya ke layanan lirik mana pun.
    lyrics.lookup = lambda track, seconds, words=True: (demo if track.get("title") == SONGS[0][0]
                                                         else {"found": False, "v": lyrics.VERSION})

    root, app = appmod.create("")

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
        raise SystemExit("gagal menunggu: %s" % cond.__code__.co_names)

    def shot(name, window=None):
        w, h = winshot.capture(window or root, os.path.join(SHOTS, name))
        print("tangkapan layar: docs/screenshots/%s (%dx%d)" % (name, w, h), flush=True)

    try:
        left, top, right, bottom = system.work_area(root)
        root.geometry("%dx%d+%d+%d" % (min(theme.px(1280), right - left - 16), min(theme.px(760), bottom - top - 48),
                                       left + 8, top + 8))
        root.lift()
        wait(lambda: app.state is not None, 25)
        app.choose_folder()
        wait(lambda: len([r for r in app.res_list.rows if "url" in r]) == len(SONGS), 30)
        app.play_all()
        wait(lambda: app.now_track() is not None and (app.state or {}).get("t"), 30)
        index = next(i for i, t in enumerate(app.queue) if t.get("title") == SONGS[0][0])
        app.send("playlist-play-index", index)
        wait(lambda: (app.now_track() or {}).get("title") == SONGS[0][0] and (app.state or {}).get("t"), 30)
        wait(lambda: len(app.art_cache) >= len(SONGS), 20)
        moment = lines[4][0] + LINE_SECONDS * 0.85 * 0.55  # di tengah baris kelima: sebagian kata sudah putih
        app.seek_to(moment)
        pump(0.8)
        app.toggle()
        wait(lambda: (app.state or {}).get("pause") is True, 10)
        app.seek_to(moment)
        pump(1.2)
        app.res_list.cv.focus_set()
        shot("01-musik-lokal.png")

        app.toggle_lyrics()
        pump(1.0)
        shot("02-panel-lirik.png")
        app.toggle_lyrics()

        app.open_player()
        wait(lambda: app.player_view.color not in (theme.SURF, theme.RAISED), 15)
        pump(1.2)
        shot("03-sedang-diputar.png")

        app.show_view("settings")
        pump(0.6)
        shot("04-pengaturan.png")

        app.show_view("local")
        app.toggle()
        wait(lambda: (app.state or {}).get("pause") is False, 10)
        app.set_island_style("notch")
        root.iconify()
        wait(lambda: app.island is not None and app.island.winfo_viewable(), 10)
        island = app.island
        wait(lambda: island.mode == "compact" and not island.animating, 10)
        pump(1.0)
        shot("05-pulau-ringkas.png", island)
        island.peek()
        pump(1.0)
        shot("06-pulau-lebar.png", island)
        app.set_island_style("float")
        app.restore_window()
        pump(0.5)
    finally:
        app.close()


if __name__ == "__main__":
    main()
