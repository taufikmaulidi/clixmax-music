"""Pulau mini bergaya Dynamic Island: pil hitam di tengah atas layar saat jendela utama di-minimize
atau disembunyikan ke tray.

Polanya diambil dari proyek Dynamic Island di GitHub (Lost Island, Isla, Nimbus, rajsriv), idenya saja:
- Ringkas: gambar, judul, dan baris lirik yang sedang dinyanyikan (atau nama artis), plus putar/jeda.
- Melebar saat kursor di atasnya: gambar besar, judul, artis, lirik, bilah posisi yang bisa diklik,
  dan kontrol sebelumnya/putar/berikutnya.
- Mengintip: melebar sebentar saat lagu berganti, lalu kembali ringkas.
- Roda tetikus mengatur volume, klik kanan membuka menu, klik membuka ClixMax, seret untuk memindah.
Perubahan ukuran dianimasikan singkat (sekitar 0,2 detik) supaya jelas dari mana kartu muncul, dan
langsung tanpa animasi bila animasi Windows dimatikan. Jendela tanpa bingkai tidak bisa menerima fokus
keyboard, jadi padanan keyboardnya adalah tombol media dan panel media sistem.

Gaya notch meniru notch yang menyatu dengan tepi atas layar (contoh dari pengguna: Poni): kedua sudut
atasnya melengkung ke luar seperti bahu, sudut bawah membulat. Saat ringkas ada bilah ekualiser kecil
berwarna cover yang bergerak selama lagu berputar; saat melebar, gambar diberi pendar warna cover.
"""
import math
import random
import time
import tkinter as tk

from . import system
from .artwork import art_url
from .config import fmt_time
from .theme import (EDGE, FG, RAISED, SILVER, G_NEXT, G_NOTE, G_PAUSE, G_PLAY, G_PREV, contrast, fit, font,
                    icon_font, mix, px, shape)
from .widgets import IconButton

BLACK = "#000000"
PEEK_SECONDS = 3.5
TUCK_SECONDS = 2.5  # ringkas tanpa disentuh selama ini: menciut jadi garis supaya tab browser di bawahnya bebas
DWELL_MS = 400  # kursor harus diam di atas pulau selama ini sebelum melebar; yang sekadar lewat tidak memicunya


def round_rect(cv, x0, y0, x1, y1, r, **kw):
    """Persegi membulat dari poligon halus (cepat, cukup untuk digambar ulang di tiap langkah animasi)."""
    r = min(r, (x1 - x0) / 2, (y1 - y0) / 2)
    points = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1, x1 - r, y1, x0 + r, y1, x0, y1,
              x0, y1 - r, x0, y0 + r, x0, y0]
    return cv.create_polygon(points, smooth=True, splinesteps=16, **kw)


def arc(cx, cy, r, start, end, steps=8):
    """Titik-titik busur (derajat, sumbu y ke bawah) dari start ke end."""
    return [(cx + r * math.cos(math.radians(start + (end - start) * i / steps)),
             cy + r * math.sin(math.radians(start + (end - start) * i / steps))) for i in range(steps + 1)]


def notch_points(w, h, s, r):
    """Garis luar notch selebar w dengan bahu cekung selebar s di kiri dan kanan atas (x dari -s sampai w+s)."""
    r = min(r, w / 2, (h - s) / 2) if h > s else min(r, w / 2, h / 2)
    points = [(-s, 0), (w + s, 0)]
    points += arc(w + s, s, s, 270, 180)  # bahu kanan
    points += arc(w - r, h - r, r, 0, 90)  # sudut kanan bawah
    points += arc(r, h - r, r, 90, 180)  # sudut kiri bawah
    points += arc(-s, s, s, 360, 270)  # bahu kiri
    return [c for point in points for c in point]


def glow_color(vivid):
    """Warna cover yang cukup terang di atas hitam (3:1, batas untuk grafik) untuk ekualiser dan pendar."""
    for step in range(0, 21):
        color = mix(vivid, FG, step / 20)
        if contrast(color, BLACK) >= 3:
            return color
    return FG


class Island(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app.root, bg=BLACK)
        self.withdraw()
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.clear = system.make_transparent(self) or BLACK
        self.configure(bg=self.clear)
        self.app = app
        self.compact, self.wide, self.tucked = (px(340), px(48)), (px(440), px(164)), (px(120), px(8))
        self.size, self.expanded, self.animating = self.compact, False, False
        self.mode, self.away_since = "compact", time.time()
        self.center_x = self.top = None
        self.state_args, self.track = ("", "", None, False), None
        self.hover, self.held, self.bar = False, None, None
        self.peek_until = self.osd_until = 0.0
        self.osd_text, self.jobs, self.menu = "", {}, None
        self.hits, self.float_top, self.notch = [], None, False
        self.levels = [0.3, 0.6, 0.45, 0.8]  # tinggi bilah ekualiser, 0..1
        self.cv = tk.Canvas(self, width=self.size[0], height=self.size[1], bg=self.clear, highlightthickness=0,
                            bd=0, cursor="hand2")
        self.cv.pack()
        self.prev_btn = IconButton(self.cv, G_PREV, lambda: app.send("playlist-prev"), BLACK, size=34, glyph_px=14)
        self.play_btn = IconButton(self.cv, G_PLAY, app.toggle, BLACK, size=40, primary=True, glyph_px=15)
        self.next_btn = IconButton(self.cv, G_NEXT, lambda: app.send("playlist-next"), BLACK, size=34, glyph_px=14)
        self.buttons = {b: self.cv.create_window(0, 0, anchor="nw", window=b, state="hidden")
                        for b in (self.prev_btn, self.play_btn, self.next_btn)}
        self.bind("<Enter>", self.entered)
        self.bind("<Leave>", lambda e: self.schedule("leave", 300, self.check_leave))
        self.cv.bind("<ButtonPress-1>", self.press)
        self.cv.bind("<B1-Motion>", self.drag)
        self.cv.bind("<ButtonRelease-1>", self.release)
        for sequence in system.CONTEXT_CLICK:
            self.cv.bind(sequence, self.context)

    # ---------- jadwal ----------
    def schedule(self, name, ms, action):
        self.cancel(name)

        def run():
            self.jobs.pop(name, None)
            action()

        self.jobs[name] = self.after(ms, run)

    def cancel(self, name):
        job = self.jobs.pop(name, None)
        if job:
            self.after_cancel(job)

    # ---------- muncul dan hilang ----------
    def place_by_style(self):
        """Notch: menempel di tepi atas layar. Melayang: 8 px di bawahnya, atau di tempat terakhir ia diseret."""
        left, top, right, _ = system.work_area(self)
        if self.center_x is None:
            self.center_x = (left + right) // 2
        self.notch = self.app.cfg["island_style"] == "notch"
        self.top = top if self.notch else (self.float_top if self.float_top is not None else top + px(8))
        self.edge = top  # garis tipis selalu di tepi atas: kursor yang didorong ke atas pasti mengenainya
        try:
            self.attributes("-alpha", 1.0 - float(self.app.cfg["island_alpha"]))
        except tk.TclError:
            pass  # pengelola jendela tanpa dukungan transparansi

    def apply_style(self):
        self.place_by_style()
        if self.winfo_viewable() and not self.animating:
            self.apply_size(self.size)

    def appear(self):
        self.place_by_style()
        self.expanded, self.mode, self.away_since = False, "compact", time.time()
        self.apply_size(self.compact)
        self.deiconify()
        self.lift()
        self.schedule("tick", 250, self.tick)

    def vanish(self):
        for name in list(self.jobs):
            self.cancel(name)
        self.animating = self.hover = False
        self.withdraw()

    def tick(self):
        """Empat kali sedetik: perbarui lirik dan posisi, kecilkan lagi bila intip sudah selesai, dan ciutkan
        jadi garis bila sudah lama tidak disentuh."""
        now, inside = time.time(), self.pointer_inside()
        if inside or self.hover or now < self.peek_until:
            self.away_since = now
        if self.expanded and not self.hover and now >= self.peek_until and not inside:
            self.set_mode("compact")
        elif (self.mode == "compact" and self.app.cfg["island_tuck"] and not self.animating
              and now - self.away_since >= TUCK_SECONDS):
            self.set_mode("tuck")
        elif not self.animating:
            if self.state_args[3]:
                self.levels = [0.4 * old + 0.6 * random.uniform(0.2, 1.0) for old in self.levels]
            self.draw()
        self.schedule("tick", 250, self.tick)

    def show_state(self, title, sub, track, playing):
        changed = track is not self.track
        self.state_args, self.track = (title, sub, track, playing), track
        self.play_btn.show(G_PAUSE if playing else G_PLAY)
        if changed and track is not None and self.winfo_viewable():
            self.peek()
        elif not self.animating:
            self.draw()

    def peek(self):
        self.peek_until = time.time() + PEEK_SECONDS
        if self.expanded:
            self.draw()
        else:
            self.set_mode("wide")

    # ---------- ukuran dan animasi ----------
    def set_expanded(self, on):
        self.set_mode("wide" if on else "compact")

    def set_mode(self, mode):
        """tuck (garis tipis), compact (ringkas), atau wide (lebar dengan kontrol)."""
        if mode == self.mode:
            return
        self.mode, self.expanded = mode, mode == "wide"
        if mode != "tuck":
            self.away_since = time.time()
        target = {"tuck": self.tucked, "compact": self.compact, "wide": self.wide}[mode]
        if not system.animations_enabled():
            self.apply_size(target)
            return
        start, began = self.size, time.time()
        self.animating = True

        def step():
            k = min(1.0, (time.time() - began) / 0.18)
            ease = 1 - (1 - k) ** 3  # cepat di awal, melambat di akhir
            size = (round(start[0] + (target[0] - start[0]) * ease), round(start[1] + (target[1] - start[1]) * ease))
            if k < 1:
                self.apply_size(size, outline_only=True)
                self.schedule("animate", 15, step)
            else:
                self.animating = False
                self.apply_size(target)

        step()

    def shoulder(self):
        return px(10) if self.notch and self.size[1] > px(20) else 0  # garis tipis tidak punya bahu

    def apply_size(self, size, outline_only=False):
        self.size = size
        w, h = size
        s = self.shoulder()
        # Bahu notch berada di luar badan pulau: kanvas dilebarkan 2s dan digeser supaya x=0 tetap tepi kiri
        # badan; tombol, area klik, dan bilah posisi tidak perlu tahu soal bahu.
        self.cv.configure(width=w + 2 * s, height=h, scrollregion=(-s, 0, w + s, h))
        self.cv.xview_moveto(0)
        y = self.edge if h <= px(20) else self.top
        self.geometry("%dx%d+%d+%d" % (w + 2 * s, h, self.center_x - w // 2 - s, y))
        self.draw(outline_only)

    def vivid(self, size):
        """Warna cover untuk gambar seukuran size (warnanya tersedia setelah gambar itu selesai diunduh)."""
        track = self.state_args[2]
        url = art_url(track, size, size) if track and self.app.cfg["tint"] else None
        color = self.app.art_vivid.get(url) if url else None
        return glow_color(color) if color else None

    # ---------- gambar ----------
    def draw(self, outline_only=False):
        cv, (w, h) = self.cv, self.size
        cv.delete("ink")
        for item in self.buttons.values():
            cv.itemconfigure(item, state="hidden")
        self.bar, self.hits = None, []
        if h <= px(20):  # garis tipis: berwarna cover supaya mudah ditemukan lagi di atas bilah tab mana pun
            round_rect(cv, 0, -h, w, h, h / 2, fill=self.vivid(px(32)) or SILVER, outline="", tags="ink")
            return
        if self.notch:
            cv.create_polygon(notch_points(w, h, self.shoulder(), px(20)), fill=BLACK, outline=BLACK, tags="ink")
        else:
            round_rect(cv, 0, 0, w, h, min(h / 2, px(28)), fill=BLACK, outline=BLACK, tags="ink")
        cv.tag_lower("ink")
        self.bar, self.hits = None, []
        if outline_only:
            return
        if self.size == self.wide:
            self.draw_wide()
        else:
            self.draw_compact()

    def caption(self):
        """Baris kedua: OSD volume sesaat, lalu baris lirik yang sedang dinyanyikan, lalu nama artis."""
        title, sub, track, playing = self.state_args
        if time.time() < self.osd_until:
            return self.osd_text, FG
        line = self.app.lyric_now(track) if track else None
        return (line, FG) if line else (sub, SILVER)

    def art_box(self, x, y, size, radius):
        track = self.state_args[2]
        image = self.app.art(track, size) if track else None
        self.cv.create_image(x, y, anchor="nw", image=shape(size, size, radius, RAISED), tags="ink")
        if image is not None:
            self.cv.create_image(x, y, anchor="nw", image=image, tags="ink")
            self.cv.create_image(x, y, anchor="nw", image=shape(size, size, radius, BLACK, inverse=True), tags="ink")
        else:
            self.cv.create_text(x + size // 2, y + size // 2, text=G_NOTE, font=icon_font(size // 2), fill=SILVER,
                                tags="ink")

    def place_button(self, button, x, y):
        item = self.buttons[button]
        self.cv.coords(item, x, y)
        self.cv.itemconfigure(item, state="normal")

    def draw_compact(self):
        cv, (w, h) = self.cv, self.size
        title = self.state_args[0]
        size = px(32)
        self.art_box(px(8), (h - size) // 2, size, size / 2)
        x, room = px(50), w - px(50) - px(88)
        self.draw_levels(w - px(80), h / 2)
        text, color = self.caption()
        cv.create_text(x, px(16), anchor="w", font=font(13, True), fill=FG, text=fit(title, font(13, True), room),
                       tags="ink")
        cv.create_text(x, px(33), anchor="w", font=font(12), fill=color, text=fit(text or "", font(12), room),
                       tags="ink")
        is_artist = text and text == self.state_args[1] and color == SILVER
        self.hits = [("open", 0, 0, x + room, px(25)), ("artist" if is_artist else "open", x, px(25), x + room, h)]
        self.place_button(self.play_btn, w - px(52), (h - self.play_btn.winfo_reqheight()) // 2)

    def draw_levels(self, x, cy):
        """Ekualiser empat bilah: bergerak saat lagu berputar, rata saat jeda. Tanda putar yang terlihat dari
        jauh, berwarna cover supaya pulau ikut berganti suasana tiap lagu."""
        color = self.vivid(px(32)) or FG
        playing = bool(self.state_args[2]) and self.state_args[3]
        bar, gap, tall = px(3), px(3), px(18)
        for i, level in enumerate(self.levels):
            half = max(bar, tall * (level if playing else 0.15)) / 2
            left = x + i * (bar + gap)
            self.cv.create_line(left + bar / 2, cy - half + bar / 2, left + bar / 2, cy + half - bar / 2, width=bar,
                                fill=color, capstyle="round", tags="ink")

    def draw_wide(self):
        cv, (w, h) = self.cv, self.size
        title, sub = self.state_args[:2]
        pad, size = px(16), px(88)
        glow = self.vivid(size)
        if glow:  # pendar warna cover di belakang gambar, makin pudar ke luar
            for spread, fade in ((px(10), 0.86), (px(7), 0.74), (px(4), 0.6)):
                round_rect(cv, pad - spread, pad - spread, pad + size + spread, pad + size + spread,
                           px(10) + spread, fill=mix(glow, BLACK, fade), outline="", tags="ink")
        self.art_box(pad, pad, size, px(10))
        x = pad + size + px(14)
        room = w - x - pad
        cv.create_text(x, pad + px(10), anchor="w", font=font(15, True), fill=FG,
                       text=fit(title, font(15, True), room), tags="ink")
        cv.create_text(x, pad + px(31), anchor="w", font=font(13), fill=SILVER, text=fit(sub or "", font(13), room),
                       tags="ink")
        text, color = self.caption()
        if text and text != sub:
            cv.create_text(x, pad + px(51), anchor="w", font=font(13), fill=color, text=fit(text, font(13), room),
                           tags="ink")
        self.hits = [("open", pad, pad, pad + size, pad + size), ("open", x, pad, w - pad, pad + px(21)),
                     ("artist", x, pad + px(21), w - pad, pad + px(41)), ("open", x, pad + px(41), w - pad, pad + px(61))]
        state = self.app.state or {}
        now, total = self.app.position_now(), state.get("dur") or 0
        y = pad + px(72)
        cv.create_line(x, y, w - pad, y, fill=EDGE, width=px(4), capstyle="round", tags="ink")
        if total and now is not None:
            cv.create_line(x, y, x + (w - pad - x) * min(1.0, now / total), y, fill=FG, width=px(4),
                           capstyle="round", tags="ink")
            self.bar = (x, w - pad, y, total)
        cv.create_text(x, y + px(13), anchor="w", font=font(11), fill=SILVER, text=fmt_time(now) if now else "-:--",
                       tags="ink")
        cv.create_text(w - pad, y + px(13), anchor="e", font=font(11), fill=SILVER,
                       text=fmt_time(total) if total else "-:--", tags="ink")
        widths = [b.winfo_reqwidth() for b in (self.prev_btn, self.play_btn, self.next_btn)]
        bx, by = (w - sum(widths) - px(16)) // 2, h - px(48)
        for button, width in zip((self.prev_btn, self.play_btn, self.next_btn), widths):
            self.place_button(button, bx, by + (self.play_btn.winfo_reqheight() - button.winfo_reqheight()) // 2)
            bx += width + px(8)

    # ---------- interaksi ----------
    def pointer_inside(self):
        x, y = self.winfo_pointerxy()
        rx, ry = self.winfo_rootx(), self.winfo_rooty()
        return rx <= x < rx + self.winfo_width() and ry <= y < ry + self.winfo_height()

    def entered(self, event):
        self.hover = True
        self.cancel("leave")
        if self.mode == "tuck":  # garis disentuh: ringkas dulu, lalu lebar bila kursor tetap di sana
            self.schedule("expand", 120, lambda: (self.set_mode("compact"),
                                                  self.schedule("expand", DWELL_MS, self.expand_if_held)))
        elif not self.expanded:
            self.schedule("expand", DWELL_MS, self.expand_if_held)

    def expand_if_held(self):
        if self.hover and self.pointer_inside():
            self.set_mode("wide")

    def check_leave(self):
        if self.pointer_inside():
            return
        self.hover = False
        self.cancel("expand")
        if time.time() >= self.peek_until and self.mode == "wide":
            self.set_mode("compact")

    def scroll_by(self, direction):
        """Roda tetikus di atas pulau: volume naik/turun 5, ditampilkan sesaat di baris kedua."""
        self.app.nudge_volume(-5 * direction)
        self.osd_text = "Volume %d%%" % int(self.app.vol.value)
        self.osd_until = time.time() + 1.2
        if not self.animating:
            self.draw()

    def press(self, event):
        # Titik tekan disimpan dalam koordinat kanvas (bergeser selebar bahu notch dari koordinat jendela).
        self.held = [event.x_root, event.y_root, self.winfo_x(), self.winfo_y(), False, self.cv.canvasx(event.x),
                     event.y]

    def drag(self, event):
        if self.held:
            dx, dy = event.x_root - self.held[0], event.y_root - self.held[1]
            if self.held[4] or abs(dx) + abs(dy) > px(4):
                self.held[4] = True
                # Notch dan garis tipis tetap menempel di tepi atas, hanya bergeser mendatar.
                y = self.held[3] if (self.notch or self.mode == "tuck") else self.held[3] + dy
                self.geometry("+%d+%d" % (self.held[2] + dx, y))

    def release(self, event):
        held, self.held = self.held, None
        if held and held[4]:  # dipindah: pulau mekar dan menyusut dari titik barunya
            self.center_x = self.winfo_x() + self.shoulder() + self.size[0] // 2
            if not self.notch and self.mode != "tuck":
                self.float_top = self.top = self.winfo_y()
            return
        if self.mode == "tuck":  # klik garis tipis membuka pulau, bukan langsung jendela
            self.set_mode("compact")
            return
        if self.bar and held:
            x0, x1, y, total = self.bar
            if x0 - px(4) <= held[5] <= x1 + px(4) and abs(held[6] - y) <= px(10):
                self.app.seek_to(total * min(1.0, max(0.0, (held[5] - x0) / (x1 - x0))))
                return
        if held:
            for action, x0, y0, x1, y1 in self.hits:
                if x0 <= held[5] <= x1 and y0 <= held[6] <= y1:
                    if action == "artist":
                        self.app.open_artist(self.state_args[2])
                    else:
                        self.app.open_player()
                    return
        self.app.restore_window()

    def build_menu(self):
        if self.menu is not None:
            self.menu.destroy()
        self.menu = tk.Menu(self, tearoff=0, bg=RAISED, fg=FG, activebackground="#333333", activeforeground=FG,
                            bd=0, font=font(14))
        self.menu.add_command(label="Buka ClixMax", command=self.app.restore_window)
        self.menu.add_command(label="Keluar dari ClixMax", command=self.app.close)
        return self.menu

    def context(self, event):
        menu = self.build_menu()
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"
