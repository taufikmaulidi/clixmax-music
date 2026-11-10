"""Gambar lagu: cover album (server gambar Google), thumbnail video (i.ytimg.com), dan cover musik lokal.

Pillow dipakai karena tkinter tidak bisa membaca JPEG, format semua thumbnail video YouTube.
"""
import colorsys
import io
import urllib.request

from PIL import Image, ImageDraw, ImageOps

from . import localfiles
from .theme import FG, GREEN, INK, SILVER, SURF, contrast

HEADERS = {"User-Agent": "Mozilla/5.0"}
LOCAL = "local:"


def is_video(track):
    kind = track.get("kind")
    if kind:
        return kind == "video"
    return not track.get("art")  # data lama belum punya kolom kind


def art_url(track, w, h, wide=False):
    """Alamat gambar untuk lagu ini, atau None bila tidak ada sumbernya.

    wide=True meminta thumbnail video 16:9; selain itu cover album bila ada, lalu thumbnail video.
    Lagu lokal memakai alamat "local:<path>" yang dibaca dari tag berkasnya.
    """
    if track.get("kind") == "local":
        return LOCAL + track["url"]
    vid = track.get("id") or ""
    thumb = "https://i.ytimg.com/vi/%s/mqdefault.jpg" % vid if len(vid) == 11 else None
    if wide and thumb:
        return thumb
    if track.get("art"):
        side = max(w, h)
        return "%s=w%d-h%d-p-l90-rj" % (track["art"], side, side)
    return thumb


def dominant(image):
    """(hue, saturasi, kecerahan) warna cover yang dominan dan paling berwarna, atau None."""
    small = image.resize((24, 24)).quantize(colors=5)
    palette, best, score = small.getpalette(), None, -1.0
    for count, index in small.getcolors() or []:
        r, g, b = palette[index * 3:index * 3 + 3]
        hue, sat, val = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        weight = count * (0.3 + sat) * (0.3 + val)
        if weight > score:
            best, score = (hue, sat, val), weight
    return best


def _darken_until(hue, sat, val, ok):
    while val > 0.04:
        color = "#%02x%02x%02x" % tuple(int(c * 255) for c in colorsys.hsv_to_rgb(hue, sat, val))
        if ok(color):
            return color
        val -= 0.03
    return None


def tint_of(image):
    """Warna gelap dari cover untuk latar kartu: teks putih (7:1) dan abu (4.5:1) tetap terbaca."""
    best = dominant(image)
    if best is None:
        return SURF
    return _darken_until(best[0], min(best[1], 0.75), min(best[2], 0.55),
                         lambda c: contrast(FG, c) >= 7 and contrast(SILVER, c) >= 4.5) or SURF


def vivid_of(image):
    """Warna cerah dari cover untuk latar halaman lirik (gaya Spotify): tetap berwarna, tetapi cukup gelap
    supaya teks putih terbaca (4.5:1). Cover yang hampir abu memberi abu gelap."""
    best = dominant(image)
    if best is None:
        return "#3a3a3a"
    sat = max(best[1], 0.45) if best[1] > 0.12 else best[1]
    return _darken_until(best[0], min(sat, 0.8), 0.62, lambda c: contrast(FG, c) >= 4.5) or "#3a3a3a"


def fetch(url, w, h):
    """Unduh (atau baca dari berkas lokal) lalu potong-tengah ke w x h.

    Mengembalikan (PNG untuk tk.PhotoImage, warna latar dari cover). Aman dari thread mana pun.
    """
    if url.startswith(LOCAL):
        raw = localfiles.cover_bytes(url[len(LOCAL):])
        if not raw:
            raise LookupError("berkas tidak punya cover")
    else:
        raw = urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=10).read()
    image = Image.open(io.BytesIO(raw)).convert("RGB")
    tint, vivid = tint_of(image), vivid_of(image)
    out = io.BytesIO()
    ImageOps.fit(image, (w, h), Image.LANCZOS).save(out, "PNG", compress_level=1)
    return out.getvalue(), tint, vivid


def make_icon(ico_path, png_path):
    """Ikon aplikasi: lingkaran aksen dengan segitiga putar. .ico untuk Windows, .png untuk macOS/Linux."""
    big = 1024  # digambar besar lalu diperkecil supaya tepinya halus
    image = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw, unit = ImageDraw.Draw(image), big / 64
    draw.ellipse([2 * unit, 2 * unit, 62 * unit, 62 * unit], fill=GREEN)
    draw.polygon([(25 * unit, 18 * unit), (25 * unit, 46 * unit), (48 * unit, 32 * unit)], fill=INK)
    image = image.resize((256, 256), Image.LANCZOS)
    image.save(ico_path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (256, 256)])
    image.save(png_path)
