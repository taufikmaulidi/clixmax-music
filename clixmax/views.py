"""Tampilan besar yang bukan daftar lagu: Pengaturan, panel Lirik, dan daftar pintasan keyboard."""
import bisect
import time
import tkinter as tk

from . import system
from .artwork import art_url, is_video
from .theme import (FG, SILVER, SURF, RAISED, G_HEART, G_HEART_FILL, G_NOTE, contrast, fit, font, icon_font,
                    measure, mix, px, shape)
from .widgets import Chip, Control, IconButton, PillButton, ScrollFrame, Slider, TextLink, Toggle


class SettingsView(ScrollFrame):
    """Pengaturan: suara (perataan volume, kecepatan, nada), tampilan, jendela, musik lokal, pintasan."""

    def __init__(self, parent, app):
        super().__init__(parent, SURF)
        self.app = app
        cfg = app.cfg
        self.heading("Suara")
        self.normalize = Toggle(self.inner, "Ratakan volume antar lagu", cfg["normalize"], app.set_normalize, SURF)
        self.normalize.pack(anchor="w", padx=px(13), pady=(0, px(2)))
        self.note("Lagu yang pelan dan yang keras terdengar setara.")
        self.speed_value, self.speed = self.slider_row("Kecepatan", 0.5, 2.0, 0.05, app.set_speed)
        self.pitch_value, self.pitch = self.slider_row("Nada", -6, 6, 1, app.set_pitch)
        PillButton(self.inner, "Kembalikan normal", app.reset_audio, SURF).pack(anchor="w", padx=px(13),
                                                                              pady=(px(10), 0))
        self.heading("Tampilan")
        self.tint = Toggle(self.inner, "Warna kartu mengikuti cover", cfg["tint"], app.set_tint, SURF)
        self.tint.pack(anchor="w", padx=px(13))
        self.note("Kartu Sedang diputar di kanan atas diberi warna gelap dari cover lagu.")
        self.heading("Lirik")
        self.words = Toggle(self.inner, "Lirik per kata", cfg["word_lyrics"], app.set_word_lyrics, SURF)
        self.words.pack(anchor="w", padx=px(13))
        self.note("Kata disorot satu per satu saat dinyanyikan, dari Better Lyrics. Judul dan artis tiap lagu "
                  "dikirim ke layanan itu; bila dimatikan, sumber lain tetap memberi lirik per baris.")
        self.heading("Jendela")
        if app.tray:
            self.tray = Toggle(self.inner, "Tutup ke tray", cfg["tray_close"], app.set_tray_close, SURF)
            self.tray.pack(anchor="w", padx=px(13))
            self.note("Tombol tutup menyembunyikan jendela dan musik tetap jalan. Keluar lewat ikon di tray.")
        else:
            self.tray = None
            self.note("Ikon tray tidak tersedia di sistem ini, jadi menutup jendela menghentikan musik.")
        self.island = Toggle(self.inner, "Pulau mini di atas layar", cfg["island"], app.set_island, SURF)
        self.island.pack(anchor="w", padx=px(13), pady=(px(8), 0))
        self.note("Muncul saat jendela di-minimize atau disembunyikan. Arahkan kursor untuk kontrol lengkap, "
                  "putar roda tetikus untuk volume.")
        row = tk.Frame(self.inner, bg=SURF)
        row.pack(anchor="w", padx=px(16), pady=(px(8), 0))
        tk.Label(row, text="Gaya pulau", bg=SURF, fg=FG, font=font(14)).pack(side="left", padx=(0, px(10)))
        self.styles = {}
        for key, label in (("float", "Melayang"), ("notch", "Notch")):
            chip = Chip(row, label, lambda key=key: app.set_island_style(key), SURF)
            chip.pack(side="left", padx=(0, px(2)))
            self.styles[key] = chip
        self.note("Notch menempel ke tepi atas layar seperti poni ponsel; Melayang sedikit di bawahnya.")
        self.tuck = Toggle(self.inner, "Ciutkan jadi garis saat tidak dipakai", cfg["island_tuck"],
                           app.set_island_tuck, SURF)
        self.tuck.pack(anchor="w", padx=px(13), pady=(px(8), 0))
        self.note("Supaya tab browser di bawahnya tetap bisa diklik. Dorong kursor ke garis di tepi atas layar "
                  "untuk membukanya lagi; pulau tetap muncul sebentar tiap lagu berganti.")
        self.alpha_value, self.alpha = self.slider_row("Transparansi", 0, 60, 5,
                                                       lambda v: app.set_island_alpha(round(v / 5) * 5 / 100))
        self.heading("Musik lokal")
        self.folder = tk.Label(self.inner, bg=SURF, fg=SILVER, font=font(14), anchor="w", justify="left")
        self.folder.pack(anchor="w", padx=px(16), pady=(0, px(8)))
        PillButton(self.inner, "Pilih folder", app.choose_folder, SURF).pack(anchor="w", padx=px(13))
        self.heading("Pintasan keyboard")
        PillButton(self.inner, "Lihat pintasan", app.show_shortcuts, SURF).pack(anchor="w", padx=px(13),
                                                                             pady=(0, px(18)))
        for widget in self.all_controls(self.inner):
            self.watch(widget)

    def all_controls(self, widget):
        for child in widget.winfo_children():
            if isinstance(child, Control):
                yield child
            yield from self.all_controls(child)

    def heading(self, text):
        tk.Label(self.inner, text=text, bg=SURF, fg=FG, font=font(18, True)).pack(anchor="w", padx=px(16),
                                                                                 pady=(px(18), px(8)))

    def note(self, text):
        tk.Label(self.inner, text=text, bg=SURF, fg=SILVER, font=font(13), justify="left",
                 wraplength=px(330)).pack(anchor="w", padx=px(16), pady=(0, px(4)))

    def slider_row(self, title, lo, hi, step, command):
        # Muat di panel tengah tersempit (sekitar 370 px): label 80, garis geser 180, nilai 90.
        row = tk.Frame(self.inner, bg=SURF)
        row.pack(anchor="w", padx=px(16), pady=(px(10), 0))
        row.columnconfigure(0, minsize=px(80))
        tk.Label(row, text=title, bg=SURF, fg=FG, font=font(14), anchor="w").grid(row=0, column=0, sticky="w")
        slider = Slider(row, SURF, length=px(180), lo=lo, hi=hi, step=step)
        slider.grid(row=0, column=1)
        value = tk.Label(row, bg=SURF, fg=SILVER, font=font(14), anchor="w")
        value.grid(row=0, column=2, sticky="w", padx=(px(10), 0))

        def moved(v):
            command(v)
            self.sync()

        slider.on_move = slider.on_release = moved
        return value, slider

    def sync(self):
        cfg = self.app.cfg
        self.normalize.set(cfg["normalize"])
        self.tint.set(cfg["tint"])
        self.island.set(cfg["island"])
        self.tuck.set(cfg["island_tuck"])
        self.words.set(cfg["word_lyrics"])
        for key, chip in self.styles.items():
            if chip.on != (cfg["island_style"] == key):
                chip.on = cfg["island_style"] == key
                chip.paint()
        if not self.alpha.dragging:
            self.alpha.set(cfg["island_alpha"] * 100)
        self.alpha_value.configure(text="%d%%" % round(cfg["island_alpha"] * 100))
        if self.tray:
            self.tray.set(cfg["tray_close"])
        if not self.speed.dragging:
            self.speed.set(cfg["speed"])
        if not self.pitch.dragging:
            self.pitch.set(cfg["pitch"])
        self.speed_value.configure(text="%.2fx" % cfg["speed"])
        pitch = cfg["pitch"]
        self.pitch_value.configure(text="normal" if not pitch else "%+d semiton" % pitch)
        folder = cfg["local_dir"]
        self.folder.configure(text=fit(folder, font(14), px(330)) if folder else "Belum ada folder yang dipilih.")


class LyricsView(tk.Frame):
    """Lirik di panel kanan.

    Tersinkron: baris yang sedang dinyanyikan putih, lainnya abu, panel menggulir sendiri ke baris itu;
    klik baris (atau pilih dengan panah lalu Enter) untuk melompat ke sana. Teks biasa: tampil apa adanya.
    """

    def __init__(self, parent, bg, on_seek, big=False):
        super().__init__(parent, bg=bg)
        self.bg, self.on_seek, self.big = bg, on_seek, big
        self.past = self.upcoming = self.hint = SILVER  # panel kanan: hanya baris aktif yang putih
        self.cv = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0, takefocus=1, yscrollincrement=px(20),
                            height=px(120))
        self.cv.pack(fill="both", expand=True)
        self.mode, self.note, self.lines, self.times = "note", ("", "", FG), [], []
        self.words, self.word_items, self.sung = None, [], -1
        self.items, self.tops, self.heights = [], [], []  # items: tag kanvas per baris ("L0", "L1", ...)
        self.current = self.cursor = -1
        self.kb, self.hold_until, self.width, self.job = False, 0.0, 0, None
        cv = self.cv
        cv.bind("<Configure>", self.resized)
        cv.bind("<Button-1>", self.click)
        cv.bind("<Motion>", self.motion)
        cv.bind("<Up>", lambda e: self.step(-1))
        cv.bind("<Down>", lambda e: self.step(1))
        cv.bind("<Return>", lambda e: self.seek_cursor())
        for arrow in ("Up", "Down"):  # Ctrl+atas/bawah adalah pintasan volume: biarkan lewat ke jendela
            cv.bind("<%s-%s>" % (system.SHORTCUT, arrow), lambda e: None)
        cv.bind("<FocusIn>", lambda e: self.paint_ring())
        cv.bind("<FocusOut>", lambda e: self.cv.delete("ring"))

    def set_palette(self, bg, past, upcoming, hint):
        """Warna latar dan baris lirik (halaman pemutar: latar dari cover, baris berikutnya gelap)."""
        if (bg, past, upcoming, hint) != (self.bg, self.past, self.upcoming, self.hint):
            self.bg, self.past, self.upcoming, self.hint = bg, past, upcoming, hint
            self.configure(bg=bg)
            self.cv.configure(bg=bg)
            self.render()

    def color_for(self, i):
        return FG if i == self.current else (self.past if i < self.current else self.upcoming)

    # ----- isi
    def say(self, title, hint="", color=FG):
        self.mode, self.note = "note", (title, hint, color)
        self.lines, self.times, self.current, self.cursor = [], [], -1, -1
        self.render()

    def wait(self):
        self.mode, self.lines, self.times, self.current, self.cursor = "wait", [], [], -1, -1
        self.render()

    def show_synced(self, lines, words=None):
        """words: per baris daftar (mulai, selesai, teks) atau None; ada bila sumbernya memberi waktu per kata."""
        self.mode, self.lines = "synced", list(lines)
        self.words = list(words) if words and len(words) == len(self.lines) else None
        self.times = [t for t, _ in self.lines]
        self.current = self.cursor = -1
        self.render()
        self.cv.yview_moveto(0)

    def show_plain(self, text):
        self.mode, self.lines, self.times = "plain", [(None, line) for line in text.splitlines()], []
        self.current = self.cursor = -1
        self.render()
        self.cv.yview_moveto(0)

    # ----- gambar
    def resized(self, event):
        if event.width != self.width:
            if self.job is None:
                self.job = self.after(60, self.render)
        elif self.current >= 0 and not self.kb:
            self.after_idle(lambda: self.current >= 0 and self.center(self.current))  # tinggi berubah: tetap di tengah

    def render(self):
        self.job = None
        cv = self.cv
        cv.delete("all")
        self.items, self.tops, self.heights = [], [], []
        w = self.width = max(cv.winfo_width(), px(200))
        if self.mode == "wait":
            skeleton = RAISED if self.bg == SURF else mix(self.bg, FG, 0.15)
            for i, size in enumerate((220, 170, 240, 140)):
                cv.create_image(px(16), px(16) + i * px(34), anchor="nw",
                                image=shape(px(size), px(16), px(8), skeleton))
            cv.configure(scrollregion=(0, 0, w, 1))
            return
        if self.mode == "note":
            title, hint, color = self.note
            if contrast(color, self.bg) < 3:  # merah peringatan tidak terbaca di atas sebagian warna cover
                color = FG
            cv.create_text(w / 2, px(48), text=title, font=font(18, True), fill=color, width=w - px(40),
                           justify="center")
            if hint:
                cv.create_text(w / 2, px(68), anchor="n", text=hint, font=font(14), fill=self.hint, width=w - px(40),
                               justify="center")
            cv.configure(scrollregion=(0, 0, w, 1))
            return
        synced = self.mode == "synced"
        if synced:
            spec, gap = (font(28, True), px(18)) if self.big else (font(17, True), px(12))
        else:
            spec, gap = (font(18), px(6)) if self.big else (font(15), px(4))
        y, left, right = px(14), px(16), w - px(24)
        linespace = int(cv.tk.call("font", "metrics", spec, "-linespace"))
        self.word_items, self.sung = [], -1
        for i, (_, text) in enumerate(self.lines):
            tag, fill = "L%d" % i, self.color_for(i) if synced else FG
            parts = self.words[i] if synced and self.words else None
            ids = []
            if parts:
                # Per kata: tiap kata satu teks supaya bisa diwarnai sendiri; dibungkus manual karena kanvas
                # tidak bisa mewarnai sebagian teks. Suku kata yang menempel (tanpa spasi) tidak dipisah baris.
                spaced = any(" " in chunk for _, _, chunk in parts)
                x, row = left, y
                for j, (_, _, chunk) in enumerate(parts):
                    width = measure(chunk.rstrip(), spec)
                    breakable = not spaced or j == 0 or parts[j - 1][2].endswith(" ")
                    if x > left and x + width > right and breakable:
                        x, row = left, row + linespace
                    ids.append(cv.create_text(x, row, anchor="nw", text=chunk, font=spec, fill=fill, tags=(tag,)))
                    x += measure(chunk, spec)
                bottom = row + linespace
            else:
                item = cv.create_text(left, y, anchor="nw", width=w - px(40), text=text or "♪", font=spec, fill=fill,
                                      tags=(tag,))
                bottom = cv.bbox(item)[3]
            self.items.append(tag)
            self.word_items.append(ids)
            self.tops.append(y)
            self.heights.append(bottom - y)
            y = bottom + gap
        cv.configure(scrollregion=(0, 0, w, y + px(14)))
        if synced and 0 <= self.current < len(self.items) and not self.kb:
            self.center(self.current)  # tata ulang (lebar berubah, halaman baru dibuka): baris aktif tetap di tengah
        self.paint_ring()

    def at_time(self, seconds):
        if self.mode != "synced" or not self.times:
            return
        i = bisect.bisect_right(self.times, seconds + 0.2) - 1
        if i != self.current:
            old, self.current, self.sung = self.current, i, -1
            for k in range(max(0, min(old, i)), min(len(self.items), max(old, i) + 1)):
                self.cv.itemconfigure(self.items[k], fill=self.color_for(k))
            if i >= 0 and time.time() >= self.hold_until and not self.kb:
                self.center(i)
        self.paint_words(seconds)

    def paint_words(self, seconds):
        """Baris aktif per kata: kata yang sudah dinyanyikan putih, sisanya masih warna baris berikutnya."""
        i = self.current
        if i < 0 or i >= len(self.word_items) or not self.word_items[i]:
            return
        sung = sum(1 for start, _, _ in self.words[i] if start <= seconds + 0.05)
        if sung != self.sung:
            self.sung = sung
            for j, item in enumerate(self.word_items[i]):
                self.cv.itemconfigure(item, fill=FG if j < sung else self.upcoming)

    def total_height(self):
        region = self.cv.cget("scrollregion").split()
        return max(1.0, float(region[3]) if len(region) == 4 else 1.0)

    def center(self, i):
        top = self.tops[i] + self.heights[i] / 2 - self.cv.winfo_height() / 2
        self.cv.yview_moveto(max(0.0, top) / self.total_height())

    def scroll_by(self, direction):
        """Roda tetikus: gulir manual, dan tahan gulir otomatis sebentar supaya tidak melawan."""
        self.cv.yview_scroll(2 * direction, "units")
        self.hold_until = time.time() + 4

    # ----- interaksi
    def index_at(self, y):
        cy = self.cv.canvasy(y)
        for i, (top, height) in enumerate(zip(self.tops, self.heights)):
            if top - px(6) <= cy <= top + height + px(6):
                return i
        return -1

    def motion(self, event):
        clickable = self.mode == "synced" and self.index_at(event.y) >= 0
        self.cv.configure(cursor="hand2" if clickable else "")

    def click(self, event):
        self.cv.focus_set()
        self.kb = False
        self.cv.delete("ring")
        i = self.index_at(event.y)
        if self.mode == "synced" and i >= 0:
            self.on_seek(self.times[i])

    def step(self, delta):
        if self.mode not in ("synced", "plain") or not self.items:
            return "break"
        if self.cursor < 0:
            self.cursor = max(self.current, 0)
        else:
            self.cursor = max(0, min(len(self.items) - 1, self.cursor + delta))
        self.kb = True
        self.paint_ring()
        top, height, view = self.tops[self.cursor], self.heights[self.cursor], self.cv.winfo_height()
        visible_top = self.cv.canvasy(0)
        if top < visible_top or top + height > visible_top + view:
            self.cv.yview_moveto(max(0.0, top - px(20)) / self.total_height())
        return "break"

    def paint_ring(self):
        self.cv.delete("ring")
        if self.kb and self.focus_get() is self.cv and 0 <= self.cursor < len(self.items):
            top, height = self.tops[self.cursor], self.heights[self.cursor]
            self.cv.create_rectangle(px(8), top - px(4), self.width - px(8), top + height + px(4), outline=FG,
                                     width=2, tags="ring")

    def seek_cursor(self):
        if self.mode == "synced" and 0 <= self.cursor < len(self.times):
            self.on_seek(self.times[self.cursor])
        return "break"


def upcoming_color(bg):
    """Warna baris lirik yang belum dinyanyikan: gelap seperti Spotify bila kontras 3:1 (teks besar) tercapai,
    selain itu terang. Dicari campuran paling ringan supaya baris tetap terasa redup."""
    for target in ("#000000", FG):
        for step in range(1, 21):
            color = mix(bg, target, step / 20)
            if contrast(color, bg) >= 3:
                return color
    return SILVER


class PlayerView(tk.Frame):
    """Halaman Sedang diputar bergaya halaman lirik Spotify: seluruh panel tengah diwarnai warna cerah dari
    cover, kepala kecil (gambar, judul, artis yang membuka halaman artisnya, favorit), lalu lirik besar.
    Baris yang sudah dan sedang dinyanyikan putih, baris berikutnya gelap; sumber lirik di paling bawah."""

    ART = 72

    def __init__(self, parent, app):
        super().__init__(parent, bg=SURF)
        self.app, self.track, self.key, self.color = app, None, None, SURF
        self.h = px(self.ART + 24)
        self.head = tk.Canvas(self, bg=SURF, height=self.h, highlightthickness=0, bd=0)
        self.head.pack(fill="x", padx=px(8))
        self.artist = TextLink(self.head, "", lambda: app.open_artist(self.track), SURF, size=15)
        self.fav = IconButton(self.head, G_HEART, lambda: self.track and app.toggle_fav(self.track), SURF, size=40,
                              glyph_px=18)
        self.windows = [self.head.create_window(0, 0, anchor="nw", window=w, state="hidden")
                        for w in (self.artist, self.fav)]
        self.foot = tk.Frame(self, bg=SURF)
        self.foot.pack(side="bottom", fill="x", padx=px(16), pady=(px(4), px(10)))
        self.source = tk.Label(self.foot, text="", bg=SURF, fg=FG, font=font(13))
        self.retry = PillButton(self.foot, "Coba lagi", lambda: app.load_lyrics(force=True), SURF)
        self.source.pack(side="left", pady=(px(4), 0))
        self.lyrics = LyricsView(self, SURF, app.seek_to, big=True)
        self.lyrics.pack(fill="both", expand=True, padx=(px(8), px(2)), pady=(px(4), 0))
        self.head.bind("<Configure>", lambda e: self.paint())

    def show(self, track, force=False):
        if force or track is not self.track or self.key is None:
            self.track = track
            self.paint()
        else:
            liked = bool(track) and self.app.library.is_fav(track)
            self.fav.show(G_HEART_FILL if liked else G_HEART, active=liked)

    def recolor(self, color):
        """Warnai seluruh halaman (dan panel tengah bila halaman ini yang tampil) dengan warna cover."""
        if color != self.color:
            self.color = color
            for widget in (self, self.head, self.foot, self.source):
                widget.configure(bg=color)
            for control in (self.artist, self.fav):
                control.set_bg(color, dim=FG, accent=FG)
            self.retry.set_bg(color)
            self.lyrics.set_palette(color, FG, upcoming_color(color), FG)
        if self.app.view[0] == "player":
            self.app.paint_center(color)

    def paint(self):
        cv, track, app = self.head, self.track, self.app
        w, h, pad = max(cv.winfo_width(), px(300)), self.h, px(8)
        cv.delete("ink")
        wide = bool(track) and is_video(track) and len(track.get("id") or "") == 11
        ah = px(self.ART)
        aw = round(ah * 16 / 9) if wide else ah
        url = art_url(track, aw, ah, wide) if track else None
        color = (app.art_vivid.get(url) if app.cfg["tint"] and url else None) or RAISED
        self.key = (track and track.get("url"), w, url, color)
        self.recolor(color)
        top = (h - ah) // 2
        cv.create_image(pad, top, anchor="nw", image=shape(aw, ah, px(4), mix(color, "#000000", 0.35)), tags="ink")
        image = app.art(track, aw, ah, wide=wide) if track else None
        if image is not None:
            cv.create_image(pad, top, anchor="nw", image=image, tags="ink")
        else:
            cv.create_text(pad + aw // 2, top + ah // 2, text=G_NOTE, font=icon_font(28), fill=FG, tags="ink")
        cv.create_image(pad, top, anchor="nw", image=shape(aw, ah, px(4), color, inverse=True), tags="ink")
        x = pad + aw + px(16)
        side = self.fav.w + 2 * self.fav.PAD
        room = max(px(60), w - x - side - px(16))
        if not track:
            cv.create_text(x, h / 2 - px(11), anchor="w", font=font(20, True), fill=FG, text="Belum ada yang diputar",
                           tags="ink")
            cv.create_text(x, h / 2 + px(14), anchor="w", font=font(14), fill=FG, tags="ink",
                           text=fit("Putar lagu dari Beranda, Cari, atau Musik lokal.", font(14), room))
            for item in self.windows:
                cv.itemconfigure(item, state="hidden")
            return
        spec = font(22, True)
        cv.create_text(x, h / 2 - px(1), anchor="sw", font=spec, fill=FG, text=fit(track["title"], spec, room),
                       tags="ink")
        self.artist.set_text(track.get("artist") or "Artis tidak diketahui", room - 2 * self.artist.PAD)
        cv.coords(self.windows[0], x - self.artist.PAD, h / 2 + px(1))
        liked = app.library.is_fav(track)
        self.fav.show(G_HEART_FILL if liked else G_HEART, active=liked)
        cv.coords(self.windows[1], w - side - pad, (h - side) / 2)
        for item in self.windows:
            cv.itemconfigure(item, state="normal")
        self.artist.configure(state="normal")


def shortcut_list():
    mod = "Cmd" if system.MAC else "Ctrl"
    return [
        ("%s+K" % mod, "Cari"),
        ("Spasi", "Putar atau jeda"),
        ("%s+→ / %s+←" % (mod, mod), "Lagu berikutnya / sebelumnya"),
        ("%s+↑ / %s+↓" % (mod, mod), "Volume naik / turun"),
        ("%s+M" % mod, "Bisukan"),
        ("%s+S" % mod, "Acak antrean"),
        ("%s+R" % mod, "Ulangi"),
        ("%s+J" % mod, "Lirik"),
        ("%s+P" % mod, "Halaman Sedang diputar"),
        ("%s+1 sampai 5" % mod, "Beranda, Cari, Riwayat, Favorit, Musik lokal"),
        ("%s+koma" % mod, "Pengaturan"),
        ("%s+H" % mod, "Daftar pintasan ini"),
        ("Enter", "Putar baris terpilih"),
        ("F", "Favoritkan baris terpilih"),
        ("Delete", "Hapus dari antrean"),
        ("Alt+↑ / Alt+↓", "Geser lagu di antrean"),
        ("Shift+F10", "Menu untuk baris terpilih"),
    ]


def show_shortcuts(root):
    """Jendela kecil berisi semua pintasan keyboard. Escape atau tombol Tutup untuk menutup."""
    win = tk.Toplevel(root, bg=SURF)
    win.withdraw()
    win.title("Pintasan keyboard")
    win.transient(root)
    win.resizable(False, False)
    tk.Label(win, text="Pintasan keyboard", bg=SURF, fg=FG, font=font(18, True)).grid(
        row=0, column=0, columnspan=2, sticky="w", padx=px(20), pady=(px(18), px(10)))
    for row, (keys, action) in enumerate(shortcut_list(), start=1):
        tk.Label(win, text=keys, bg=SURF, fg=FG, font=font(14, True), anchor="w").grid(
            row=row, column=0, sticky="w", padx=(px(20), px(24)), pady=px(3))
        tk.Label(win, text=action, bg=SURF, fg=SILVER, font=font(14), anchor="w").grid(
            row=row, column=1, sticky="w", padx=(0, px(20)), pady=px(3))
    close = PillButton(win, "Tutup", win.destroy, SURF)
    close.grid(row=len(shortcut_list()) + 1, column=1, sticky="e", padx=px(17), pady=px(16))
    win.bind("<Escape>", lambda e: win.destroy())
    win.update_idletasks()
    win.geometry("+%d+%d" % (root.winfo_rootx() + (root.winfo_width() - win.winfo_reqwidth()) // 2,
                             root.winfo_rooty() + max(0, (root.winfo_height() - win.winfo_reqheight()) // 3)))
    system.dark_titlebar(win)
    win.deiconify()
    close.focus_set()
    return win
