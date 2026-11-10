"""Palet, ukuran, huruf, ikon, dan penggambar bentuk membulat.

Tampilan mengikuti arahan gaya "terinspirasi Spotify": gelap akromatik, satu aksen hijau untuk
kontrol putar dan status aktif, tombol berbentuk pil dan lingkaran. tkinter tidak punya sudut
membulat, jadi semua bentuk digambar sendiri sebagai PNG beralpha (lihat shape).
"""
import math
import struct
import zlib
import tkinter as tk
import tkinter.font as tkfont

from . import system

# Palet arahan: abu arang bertingkat + satu aksen hijau. Tidak ada warna merek lain.
BG, SURF, MID, HOVER, RAISED, SELECT = "#121212", "#181818", "#1f1f1f", "#252525", "#2a2a2a", "#333333"
BORDER, EDGE, FG, SILVER, INK = "#4d4d4d", "#7c7c7c", "#ffffff", "#b3b3b3", "#121212"
GREEN, GREEN_HI, GREEN_LO, RED = "#1ed760", "#3be477", "#1db954", "#f3727f"
LIGHT = "#eeeeee"
# Font milik Spotify tidak bisa dipakai; urutan cadangan dari arahan gaya, lalu font umum Linux.
FONT_STACK = ("Helvetica Neue", "Helvetica", "Arial", "Liberation Sans", "Nimbus Sans", "DejaVu Sans",
              "Noto Sans")

if system.WINDOWS:
    ICON_FAMILY = "Segoe MDL2 Assets"
    G_PLAY, G_PAUSE, G_PREV, G_NEXT = "", "", "", ""
    G_VOL, G_MUTE, G_SEARCH, G_NOTE = "", "", "", ""
    G_SHUFFLE, G_REPEAT, G_REPEAT_ONE = "", "", ""
    G_HEART, G_HEART_FILL, G_ADD, G_LIST = "", "", "", ""
    G_HOME, G_HISTORY, G_FOLDER, G_SETTINGS, G_LYRICS = "", "", "", "", ""
else:
    # Font ikon Windows tidak ada di macOS/Linux; simbol Unicode di bawah ada di font bawaan keduanya.
    # Semuanya di dalam BMP karena Tk 8.6 belum stabil menggambar karakter di luar BMP (emoji).
    ICON_FAMILY = None
    G_PLAY, G_PAUSE, G_PREV, G_NEXT = "▶", "⏸", "⏮", "⏭"
    G_VOL, G_MUTE, G_SEARCH, G_NOTE = "♪", "✕", "⌕", "♫"
    G_SHUFFLE, G_REPEAT, G_REPEAT_ONE = "⇄", "↻", "↻1"
    G_HEART, G_HEART_FILL, G_ADD, G_LIST = "♡", "♥", "+", "≡"
    G_HOME, G_HISTORY, G_FOLDER, G_SETTINGS, G_LYRICS = "⌂", "⏲", "▤", "⚙", "¶"


class UI:
    scale = 1.0
    family = "Arial"


def pick_family(root):
    installed = set(tkfont.families(root))
    for name in FONT_STACK:
        if name in installed:
            return name
    return tkfont.nametofont("TkDefaultFont").actual("family")


def px(n):
    return max(1, int(round(n * UI.scale)))


def font(size, bold=False):
    return (UI.family, -px(size), "bold" if bold else "normal")


def icon_font(size):
    return (ICON_FAMILY or UI.family, -px(size))


def measure(text, spec):
    # Diukur lewat Tk dengan spesifikasi font yang sama persis dengan yang dipakai menggambar;
    # tkfont.Font membulatkan ukuran piksel ke poin sehingga hasilnya meleset sampai 10%.
    return tk._default_root.tk.call("font", "measure", spec, text)


def fit(text, spec, width):
    """Potong teks dengan elipsis supaya muat di lebar tertentu."""
    if measure(text, spec) <= width:
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if measure(text[:mid].rstrip() + "…", spec) <= width:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo].rstrip() + "…" if lo else ""


def fit_lines(text, spec, width, lines=2):
    """Bungkus teks per kata ke paling banyak `lines` baris; baris terakhir dipotong dengan elipsis."""
    out, rest = [], text.strip()
    while rest and len(out) < lines - 1 and measure(rest, spec) > width:
        line = ""
        for word in rest.split(" "):
            trial = (line + " " + word).strip()
            if measure(trial, spec) > width:
                break
            line = trial
        if not line:  # satu kata yang terlalu panjang: biarkan baris terakhir memotongnya
            break
        out.append(line)
        rest = rest[len(line):].strip()
    if rest:
        out.append(fit(rest, spec, width))
    return out


def hexrgb(color):
    return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))


def luminance(color):
    parts = [c / 255 for c in hexrgb(color)]
    parts = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in parts]
    return 0.2126 * parts[0] + 0.7152 * parts[1] + 0.0722 * parts[2]


def mix(a, b, k):
    """Campur warna a ke b sebanyak k (0 = a, 1 = b)."""
    return "#%02x%02x%02x" % tuple(int(x + (y - x) * k + 0.5) for x, y in zip(hexrgb(a), hexrgb(b)))


def contrast(a, b):
    """Rasio kontras WCAG antara dua warna hex."""
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def png(w, h, rows, level=6):
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    raw = b"".join(b"\0" + row for row in rows)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, level)) + chunk(b"IEND", b""))


_shapes = {}


def shape(w, h, r, fill, ring=None, rw=0, inverse=False, keep=True):
    """Persegi membulat beralpha (pil bila r = h/2, lingkaran bila w = h = 2r).

    ring/rw menggambar garis tepi di sisi dalam. inverse membalik alpha: bagian luar
    sudut diisi warna, bagian dalam tembus, dipakai untuk membulatkan sudut gambar sampul.
    Hanya kolom sudut yang dihitung per piksel; bagian tengah tiap baris diulang.
    """
    w, h = int(w), int(h)
    key = (w, h, r, fill, ring, rw, inverse)
    if keep and key in _shapes:
        return _shapes[key]
    r = min(r, w / 2, h / 2)
    fr = hexrgb(fill)
    rr = hexrgb(ring) if ring else fr
    cap = min(w // 2, int(math.ceil(max(r, rw))))
    hw, hh = w / 2 - r, h / 2 - r

    def pixel(x, y):
        qx, qy = abs(x + 0.5 - w / 2) - hw, abs(y + 0.5 - h / 2) - hh
        d = math.hypot(max(qx, 0), max(qy, 0)) + min(max(qx, qy), 0) - r
        a = min(1.0, max(0.0, 0.5 - d))
        if inverse:
            return bytes((fr[0], fr[1], fr[2], int(255 * (1 - a) + 0.5)))
        k = min(1.0, max(0.0, 0.5 - (d + rw))) if ring else 1.0
        return bytes((int(rr[0] + (fr[0] - rr[0]) * k + 0.5), int(rr[1] + (fr[1] - rr[1]) * k + 0.5),
                      int(rr[2] + (fr[2] - rr[2]) * k + 0.5), int(255 * a + 0.5)))

    rows = []
    for y in range(h):
        left = [pixel(x, y) for x in range(cap)]
        middle = pixel(cap, y) * (w - 2 * cap) if w > 2 * cap else b""
        rows.append(b"".join(left) + middle + b"".join(reversed(left)))
    image = tk.PhotoImage(data=png(w, h, rows))
    if keep:
        _shapes[key] = image
    return image


def draw_tracked(canvas, x, y, text, spec, fill, tracking):
    """Teks dengan jarak antarhuruf (tkinter tidak punya letter-spacing)."""
    for ch in text:
        canvas.create_text(x, y, text=ch, anchor="w", font=spec, fill=fill)
        x += measure(ch, spec) + tracking


def tracked_width(text, spec, tracking):
    return sum(measure(ch, spec) for ch in text) + tracking * (len(text) - 1)
