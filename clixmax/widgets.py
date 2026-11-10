"""Komponen tampilan yang digambar sendiri di atas kanvas tkinter."""
import time
import tkinter as tk

from . import system
from .artwork import art_url, is_video
from .config import PLACEHOLDER
from .theme import (BG, BORDER, EDGE, FG, GREEN, GREEN_HI, GREEN_LO, HOVER, INK, LIGHT, MID, RAISED, SELECT,
                    SILVER, SURF, G_HEART, G_HEART_FILL, G_NOTE, G_SEARCH, UI, draw_tracked, fit, fit_lines,
                    font, icon_font, measure, px, shape, tracked_width)


class Control(tk.Canvas):
    """Dasar tombol gambar sendiri: hover, tekan, fokus keyboard (Tab), Enter/Spasi.

    Kanvas diberi tepi PAD piksel supaya cincin fokus putih muat di luar bentuknya.
    """
    PAD = 3
    dim, accent = SILVER, GREEN  # warna teks diam dan warna aktif; di atas latar berwarna keduanya putih

    def __init__(self, parent, w, h, bg, command=None):
        super().__init__(parent, width=w + 2 * self.PAD, height=h + 2 * self.PAD, bg=bg, highlightthickness=0,
                         bd=0, takefocus=1, cursor="hand2")
        self.w, self.h, self.bg, self.command = w, h, bg, command
        self.hot = self.down = self.focused = False
        self.bind("<Enter>", lambda e: self.mark(hot=True))
        self.bind("<Leave>", lambda e: self.mark(hot=False, down=False))
        self.bind("<ButtonPress-1>", self.press)
        self.bind("<ButtonRelease-1>", self.release)
        self.bind("<FocusIn>", lambda e: self.mark(focused=True))
        self.bind("<FocusOut>", lambda e: self.mark(focused=False))
        self.bind("<Return>", self.key)
        self.bind("<space>", self.key)

    def mark(self, **flags):
        for name, value in flags.items():
            setattr(self, name, value)
        self.paint()

    def press(self, event):
        self.mark(down=True)

    def release(self, event):
        inside = 0 <= event.x <= self.winfo_width() and 0 <= event.y <= self.winfo_height()
        fire = self.down and inside
        self.mark(down=False)
        if fire:
            self.fire()

    def key(self, event):
        self.fire()
        return "break"

    def fire(self):
        if self.command:
            self.command()

    def set_bg(self, color, dim=None, accent=None):
        """Pindah ke latar lain; dim/accent menggantikan abu dan hijau bila keduanya kurang kontras di sana."""
        self.bg, self.dim, self.accent = color, dim or type(self).dim, accent or type(self).accent
        self.configure(bg=color)
        self.paint()

    def ring(self, radius):
        if self.focused:
            p = self.PAD
            self.create_image(0, 0, anchor="nw",
                              image=shape(self.w + 2 * p, self.h + 2 * p, radius + p, self.bg, FG, 2))

    def paint(self):
        raise NotImplementedError


class PillButton(Control):
    """Aksi sekunder: pil bergaris tepi, label huruf besar berjarak (suara "label" dari arahan)."""

    def __init__(self, parent, text, command, bg, solid=False):
        # solid = pil terang berisi, untuk satu aksi utama di sebuah tampilan atau dialog.
        self.label, self.spec, self.tracking, self.solid = text.upper(), font(12, True), 1.4 * UI.scale, solid
        super().__init__(parent, int(tracked_width(self.label, self.spec, self.tracking)) + px(32), px(32), bg,
                         command)
        self.paint()

    def paint(self):
        self.delete("all")
        p, r = self.PAD, self.h / 2
        self.ring(r)
        if self.solid:
            image = shape(self.w, self.h, r, SILVER if self.down else (FG if self.hot else LIGHT))
        else:
            image = shape(self.w, self.h, r, MID if self.down else self.bg, FG if self.hot else EDGE, 1)
        self.create_image(p, p, anchor="nw", image=image)
        draw_tracked(self, p + px(16), p + self.h / 2, self.label, self.spec, INK if self.solid else FG,
                     self.tracking)


class Chip(Control):
    """Pil filter: putih saat terpilih, abu saat tidak."""

    def __init__(self, parent, text, command, bg):
        self.label, self.spec, self.on = text, font(14), False
        super().__init__(parent, measure(text, self.spec) + px(28), px(32), bg, command)
        self.paint()

    def paint(self):
        self.delete("all")
        p, r = self.PAD, self.h / 2
        self.ring(r)
        fill = FG if self.on else (SELECT if self.hot else RAISED)
        self.create_image(p, p, anchor="nw", image=shape(self.w, self.h, r, fill))
        self.create_text(p + self.w / 2, p + self.h / 2, text=self.label, font=self.spec,
                         fill=INK if self.on else FG)


class NavItem(Control):
    """Baris menu navigasi di panel kiri: ikon + nama. Yang aktif putih tebal, lainnya abu."""

    def __init__(self, parent, glyph, text, command, bg, width):
        self.glyph, self.label, self.active = glyph, text, False
        super().__init__(parent, width, px(40), bg, command)
        self.paint()

    def paint(self):
        self.delete("all")
        p = self.PAD
        self.ring(px(6))
        if self.active or self.hot:
            self.create_image(p, p, anchor="nw", image=shape(self.w, self.h, px(6),
                                                               RAISED if self.active else HOVER))
        color = FG if (self.active or self.hot) else SILVER
        spec = font(14, self.active)
        self.create_text(p + px(20), p + self.h / 2, text=self.glyph, font=icon_font(15), fill=color)
        self.create_text(p + px(40), p + self.h / 2, anchor="w", font=spec, fill=color,
                         text=fit(self.label, spec, self.w - px(50)))


class TextLink(Control):
    """Teks yang bisa diklik (nama artis): abu, putih bergaris bawah saat disentuh atau difokus."""

    def __init__(self, parent, text, command, bg, size=16):
        self.label, self.size = text, size
        super().__init__(parent, max(px(10), measure(text, font(size))), px(size + 8), bg, command)
        self.paint()

    def set_text(self, text, width):
        self.label = fit(text, font(self.size), width)
        self.w = max(px(10), measure(self.label, font(self.size)))
        self.configure(width=self.w + 2 * self.PAD)
        self.paint()

    def paint(self):
        self.delete("all")
        self.ring(px(4))
        lit = self.hot or self.focused
        spec = (UI.family, -px(self.size), "underline") if lit else font(self.size)
        self.create_text(self.PAD, self.PAD + self.h / 2, anchor="w", text=self.label, font=spec,
                         fill=FG if lit else self.dim)


class IconButton(Control):
    """Tombol ikon bulat. primary = lingkaran hijau, satu-satunya titik fokus warna di layar."""

    def __init__(self, parent, glyph, command, bg, size=36, primary=False, glyph_px=16):
        self.glyph, self.primary, self.spec, self.active = glyph, primary, icon_font(glyph_px), False
        super().__init__(parent, px(size), px(size), bg, command)
        self.paint()

    def show(self, glyph, active=None):
        """Ganti ikon; active=True mewarnai hijau untuk menandai mode yang sedang menyala."""
        if glyph != self.glyph or (active is not None and active != self.active):
            self.glyph = glyph
            if active is not None:
                self.active = active
            self.paint()

    def paint(self):
        self.delete("all")
        p, r = self.PAD, self.h / 2
        self.ring(r)
        if self.primary:
            fill = GREEN_LO if self.down else (GREEN_HI if self.hot else GREEN)
            self.create_image(p, p, anchor="nw", image=shape(self.w, self.h, r, fill))
            color = INK
        else:
            color = FG if (self.hot and not self.down) else self.dim
            if self.active:
                color = self.accent if self.accent != GREEN else (GREEN_HI if self.hot else GREEN)
        self.create_text(p + self.w / 2, p + self.h / 2, text=self.glyph, font=self.spec, fill=color)


class Toggle(Control):
    """Sakelar: hijau saat aktif."""

    def __init__(self, parent, text, on, command, bg):
        self.label, self.spec, self.on = text, font(14), on
        super().__init__(parent, px(46) + measure(text, self.spec), px(20), bg, command)
        self.paint()

    def set(self, on):
        if bool(on) != self.on:
            self.on = bool(on)
            self.paint()

    def fire(self):
        self.on = not self.on
        self.paint()
        if self.command:
            self.command(self.on)

    def paint(self):
        self.delete("all")
        p, h = self.PAD, self.h
        self.ring(h / 2)
        self.create_image(p, p, anchor="nw", image=shape(px(36), h, h / 2, GREEN if self.on else EDGE))
        knob = h - px(6)
        self.create_image(p + (px(36) - knob - px(3) if self.on else px(3)), p + px(3), anchor="nw",
                          image=shape(knob, knob, knob / 2, FG))
        self.create_text(p + px(46), p + h / 2, text=self.label, anchor="w", font=self.spec,
                         fill=FG if self.hot or self.on else SILVER)


class Slider(Control):
    """Garis geser 4 px. Hijau dan berkenop saat disentuh atau difokus; panah kiri/kanan menggeser."""

    def __init__(self, parent, bg, length=None, on_move=None, on_release=None, step=5, lo=0.0, hi=1.0):
        self.lo, self.hi, self.value, self.dragging = float(lo), float(hi), float(lo), False
        self.on_move, self.on_release, self.step = on_move, on_release, step
        super().__init__(parent, length or px(120), px(16), bg)
        if length is None:
            self.bind("<Configure>", self.resized)
        self.bind("<B1-Motion>", self.press)
        self.bind("<Left>", lambda e: self.nudge(-self.step))
        self.bind("<Right>", lambda e: self.nudge(self.step))
        self.paint()

    def resized(self, event):
        self.w = max(px(40), event.width - 2 * self.PAD)
        self.paint()

    def span(self, hi):
        self.hi = max(float(hi), self.lo + 1e-6)

    def set(self, value):
        value = min(self.hi, max(self.lo, float(value)))
        if value != self.value:
            self.value = value
            self.paint()

    def at(self, event):
        x0, x1 = self.PAD + px(6), self.PAD + self.w - px(6)
        frac = min(1.0, max(0.0, (event.x - x0) / max(1, x1 - x0)))
        return self.lo + frac * (self.hi - self.lo)

    def press(self, event):
        self.dragging = True
        self.value = self.at(event)
        self.paint()
        if self.on_move:
            self.on_move(self.value)

    def release(self, event):
        if not self.dragging:
            return
        self.value = self.at(event)
        self.dragging = False
        self.paint()
        if self.on_release:
            self.on_release(self.value)

    def nudge(self, delta):
        self.set(self.value + delta)
        for callback in (self.on_move, self.on_release):
            if callback:
                callback(self.value)
        return "break"

    def key(self, event):
        return None

    def paint(self):
        self.delete("all")
        p = self.PAD
        y, x0, x1 = p + self.h / 2, p + px(6), p + self.w - px(6)
        xv = x0 + (x1 - x0) * (self.value - self.lo) / (self.hi - self.lo)
        live = self.hot or self.dragging or self.focused
        self.create_line(x0, y, x1, y, fill=EDGE, width=px(4), capstyle="round")
        if xv > x0:
            self.create_line(x0, y, xv, y, fill=GREEN if live else FG, width=px(4), capstyle="round")
        if live:
            if self.focused:
                d = px(20)
                self.create_image(xv, y, image=shape(d, d, d / 2, self.bg, FG, 2))
            d = px(12)
            self.create_image(xv, y, image=shape(d, d, d / 2, FG))


class SearchField(tk.Canvas):
    """Kotak cari berbentuk pil. Garis tepi dalam 1 px saat diam, cincin putih 2 px saat difokus.

    on_change dipanggil setiap teks berubah karena diketik (untuk saran); on_arrow(+1/-1) dan
    on_escape untuk berpindah di daftar saran tanpa meninggalkan kotak.
    """
    PAD = 3
    QUIET = {"Up", "Down", "Left", "Right", "Return", "KP_Enter", "Escape", "Tab", "Home", "End", "Shift_L",
             "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R", "Meta_L", "Meta_R"}

    def __init__(self, parent, bg, on_submit, on_change=None, on_arrow=None, on_escape=None):
        self.h, self.bg, self.focused = px(48), bg, False
        self.on_change, self.on_arrow, self.on_escape = on_change, on_arrow, on_escape
        super().__init__(parent, height=self.h + 2 * self.PAD, width=px(240), bg=bg, highlightthickness=0, bd=0,
                         cursor="xterm")
        self.entry = tk.Entry(self, bg=MID, fg=SILVER, insertbackground=FG, relief="flat", bd=0,
                              highlightthickness=0, font=font(15), selectbackground=BORDER, selectforeground=FG)
        self.entry.insert(0, PLACEHOLDER)
        self.entry.bind("<FocusIn>", lambda e: self.focus_change(True))
        self.entry.bind("<FocusOut>", lambda e: self.focus_change(False))
        self.entry.bind("<Return>", lambda e: on_submit())
        self.entry.bind("<KeyRelease>", self.typed)
        self.entry.bind("<Down>", lambda e: self.arrow(1))
        self.entry.bind("<Up>", lambda e: self.arrow(-1))
        self.entry.bind("<Escape>", lambda e: self.on_escape and self.on_escape())
        self.bind("<Button-1>", lambda e: self.entry.focus_set())
        self.bind("<Configure>", lambda e: self.paint())

    def typed(self, event):
        if self.on_change and event.keysym not in self.QUIET and not (event.state & 0x4):
            self.on_change(self.text())

    def arrow(self, delta):
        if self.on_arrow and self.on_arrow(delta):
            return "break"
        return None

    def focus_change(self, on):
        self.focused = on
        if on and self.entry.get() == PLACEHOLDER:
            self.entry.delete(0, "end")
            self.entry.configure(fg=FG)
        elif not on and not self.entry.get():
            self.entry.insert(0, PLACEHOLDER)
            self.entry.configure(fg=SILVER)
        self.paint()

    def text(self):
        value = self.entry.get().strip()
        return "" if value == PLACEHOLDER else value

    def put(self, value):
        self.entry.delete(0, "end")
        self.entry.insert(0, value)
        self.entry.configure(fg=FG)

    def paint(self):
        self.delete("all")
        p, h, w = self.PAD, self.h, max(px(120), self.winfo_width())
        if self.focused:
            self.ring_img = shape(w, h + 2 * p, h / 2 + p, self.bg, FG, 2, keep=False)
            self.create_image(0, 0, anchor="nw", image=self.ring_img)
        self.pill_img = shape(w - 2 * p, h, h / 2, MID, None if self.focused else EDGE, 1, keep=False)
        self.create_image(p, p, anchor="nw", image=self.pill_img)
        self.create_text(p + px(26), p + h / 2, text=G_SEARCH, font=icon_font(16),
                         fill=FG if self.focused else SILVER)
        self.create_window(p + px(50), p + h / 2, anchor="w", window=self.entry, width=w - 2 * p - px(74),
                           height=h - px(16))


class SuggestBox(tk.Canvas):
    """Daftar saran di bawah kotak cari, melayang di atas isi jendela.

    Dikendalikan dari kotak cari: panah bawah/atas memilih, Enter memakai, Escape menutup; klik juga bisa.
    """

    def __init__(self, root, on_pick):
        super().__init__(root, bg=BG, highlightthickness=0, bd=0, cursor="hand2")
        self.root, self.on_pick = root, on_pick
        self.items, self.cursor, self.rh, self.w, self.h = [], -1, px(38), 0, 0
        self.bind("<Motion>", lambda e: self.point(self.index_at(e.y)))
        self.bind("<Button-1>", self.click)

    @property
    def shown(self):
        return bool(self.items)

    def show(self, items, field):
        self.items, self.cursor = list(items), -1
        self.w = field.winfo_width() - 2 * field.PAD
        self.h = len(self.items) * self.rh + px(12)
        x = field.winfo_rootx() - self.root.winfo_rootx() + field.PAD
        y = field.winfo_rooty() - self.root.winfo_rooty() + field.winfo_height() + px(2)
        self.place(x=x, y=y, width=self.w, height=self.h)
        tk.Misc.tkraise(self)  # Canvas.lift menaikkan item di dalam kanvas, bukan jendelanya
        self.paint()

    def hide(self):
        if self.items:
            self.items, self.cursor = [], -1
            self.place_forget()

    def paint(self):
        self.delete("all")
        self.create_image(0, 0, anchor="nw", image=shape(self.w, self.h, px(8), RAISED, BORDER, 1, keep=False))
        self.frame_img = self.find_all()  # simpan acuan gambar latar di kanvas
        for i, text in enumerate(self.items):
            y = px(6) + i * self.rh
            if i == self.cursor:
                self.create_image(px(6), y, anchor="nw", image=shape(self.w - px(12), self.rh, px(6), SELECT))
            self.create_text(px(26), y + self.rh / 2, text=G_SEARCH, font=icon_font(13), fill=SILVER)
            self.create_text(px(48), y + self.rh / 2, anchor="w", font=font(15), fill=FG,
                             text=fit(text, font(15), self.w - px(64)))

    def index_at(self, y):
        i = int((y - px(6)) // self.rh)
        return i if 0 <= i < len(self.items) else -1

    def point(self, i):
        if i != self.cursor:
            self.cursor = i
            self.paint()

    def move(self, delta):
        """Geser pilihan; False bila daftar tidak tampil (panah dibiarkan untuk kotak cari)."""
        if not self.items:
            return False
        self.point(max(-1, min(len(self.items) - 1, self.cursor + delta)))
        return True

    def current(self):
        return self.items[self.cursor] if 0 <= self.cursor < len(self.items) else None

    def click(self, event):
        i = self.index_at(event.y)
        if i >= 0:
            self.on_pick(self.items[i])


class TrackList(tk.Frame):
    """Daftar lagu di atas kanvas: gambar, judul, artis, durasi, hati; plus status kosong/memuat/gagal.

    Baris {"header": teks} digambar sebagai judul rak dan tidak bisa dipilih.
    Mouse: klik pilih, Ctrl (Cmd di macOS)/Shift untuk banyak, klik dua kali jalankan, klik hati,
    klik kanan untuk menu, seret untuk mengurutkan (bila on_move diberikan).
    Keyboard: panah, Home/End, Enter jalankan, Delete hapus, F favorit, Ctrl+A pilih semua,
    Shift+F10 menu, Alt+panah geser baris (bila on_move diberikan).
    """

    def __init__(self, parent, bg, app, on_activate, on_delete=None, on_menu=None, on_move=None):
        super().__init__(parent, bg=bg)
        self.bg, self.app, self.on_activate, self.on_delete = bg, app, on_activate, on_delete
        self.on_menu, self.on_move = on_menu, on_move
        self.rows, self.cells, self.sel = [], [], set()
        self.cursor = self.pivot = self.hot = self.now = -1
        self.note = self.job = self.drag = None
        self.focused = self.kb = self.bar_hot = False
        self.clicked_at = 0.0
        self.built_w, self.view = 0, (0.0, 1.0)
        self.rh, self.art = px(56), px(40)
        self.text_w, self.heart_x = px(40), 0
        self.cv = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0, takefocus=1, yscrollincrement=px(28),
                            height=px(120))
        self.bar = tk.Canvas(self, width=px(12), bg=bg, highlightthickness=0, bd=0, height=px(120))
        self.bar.pack(side="right", fill="y")
        self.cv.pack(side="left", fill="both", expand=True)
        self.cv.configure(yscrollcommand=self.scrolled)
        cv = self.cv
        cv.bind("<Configure>", self.resized)
        cv.bind("<Motion>", lambda e: self.hover(self.row_at(e.y)))
        cv.bind("<Leave>", lambda e: self.hover(-1))
        cv.bind("<Button-1>", self.click)
        cv.bind("<B1-Motion>", self.drag_motion)
        cv.bind("<ButtonRelease-1>", self.drag_end)
        cv.bind("<Double-Button-1>", self.double)
        for sequence in system.CONTEXT_CLICK:
            cv.bind(sequence, self.context_click)
        cv.bind("<Shift-F10>", self.context_key)
        if system.WINDOWS:
            cv.bind("<App>", self.context_key)
        cv.bind("<f>", lambda e: self.like_selected())
        cv.bind("<F>", lambda e: self.like_selected())
        cv.bind("<FocusIn>", lambda e: self.focus_change(True))
        cv.bind("<FocusOut>", lambda e: self.focus_change(False))
        cv.bind("<Up>", lambda e: self.step(-1))
        cv.bind("<Down>", lambda e: self.step(1))
        cv.bind("<Home>", lambda e: self.step(to=0))
        cv.bind("<End>", lambda e: self.step(to=-1))
        cv.bind("<Return>", lambda e: self.activate_key())
        cv.bind("<Delete>", lambda e: self.on_delete() if self.on_delete else None)
        cv.bind("<%s-a>" % system.SHORTCUT, lambda e: self.pick_all())
        for arrow in ("Up", "Down"):  # Ctrl+atas/bawah adalah pintasan volume: biarkan lewat ke jendela
            cv.bind("<%s-%s>" % (system.SHORTCUT, arrow), lambda e: None)
        if on_move:
            cv.bind("<Alt-Up>", lambda e: self.nudge_row(-1))
            cv.bind("<Alt-Down>", lambda e: self.nudge_row(1))
        self.bar.bind("<Enter>", lambda e: self.bar_mark(True))
        self.bar.bind("<Leave>", lambda e: self.bar_mark(False))
        self.bar.bind("<Button-1>", self.bar_drag)
        self.bar.bind("<B1-Motion>", self.bar_drag)
        self.bar.bind("<Configure>", lambda e: self.bar_paint())

    # ----- isi
    def fill(self, rows):
        self.rows[:] = rows
        self.note = None
        self.sel.clear()
        self.cursor = self.pivot = self.hot = -1
        self.render()
        self.cv.yview_moveto(0)

    def append(self, tracks):
        self.note = None
        self.rows.extend(tracks)
        self.render()

    def insert(self, at, tracks):
        self.note = None
        self.rows[at:at] = tracks
        if self.now >= at:
            self.now += len(tracks)
        self.sel.clear()
        self.render()

    def remove(self, indices):
        for i in sorted(indices, reverse=True):
            del self.rows[i]
        self.sel.clear()
        self.cursor = self.pivot = min(self.cursor, len(self.rows) - 1)
        self.render()

    def move(self, src, dst):
        """Pindahkan satu baris; penanda "sedang diputar" ikut bergeser."""
        self.rows.insert(dst, self.rows.pop(src))
        if self.now == src:
            self.now = dst
        elif src < self.now <= dst:
            self.now -= 1
        elif dst <= self.now < src:
            self.now += 1
        self.sel, self.cursor, self.pivot = {dst}, dst, dst
        self.render()
        self.reveal(dst)

    def say(self, title, hint="", color=FG):
        """Status kosong atau gagal menggantikan daftar."""
        self.rows[:] = []
        self.sel.clear()
        self.cursor = self.pivot = self.hot = -1
        self.note = (title, hint, color)
        self.render()

    def wait(self):
        """Status memuat: kerangka baris berbentuk sama dengan hasil akhirnya."""
        self.rows[:] = []
        self.sel.clear()
        self.cursor = self.pivot = self.hot = -1
        self.note = "wait"
        self.render()

    def selection(self):
        return sorted(self.sel)

    def is_header(self, i):
        return 0 <= i < len(self.rows) and "header" in self.rows[i]

    def picks(self):
        return [i for i in range(len(self.rows)) if "header" not in self.rows[i]]

    def mark_now(self, index):
        old, self.now = self.now, index
        for i in (old, index):
            if 0 <= i < len(self.cells):
                self.paint_row(i)
        if 0 <= index < len(self.cells):
            self.reveal(index)

    def retitle(self, index):
        if 0 <= index < len(self.cells) and self.cells[index]:
            self.cv.itemconfigure(self.cells[index]["title"],
                                  text=fit(self.rows[index]["title"], font(15), self.text_w))

    def refresh_art(self):
        for track, cell in zip(self.rows, self.cells):
            if cell:
                image = self.app.art(track, self.art)
                if image is not None and image is not cell["img"]:
                    # Item baru di lapisan yang sama, lalu yang lama dihapus. Mengganti -image lewat itemconfigure
                    # pada item yang dibuat tanpa gambar membuat Tk 8.6.12 (Ubuntu 22.04) kadang crash.
                    old = cell["art"]
                    cell["art"] = self.cv.create_image(*self.cv.coords(old), anchor="nw", image=image)
                    self.cv.tag_raise(cell["art"], old)
                    self.cv.delete(old)
                    cell["img"] = image

    # ----- gambar
    def render(self):
        self.job = None
        cv = self.cv
        cv.delete("all")
        self.cells = []
        w = max(cv.winfo_width(), px(240))
        if w != self.built_w:
            self.built_w, h, r = w, self.rh - 2, px(6)
            self.row_img = {}
            for name, color in (("hot", HOVER), ("sel", SELECT), ("", self.bg)):
                if name:
                    self.row_img[name] = shape(w, h, r, color, keep=False)
                self.row_img[name + "+cur"] = shape(w, h, r, color, FG, 2, keep=False)
        if self.note:
            self.render_note(w)
            return
        rh, art = self.rh, self.art
        blank = shape(art, art, 0, RAISED, inverse=True)  # transparen penuh: ubin dan ikon not tetap terlihat
        self.text_w = max(px(40), w - px(60) - px(112))
        self.heart_x = w - px(88)
        for i, track in enumerate(self.rows):
            y = i * rh
            if "header" in track:
                cv.create_text(px(10), y + rh - px(12), anchor="sw", font=font(17, True), fill=FG,
                               text=fit(track["header"], font(17, True), w - px(20)))
                self.cells.append(None)
                continue
            # Item gambar selalu dibuat langsung dengan gambarnya (lihat refresh_art soal Tk 8.6.12).
            cell = {"bg": cv.create_image(0, y + 1, anchor="nw", image=self.row_img["hot"], state="hidden"),
                    "img": self.app.art(track, art)}
            ay = y + (rh - art) // 2
            # Ubin + not selalu ada di bawah; gambarnya menutupi begitu selesai diunduh.
            cv.create_image(px(8), ay, anchor="nw", image=shape(art, art, px(4), RAISED))
            cv.create_text(px(8) + art // 2, ay + art // 2, text=G_NOTE, font=icon_font(16), fill=SILVER)
            cell["art"] = cv.create_image(px(8), ay, anchor="nw", image=cell["img"] or blank)
            cell["mask"] = cv.create_image(px(8), ay, anchor="nw",
                                           image=shape(art, art, px(4), self.bg, inverse=True))
            cell["title"] = cv.create_text(px(60), y + px(19), anchor="w", font=font(15), fill=FG,
                                           text=fit(track["title"], font(15), self.text_w))
            sub = " · ".join(part for part in (track.get("tag"), track["artist"]) if part)
            cv.create_text(px(60), y + px(38), anchor="w", font=font(13), fill=SILVER,
                           text=fit(sub, font(13), self.text_w))
            cv.create_text(w - px(14), y + rh // 2, anchor="e", font=font(13), fill=SILVER, text=track["dur"])
            # Hati hanya untuk baris yang bisa diputar; artis/album/playlist tidak bisa difavoritkan.
            cell["heart"] = (cv.create_text(self.heart_x, y + rh // 2, font=icon_font(15), state="hidden")
                             if "url" in track else None)
            self.cells.append(cell)
            self.paint_row(i)
        cv.configure(scrollregion=(0, 0, w, max(1, len(self.rows) * rh)))

    def render_note(self, w):
        cv, art = self.cv, self.art
        cv.configure(scrollregion=(0, 0, w, 1))
        cv.yview_moveto(0)
        if self.note == "wait":
            for i in range(6):
                y = i * self.rh + (self.rh - art) // 2
                cv.create_image(px(8), y, anchor="nw", image=shape(art, art, px(4), RAISED))
                cv.create_image(px(60), y + px(4), anchor="nw", image=shape(px(190), px(12), px(6), RAISED))
                cv.create_image(px(60), y + px(24), anchor="nw", image=shape(px(110), px(10), px(5), RAISED))
            return
        title, hint, color = self.note
        cv.create_text(w / 2, px(64), text=title, font=font(18, True), fill=color, width=w - px(48),
                       justify="center")
        if hint:
            cv.create_text(w / 2, px(84), anchor="n", text=hint, font=font(14), fill=SILVER, width=w - px(48),
                           justify="center")

    def paint_row(self, i):
        cell = self.cells[i]
        if cell is None:
            return
        selected = i in self.sel
        cursor = self.focused and self.kb and i == self.cursor
        name = ("sel" if selected else "hot" if i == self.hot else "") + ("+cur" if cursor else "")
        color = SELECT if selected else (HOVER if i == self.hot else self.bg)
        if name:
            self.cv.itemconfigure(cell["bg"], image=self.row_img[name], state="normal")
        else:
            self.cv.itemconfigure(cell["bg"], state="hidden")
        self.cv.itemconfigure(cell["mask"], image=shape(self.art, self.art, px(4), color, inverse=True))
        self.cv.itemconfigure(cell["title"], fill=GREEN if i == self.now else FG)
        if cell["heart"]:
            liked = self.app.library.is_fav(self.rows[i])
            self.cv.itemconfigure(cell["heart"], text=G_HEART_FILL if liked else G_HEART,
                                  fill=GREEN if liked else SILVER,
                                  state="normal" if (liked or selected or i == self.hot) else "hidden")

    def repaint(self):
        for i in range(len(self.cells)):
            self.paint_row(i)

    def on_heart(self, event):
        i = self.row_at(event.y)
        return (i >= 0 and bool(self.cells[i]) and bool(self.cells[i]["heart"])
                and abs(event.x - self.heart_x) <= px(15))

    def like_selected(self):
        """Tombol F: favoritkan (atau batalkan) lagu yang dipilih."""
        for i in self.selection():
            if "url" in self.rows[i]:
                self.app.toggle_fav(self.rows[i])
        return "break"

    def resized(self, event):
        if event.width != self.built_w and self.job is None:
            self.job = self.after(60, self.render)

    # ----- interaksi
    def row_at(self, y):
        if self.note:
            return -1
        i = int(self.cv.canvasy(y) // self.rh)
        return i if 0 <= i < len(self.rows) else -1

    def hover(self, i):
        if self.is_header(i):
            i = -1
        old, self.hot = self.hot, i
        for j in (old, i):
            if j != -1 and j < len(self.cells) and old != i:
                self.paint_row(j)

    def click(self, event):
        self.clicked_at = time.time()
        self.kb = False
        self.cv.focus_set()
        i = self.row_at(event.y)
        if i < 0 or self.is_header(i):
            return
        if self.on_heart(event):
            self.app.toggle_fav(self.rows[i])
            return
        multi, shift = bool(event.state & system.MULTI_SELECT), bool(event.state & 0x1)
        self.pick(i, ctrl=multi, shift=shift)
        if self.on_move and not (multi or shift):
            self.drag = {"from": i, "y": event.y, "live": False}

    def double(self, event):
        i = self.row_at(event.y)
        if i >= 0 and not self.is_header(i) and not self.on_heart(event):
            self.on_activate()

    def drag_motion(self, event):
        d = self.drag
        if not d:
            return
        if not d["live"]:
            if abs(event.y - d["y"]) < px(6):
                return
            d["live"] = True
        height = self.cv.winfo_height()
        if event.y < px(16):
            self.cv.yview_scroll(-1, "units")
        elif event.y > height - px(16):
            self.cv.yview_scroll(1, "units")
        d["gap"] = min(len(self.rows), max(0, int(round(self.cv.canvasy(event.y) / self.rh))))
        self.cv.delete("drop")
        y = d["gap"] * self.rh
        self.cv.create_line(px(8), y, self.cv.winfo_width() - px(8), y, fill=GREEN, width=px(2), tags="drop")

    def drag_end(self, event):
        d, self.drag = self.drag, None
        self.cv.delete("drop")
        if not d or not d["live"] or "gap" not in d:
            return
        src, gap = d["from"], d["gap"]
        dst = gap if gap <= src else gap - 1
        if dst != src:
            self.on_move(src, dst)

    def nudge_row(self, delta):
        i, j = self.cursor, self.cursor + delta
        if 0 <= i < len(self.rows) and 0 <= j < len(self.rows):
            self.kb = True
            self.on_move(i, j)
        return "break"

    def context_click(self, event):
        i = self.row_at(event.y)
        if i < 0 or self.is_header(i) or not self.on_menu:
            return None
        if i not in self.sel:
            self.pick(i)
        self.cv.focus_set()
        self.on_menu(self, event.x_root, event.y_root)
        return "break"

    def context_key(self, event=None):
        if self.sel and self.on_menu:
            i = self.cursor if self.cursor in self.sel else min(self.sel)
            self.reveal(i)
            x = self.cv.winfo_rootx() + px(60)
            y = self.cv.winfo_rooty() + int(i * self.rh - self.cv.canvasy(0)) + self.rh
            self.on_menu(self, x, y)
        return "break"

    def pick(self, i, ctrl=False, shift=False):
        dirty = set(self.sel) | {self.cursor, i}
        if shift and self.pivot >= 0:
            self.sel = {k for k in range(min(self.pivot, i), max(self.pivot, i) + 1) if not self.is_header(k)}
        elif ctrl:
            self.sel ^= {i}
            self.pivot = i
        else:
            self.sel = {i}
            self.pivot = i
        self.cursor = i
        for j in dirty | self.sel:
            if 0 <= j < len(self.cells):
                self.paint_row(j)

    def pick_all(self):
        self.sel = set(self.picks())
        for j in range(len(self.cells)):
            self.paint_row(j)
        return "break"

    def step(self, delta=0, to=None):
        options = self.picks()
        if not options or self.note:
            return "break"
        if to is not None:
            i = options[0] if to == 0 else options[-1]
        elif self.cursor not in options:
            i = options[0]
        elif delta > 0:
            i = next((k for k in options if k > self.cursor), self.cursor)
        else:
            i = next((k for k in reversed(options) if k < self.cursor), self.cursor)
        self.kb = True
        self.pick(i)
        self.reveal(i)
        return "break"

    def activate_key(self):
        if self.sel:
            self.on_activate()
        return "break"

    def focus_change(self, on):
        self.focused = on
        self.kb = on and time.time() - self.clicked_at > 0.3
        if on and self.cursor < 0 and not self.note:
            options = self.picks()
            if options:
                self.cursor = self.pivot = options[0]
        if 0 <= self.cursor < len(self.cells):
            self.paint_row(self.cursor)

    def reveal(self, i):
        total, top, height = len(self.rows) * self.rh, self.cv.canvasy(0), self.cv.winfo_height()
        if total <= height:
            return
        if i * self.rh < top:
            self.cv.yview_moveto(i * self.rh / total)
        elif (i + 1) * self.rh > top + height:
            self.cv.yview_moveto(((i + 1) * self.rh - height) / total)

    def scroll_by(self, direction):
        if self.view != (0.0, 1.0):
            self.cv.yview_scroll(2 * direction, "units")

    # ----- batang gulir tipis
    def scrolled(self, first, last):
        self.view = (float(first), float(last))
        self.bar_paint()

    def bar_mark(self, hot):
        self.bar_hot = hot
        self.bar_paint()

    def bar_paint(self):
        self.bar.delete("all")
        first, last = self.view
        if last - first >= 0.999:
            return
        height, x = self.bar.winfo_height(), px(6)
        y0 = first * height + px(5)
        y1 = max(y0 + px(20), last * height - px(5))
        self.bar.create_line(x, y0, x, y1, fill=SILVER if self.bar_hot else EDGE, width=px(6),
                             capstyle="round")

    def bar_drag(self, event):
        first, last = self.view
        self.cv.yview_moveto(event.y / max(1, self.bar.winfo_height()) - (last - first) / 2)


class NowInfo(tk.Canvas):
    """Judul + artis lagu yang sedang diputar.

    cover=True: versi bilah bawah dengan gambar persegi kecil di kiri.
    eyebrow: versi kartu "Sedang diputar" dengan label kecil dan judul dua baris.
    """

    def __init__(self, parent, bg, app, cover=True, eyebrow="", on_open=None, on_artist=None):
        super().__init__(parent, height=px(56) if cover else px(104), width=px(120), bg=bg,
                         highlightthickness=0, bd=0)
        self.bg, self.app, self.cover, self.eyebrow = bg, app, cover, eyebrow
        self.shown, self.args, self.img = None, ("", "", None), None
        self.bind("<Configure>", lambda e: self.paint())
        # Klik gambar atau judul membuka halaman Sedang diputar; klik nama artis membuka halaman artisnya.
        if on_open:
            self.tag_bind("open", "<Button-1>", lambda e: on_open())
        if on_artist:
            self.tag_bind("artist", "<Button-1>", lambda e: on_artist(self.args[2]))
            self.tag_bind("artist", "<Enter>", lambda e: self.itemconfigure(
                "artist", fill=FG, font=self.artist_font(True)))
            self.tag_bind("artist", "<Leave>", lambda e: self.itemconfigure(
                "artist", fill=SILVER, font=self.artist_font(False)))
        for tag in ("open", "artist"):
            self.tag_bind(tag, "<Enter>", lambda e: self.configure(cursor="hand2"), add="+")
            self.tag_bind(tag, "<Leave>", lambda e: self.configure(cursor=""), add="+")

    def artist_font(self, lit):
        return (UI.family, -px(13), "underline") if lit else font(13)

    def set_bg(self, color):
        self.bg = color
        self.configure(bg=color)
        self.shown = None
        self.paint()

    def show(self, title, sub, track):
        self.args = (title, sub, track)
        image = self.app.art(track, px(56)) if (track and self.cover) else None
        key = (title, sub, str(image), bool(track))
        if key != self.shown:
            self.shown = key
            self.paint()

    def paint(self):
        title, sub, track = self.args
        self.delete("all")
        x, size, w = 0, px(56), self.winfo_width()
        open_tag = ("open",) if track else ()
        sub_tag = ("artist",) if track and sub and sub == track.get("artist") else ()
        if track and self.cover:
            self.create_image(0, 0, anchor="nw", image=shape(size, size, px(6), RAISED), tags=open_tag)
            self.create_text(size // 2, size // 2, text=G_NOTE, font=icon_font(20), fill=SILVER, tags=open_tag)
            self.img = self.app.art(track, size)
            if self.img is not None:
                self.create_image(0, 0, anchor="nw", image=self.img, tags=open_tag)
            self.create_image(0, 0, anchor="nw", image=shape(size, size, px(6), self.bg, inverse=True), tags=open_tag)
            x = size + px(12)
        room = max(px(20), w - x - px(8))
        color = FG if track else SILVER
        if self.eyebrow:
            self.create_text(x, px(8), anchor="nw", font=font(12), fill=SILVER, text=self.eyebrow)
            y = px(28)
            for line in fit_lines(title, font(16, True), room):
                self.create_text(x, y, anchor="nw", font=font(16, True), fill=color, text=line, tags=open_tag)
                y += px(21)
            self.create_text(x, y + px(4), anchor="nw", font=font(13), fill=SILVER, text=fit(sub, font(13), room),
                             tags=sub_tag)
            return
        self.create_text(x, px(19), anchor="w", font=font(14, True), fill=color,
                         text=fit(title, font(14, True), room), tags=open_tag)
        self.create_text(x, px(40), anchor="w", font=font(13), fill=SILVER, text=fit(sub, font(13), room),
                         tags=sub_tag)


class NowArt(tk.Canvas):
    """Gambar di kartu "Sedang diputar": thumbnail 16:9 untuk video, cover persegi untuk lagu."""

    def __init__(self, parent, bg, app, height=104):
        self.h = px(height)
        super().__init__(parent, width=self.h, height=self.h, bg=bg, highlightthickness=0, bd=0)
        self.bg, self.app, self.key, self.image, self.wide = bg, app, None, None, False
        self.track = self.url = None
        self.load(None)

    def set_bg(self, color):
        self.bg = color
        self.configure(bg=color)
        self.key = None
        self.load(self.track)

    def load(self, track):
        self.track = track
        wide = bool(track) and is_video(track) and len(track.get("id") or "") == 11
        w = round(self.h * 16 / 9) if wide else self.h
        self.url = art_url(track, w, self.h, wide) if track else None
        image = self.app.art(track, w, self.h, wide=wide) if track else None
        key = (w, str(image), bool(track), self.bg)
        if key == self.key:
            return
        self.key, self.image, self.wide = key, image, wide
        self.configure(width=w)
        self.delete("all")
        self.create_image(0, 0, anchor="nw", image=shape(w, self.h, px(8), RAISED))
        if image is not None:
            self.create_image(0, 0, anchor="nw", image=image)
        else:
            self.create_text(w // 2, self.h // 2, text=G_NOTE, font=icon_font(28), fill=SILVER)
        self.create_image(0, 0, anchor="nw", image=shape(w, self.h, px(8), self.bg, inverse=True))


class NowCard(tk.Canvas):
    """Kartu "Sedang diputar": gambar + judul di atas latar yang bisa diwarnai dari cover."""

    def __init__(self, parent, bg, app, on_open=None, on_artist=None):
        self.pad, self.inner_h = px(12), px(104)
        super().__init__(parent, height=self.inner_h + 2 * self.pad, width=px(200), bg=bg, highlightthickness=0,
                         bd=0)
        self.outer = self.tint = bg
        self.drawn = None
        self.art = NowArt(self, bg, app)
        self.info = NowInfo(self, bg, app, cover=False, eyebrow="Sedang diputar", on_open=on_open,
                            on_artist=on_artist)
        if on_open:
            self.art.bind("<Button-1>", lambda e: self.art.track and on_open())
            self.art.bind("<Enter>", lambda e: self.art.configure(cursor="hand2" if self.art.track else ""))
        self.art_item = self.create_window(self.pad, self.pad, anchor="nw", window=self.art)
        self.info_item = self.create_window(self.pad, self.pad, anchor="nw", window=self.info)
        self.bind("<Configure>", lambda e: self.layout())

    def load(self, track):
        self.art.load(track)
        self.layout()

    def set_tint(self, color):
        color = color or self.outer
        if color != self.tint:
            self.tint = color
            self.art.set_bg(color)
            self.info.set_bg(color)
            self.layout()

    def layout(self):
        w, h = max(self.winfo_width(), px(200)), self.inner_h + 2 * self.pad
        if (w, self.tint) != self.drawn:
            self.drawn = (w, self.tint)
            self.delete("tint")
            if self.tint != self.outer:
                self.tint_img = shape(w, h, px(8), self.tint, keep=False)
                self.create_image(0, 0, anchor="nw", image=self.tint_img, tags="tint")
                self.tag_lower("tint")
        x = self.pad + self.art.winfo_reqwidth() + px(14)
        self.coords(self.info_item, x, self.pad)
        self.itemconfigure(self.info_item, width=max(px(40), w - x - self.pad), height=self.inner_h)


class ScrollFrame(tk.Frame):
    """Wadah yang bisa digulir; isinya ditaruh di .inner. Roda tetikus diteruskan App lewat scroll_by,
    dan kontrol yang difokus keyboard otomatis digulir ke dalam pandangan (lihat watch)."""

    def __init__(self, parent, bg):
        super().__init__(parent, bg=bg)
        self.cv = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0, yscrollincrement=px(20), height=px(40),
                            width=px(40))
        self.cv.pack(fill="both", expand=True)
        self.inner = tk.Frame(self.cv, bg=bg)
        self.window = self.cv.create_window(0, 0, anchor="nw", window=self.inner)
        self.inner.bind("<Configure>", lambda e: self.cv.configure(scrollregion=(0, 0, e.width, e.height)))
        self.cv.bind("<Configure>", lambda e: self.cv.itemconfigure(self.window, width=e.width))

    def scroll_by(self, direction):
        if self.inner.winfo_reqheight() > self.cv.winfo_height():
            self.cv.yview_scroll(2 * direction, "units")

    def watch(self, widget):
        widget.bind("<FocusIn>", lambda e: self.reveal(widget), add="+")

    def reveal(self, widget):
        y = widget.winfo_rooty() - self.inner.winfo_rooty()
        top, view = self.cv.canvasy(0), self.cv.winfo_height()
        total = max(1, self.inner.winfo_reqheight())
        if y < top:
            self.cv.yview_moveto(y / total)
        elif y + widget.winfo_height() > top + view:
            self.cv.yview_moveto((y + widget.winfo_height() - view) / total)


class Panel(tk.Frame):
    """Permukaan #181818 dengan sudut 8 px (empat potongan sudut ditempel di pojok)."""

    def __init__(self, parent, outer, fill=SURF):
        super().__init__(parent, bg=fill)
        self.outer, self.labels, self.quads = outer, [], []
        for relx, rely, anchor in ((0, 0, "nw"), (1, 0, "ne"), (0, 1, "sw"), (1, 1, "se")):
            label = tk.Label(self, bg=outer, bd=0, highlightthickness=0)
            label.place(relx=relx, rely=rely, anchor=anchor)
            self.labels.append(label)
        self.set_fill(fill)

    def set_fill(self, fill):
        """Warnai ulang permukaan dan keempat potongan sudutnya."""
        self.fill = fill
        self.configure(bg=fill)
        r = px(8)
        full = shape(2 * r, 2 * r, r, fill)
        self.quads = []
        for (x, y), label in zip(((0, 0), (r, 0), (0, r), (r, r)), self.labels):
            quad = tk.PhotoImage(width=r, height=r)
            quad.tk.call(quad, "copy", full, "-from", x, y, x + r, y + r)
            self.quads.append(quad)
            label.configure(image=quad)
            label.lift()


def ask_text(root, title, prompt):
    """Dialog kecil untuk satu baris teks. Enter menyimpan, Escape membatalkan. None bila batal."""
    win = tk.Toplevel(root, bg=SURF)
    win.withdraw()
    win.title(title)
    win.transient(root)
    win.resizable(False, False)
    tk.Label(win, text=prompt, bg=SURF, fg=FG, font=font(14, True)).pack(anchor="w", padx=px(20),
                                                                         pady=(px(18), px(8)))
    entry = tk.Entry(win, bg=MID, fg=FG, insertbackground=FG, relief="flat", bd=0, font=font(15), width=30,
                     highlightthickness=2, highlightbackground=EDGE, highlightcolor=FG)
    entry.pack(padx=px(20), ipady=px(7))
    row = tk.Frame(win, bg=SURF)
    row.pack(anchor="e", padx=px(17), pady=px(16))
    answer = []

    def save():
        if entry.get().strip():
            answer.append(entry.get().strip())
            win.destroy()

    PillButton(row, "Batal", win.destroy, SURF).pack(side="left")
    PillButton(row, "Simpan", save, SURF, solid=True).pack(side="left", padx=(px(2), 0))
    entry.bind("<Return>", lambda e: save())
    win.bind("<Escape>", lambda e: win.destroy())
    win.update_idletasks()
    win.geometry("+%d+%d" % (root.winfo_rootx() + (root.winfo_width() - win.winfo_reqwidth()) // 2,
                             root.winfo_rooty() + (root.winfo_height() - win.winfo_reqheight()) // 3))
    system.dark_titlebar(win)
    win.deiconify()
    win.grab_set()
    entry.focus_set()
    root.wait_window(win)
    return answer[0] if answer else None
