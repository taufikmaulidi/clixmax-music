"""Jendela utama ClixMax: membangun tampilan dan menyatukan bagian Playback dan Browsing."""
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import traceback
import tkinter as tk
from tkinter import messagebox

from . import artwork, config, media, system, tray
from .browsing import Browsing
from .config import APP, KINDS, TITLE, log_error, read_json, write_json
from .island import Island
from .library import Library
from .localfiles import LocalIndex
from .lyrics import LyricsCache
from .playback import Playback
from .theme import (BG, FG, SILVER, SURF, G_ADD, G_FOLDER, G_HEART, G_HISTORY, G_HOME, G_LIST, G_LYRICS, G_NEXT,
                    G_PLAY, G_PREV, G_REPEAT, G_SEARCH, G_SETTINGS, G_SHUFFLE, G_VOL, UI, fit, font, pick_family, px)
from .views import LyricsView, PlayerView, SettingsView, show_shortcuts
from .widgets import (Chip, Control, IconButton, NavItem, NowCard, NowInfo, Panel, PillButton, ScrollFrame,
                      SearchField, Slider, SuggestBox, Toggle, TrackList)

TITLES = {"home": "Beranda", "search": "Hasil pencarian", "history": "Riwayat", "favorites": "Favorit",
          "local": "Musik lokal", "settings": "Pengaturan", "player": "Sedang diputar"}
NAV = (("home", G_HOME, "Beranda"), ("search", G_SEARCH, "Cari"), ("history", G_HISTORY, "Riwayat"),
       ("favorites", G_HEART, "Favorit"), ("local", G_FOLDER, "Musik lokal"))


class App(Playback, Browsing):
    def __init__(self, root, cfg, startup_query=""):
        self.root = root
        self.cfg = dict(config.DEFAULTS)
        self.cfg.update({key: value for key, value in cfg.items() if key in config.DEFAULTS})
        self.cmdq, self.uiq, self.artq = queue.Queue(), queue.Queue(), queue.Queue()
        self.alive = True
        self.pos, self.state, self.state_at = -1, None, 0.0
        self.search_token = self.browse_token = self.suggest_token = 0
        self.lyrics_token = self.home_token = self.local_token = 0
        self.radio_busy = self.muted = False
        self.repeat = 0  # 0 mati, 1 seluruh antrean, 2 satu lagu
        self.radio_on = bool(self.cfg["radio"])
        self.radio_seeds = set()
        self.kind = "Semua"
        self.library = Library(config.LIB)
        self.lyrics_cache = LyricsCache(config.LYRICS)
        self.local_index = LocalIndex(config.LOCAL)
        self.view = ("home", None)  # panel tengah: home, search, browse, history, favorites, local, playlist, settings
        self.search_note = ""
        self.search_draw = lambda: self.res_list.say(
            "Mau dengar apa?", "Ketik judul di kotak cari lalu tekan Enter. Link YouTube juga bisa ditempel di sana.")
        self.home_rows, self.home_at = None, 0.0
        self.local_rows, self.local_scanned = None, False
        self.shown_actions, self.nav_lists_items = [], []
        self.island, self.island_on, self.resume_at = None, False, None
        self.now_args = ("Belum ada yang diputar", "", None, False)
        self.logged = None
        self.lyrics_open, self.lyrics_key, self.lyrics_job, self.suggest_job = False, None, None, None
        self.lyrics_quiet = set()
        self.art_cache, self.art_pending, self.art_failed, self.art_tint = {}, set(), set(), {}
        self.art_vivid = {}
        self.ytm_client = None
        self.ytm_lock = threading.Lock()
        self.tray = None
        if tray.available() and os.path.exists(config.ICON_PNG):
            try:
                self.tray = tray.Tray(config.ICON_PNG, self.from_os)
            except Exception:
                log_error(traceback.format_exc())

        self.build()
        root.protocol("WM_DELETE_WINDOW", self.request_close)
        root.report_callback_exception = lambda *exc: log_error("".join(traceback.format_exception(*exc)))
        system.hook_app_events(root, reopen=self.restore_window, quit=self.close)
        self.media = media.MediaSession(self.from_os)

        self.worker = threading.Thread(target=self.mpv_loop, daemon=True)
        self.worker.start()
        for _ in range(3):
            threading.Thread(target=self.art_loop, daemon=True).start()
        self.apply_audio()
        root.after(100, self.pump)
        if startup_query:
            root.after(300, lambda: self.submit(startup_query, autoplay=True))
        else:
            root.after(300, self.restore_session)
        self.autosave_job = root.after(20000, self.autosave)
        root.bind("<Unmap>", self.window_changed, add="+")
        root.bind("<Map>", self.window_changed, add="+")
        self.bind_shortcuts()

    @property
    def queue(self):
        return self.q_list.rows

    def from_os(self, action):
        """Dipanggil dari thread lain (tombol media, tray, panel media OS): diteruskan ke thread UI."""
        self.uiq.put(("key", action))

    def save_cfg(self):
        write_json(config.CFG, self.cfg)

    # ---------- tampilan ----------
    def build(self):
        root = self.root
        root.title(TITLE)
        root.configure(bg=BG)
        left, top, right, bottom = system.work_area(root)
        room_w, room_h = right - left, bottom - top
        w, h = min(px(1240), room_w - px(40)), min(px(700), room_h - px(56))
        root.geometry("%dx%d+%d+%d" % (w, h, left + (room_w - w) // 2, top + max(0, (room_h - h - px(40)) // 2)))
        root.minsize(min(px(1040), w), min(px(560), h))
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)
        shell = tk.Frame(root, bg=BG)
        shell.grid(row=1, column=0, sticky="nsew")
        self.build_nav(shell)
        content = tk.Frame(shell, bg=BG)
        content.pack(side="left", fill="both", expand=True)
        content.columnconfigure(0, weight=1)
        content.rowconfigure(1, weight=1)
        self.build_top(content)
        body = tk.Frame(content, bg=BG)
        body.grid(row=1, column=0, sticky="nsew", padx=(px(8), px(16)))
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        self.build_center(body)
        self.build_side(body)
        self.build_bar(root)
        self.suggest = SuggestBox(root, self.pick_suggestion)
        root.bind("<Button-1>", self.click_anywhere, add="+")
        self.rebuild_nav()
        self.show_view("home")
        self.sync_queue()

    def build_nav(self, shell):
        nav = Panel(shell, BG)
        nav.configure(width=px(196))
        nav.pack_propagate(False)
        nav.pack(side="left", fill="y", padx=(px(16), 0), pady=(px(16), 0))
        # Belum ada logo: nama produk sebagai teks, sesuai aturan aset (R-23).
        tk.Label(nav, text=APP, bg=SURF, fg=FG, font=font(20, True)).pack(anchor="w", padx=px(16),
                                                                         pady=(px(16), px(10)))
        self.nav_w = px(196) - px(10) - 2 * Control.PAD
        self.nav_items = {}
        for key, glyph, label in NAV:
            item = NavItem(nav, glyph, label, lambda key=key: self.show_view(key), SURF, self.nav_w)
            item.pack()
            self.nav_items[key] = item
        self.nav_search, self.nav_fav = self.nav_items["search"], self.nav_items["favorites"]
        row = tk.Frame(nav, bg=SURF)
        row.pack(fill="x", padx=(px(16), px(6)), pady=(px(14), px(2)))
        tk.Label(row, text="Playlist", bg=SURF, fg=SILVER, font=font(13, True)).pack(side="left")
        self.new_list_btn = IconButton(row, G_ADD, self.new_playlist, SURF, size=28, glyph_px=13)
        self.new_list_btn.pack(side="right")
        self.nav_scroll = ScrollFrame(nav, SURF)
        self.nav_scroll.pack(fill="both", expand=True)
        self.nav_lists = self.nav_scroll.inner
        self.nav_settings = NavItem(nav, G_SETTINGS, "Pengaturan", lambda: self.show_view("settings"), SURF,
                                    self.nav_w)
        self.nav_settings.pack(side="bottom", pady=(px(4), px(8)), before=self.nav_scroll)

    def build_top(self, content):
        bar_top = tk.Frame(content, bg=BG)
        bar_top.grid(row=0, column=0, sticky="ew", padx=(px(5), px(13)), pady=(px(13), px(5)))
        bar_top.columnconfigure(1, weight=1)
        self.search = SearchField(bar_top, BG, self.submit, on_change=self.on_typing, on_arrow=self.suggest_arrow,
                                  on_escape=self.hide_suggest)
        self.search.grid(row=0, column=1, sticky="ew")
        self.search.entry.bind("<FocusOut>", lambda e: self.root.after(150, self.hide_if_unfocused), add="+")
        self.chips = {}
        for column, (label, _) in enumerate(KINDS, start=2):
            chip = Chip(bar_top, label, lambda name=label: self.pick_kind(name), BG)
            chip.on = label == self.kind
            chip.paint()
            chip.grid(row=0, column=column, padx=(px(8) if column == 2 else px(2), 0))
            self.chips[label] = chip

    def build_center(self, body):
        results = self.center = Panel(body, BG)
        results.grid(row=0, column=0, sticky="nsew", padx=(0, px(8)))
        head = self.center_head = tk.Frame(results, bg=SURF)
        head.pack(fill="x", padx=px(16), pady=(px(16), px(4)))
        # Yang di-pack terakhir yang terpotong bila sempit: status dikorbankan, bukan judul atau tombol.
        self.view_title = tk.Label(head, text="", bg=SURF, fg=FG, font=font(24, True))
        self.view_title.pack(side="left")
        self.status = tk.Label(head, text="", bg=SURF, fg=SILVER, font=font(14))
        self.drop_list_btn = PillButton(head, "Hapus playlist", self.delete_playlist, SURF)
        self.clear_hist_btn = PillButton(head, "Hapus riwayat", self.clear_history, SURF)
        self.status.pack(side="left", padx=px(14), pady=(px(6), 0))
        # Baris aksi: tombol yang tampil bergantung tampilan, dan turun baris sendiri bila sempit (lihat flow).
        self.actions = tk.Frame(results, bg=SURF, height=px(38))
        self.actions.pack(fill="x", padx=px(13), pady=(0, px(6)))
        self.play_all_btn = PillButton(self.actions, "Putar semua", self.play_all, SURF, solid=True)
        self.add_btn = PillButton(self.actions, "Tambah ke antrean", lambda: self.activate_results(play=False),
                                  SURF)
        self.save_btn = PillButton(self.actions, "Simpan ke playlist", self.save_menu, SURF)
        self.drop_btn = PillButton(self.actions, "Hapus lagu", self.drop_from_playlist, SURF)
        self.rescan_btn = PillButton(self.actions, "Pindai ulang", self.rescan_local, SURF)
        self.choose_btn = PillButton(self.actions, "Pilih folder", self.choose_folder, SURF)
        self.action_buttons = (self.play_all_btn, self.add_btn, self.save_btn, self.drop_btn, self.rescan_btn,
                               self.choose_btn)
        self.actions.bind("<Configure>", lambda e: self.flow())
        self.res_list = TrackList(results, SURF, self, lambda: self.activate_results(play=True), on_menu=self.row_menu)
        self.res_list.pack(fill="both", expand=True, padx=(px(8), px(2)), pady=(0, px(10)))
        self.settings_view = SettingsView(results, self)
        self.player_view = PlayerView(results, self)

    def build_side(self, body):
        side = Panel(body, BG)
        side.configure(width=px(388))
        side.pack_propagate(False)
        side.grid(row=0, column=1, sticky="ns")
        self.now_card = NowCard(side, SURF, self, on_open=self.open_player, on_artist=self.open_artist)
        self.now_card.pack(fill="x", padx=px(8), pady=(px(8), 0))
        self.now_art, self.now_side = self.now_card.art, self.now_card.info
        lower = tk.Frame(side, bg=SURF)
        lower.pack(fill="both", expand=True)

        self.queue_box = tk.Frame(lower, bg=SURF)
        head = tk.Frame(self.queue_box, bg=SURF)
        head.pack(fill="x", padx=px(16), pady=(px(12), px(8)))
        tk.Label(head, text="Antrean", bg=SURF, fg=FG, font=font(18, True)).pack(side="left")
        self.count = tk.Label(head, text="", bg=SURF, fg=SILVER, font=font(13))
        self.clear_btn = PillButton(head, "Kosongkan", self.clear_queue, SURF)
        self.remove_btn = PillButton(head, "Hapus", self.remove_selected, SURF)
        self.q_list = TrackList(self.queue_box, SURF, self, self.play_selected, self.remove_selected,
                                on_menu=self.row_menu, on_move=self.move_queue)
        self.remove_btn.pack(side="right")
        self.clear_btn.pack(side="right", padx=(0, px(2)))
        self.count.pack(side="left", padx=px(8), pady=(px(4), 0))
        foot = tk.Frame(self.queue_box, bg=SURF)
        foot.pack(side="bottom", fill="x", padx=px(13), pady=(px(4), px(12)))
        self.radio = Toggle(foot, "Lanjut otomatis dengan lagu sejenis", self.radio_on, self.set_radio, SURF)
        self.q_list.pack(fill="both", expand=True, padx=(px(8), px(2)))
        self.radio.pack(side="left")
        self.queue_box.pack(fill="both", expand=True)

        self.lyrics_box = tk.Frame(lower, bg=SURF)
        head = tk.Frame(self.lyrics_box, bg=SURF)
        head.pack(fill="x", padx=px(16), pady=(px(12), px(8)))
        tk.Label(head, text="Lirik", bg=SURF, fg=FG, font=font(18, True)).pack(side="left")
        self.lyrics_source = tk.Label(head, text="", bg=SURF, fg=SILVER, font=font(13))
        self.lyrics_retry = PillButton(head, "Coba lagi", lambda: self.load_lyrics(force=True), SURF)
        self.lyrics_big_btn = PillButton(head, "Perbesar", self.open_player, SURF)
        self.lyrics_big_btn.pack(side="right")
        self.lyrics_source.pack(side="left", padx=px(8), pady=(px(4), 0))
        self.lyrics_view = LyricsView(self.lyrics_box, SURF, self.seek_to)
        self.lyrics_view.pack(fill="both", expand=True, padx=(px(8), px(2)), pady=(0, px(10)))

    def build_bar(self, root):
        bar = tk.Frame(root, bg=BG)
        bar.grid(row=2, column=0, sticky="ew", padx=px(16), pady=(px(10), px(12)))
        bar.columnconfigure(0, weight=3, uniform="side")  # sisi kiri dan kanan sama lebar: kontrol tetap di tengah
        bar.columnconfigure(1, weight=4)
        bar.columnconfigure(2, weight=3, uniform="side")
        self.now = NowInfo(bar, BG, self, on_open=self.open_player, on_artist=self.open_artist)
        self.now.grid(row=0, column=0, sticky="ew")
        mid = tk.Frame(bar, bg=BG)
        mid.grid(row=0, column=1, sticky="ew")
        mid.columnconfigure(1, weight=1)
        keys = tk.Frame(mid, bg=BG)
        keys.grid(row=0, column=0, columnspan=3)
        self.shuffle_btn = IconButton(keys, G_SHUFFLE, self.shuffle, BG, glyph_px=15)
        self.shuffle_btn.pack(side="left", padx=px(6))
        self.prev_btn = IconButton(keys, G_PREV, lambda: self.send("playlist-prev"), BG)
        self.prev_btn.pack(side="left", padx=px(6))
        self.play_btn = IconButton(keys, G_PLAY, self.toggle, BG, size=40, primary=True)
        self.play_btn.pack(side="left", padx=px(6))
        self.next_btn = IconButton(keys, G_NEXT, lambda: self.send("playlist-next"), BG)
        self.next_btn.pack(side="left", padx=px(6))
        self.repeat_btn = IconButton(keys, G_REPEAT, self.cycle_repeat, BG, glyph_px=15)
        self.repeat_btn.pack(side="left", padx=px(6))
        self.t_now = tk.Label(mid, text="-:--", bg=BG, fg=SILVER, font=font(12), width=7, anchor="e")
        self.t_now.grid(row=1, column=0)
        self.seek = Slider(mid, BG, on_release=self.seek_to)
        self.seek.grid(row=1, column=1, sticky="ew")
        self.t_end = tk.Label(mid, text="-:--", bg=BG, fg=SILVER, font=font(12), width=7, anchor="w")
        self.t_end.grid(row=1, column=2)
        right_box = tk.Frame(bar, bg=BG)
        right_box.grid(row=0, column=2, sticky="e")
        self.lyrics_btn = IconButton(right_box, G_LYRICS, self.toggle_lyrics, BG, size=32, glyph_px=15)
        self.lyrics_btn.pack(side="left", padx=(0, px(4)))
        self.mute_btn = IconButton(right_box, G_VOL, self.toggle_mute, BG, size=32)
        self.mute_btn.pack(side="left")
        self.vol = Slider(right_box, BG, length=px(104),
                          on_move=lambda v: self.send("set_property", "volume", int(v)))
        self.vol.span(100)
        self.vol.set(self.cfg["volume"])
        self.vol.pack(side="left")

    # ---------- navigasi dan tampilan ----------
    def rebuild_nav(self):
        for child in self.nav_lists.winfo_children():
            child.destroy()
        self.nav_lists_items = []
        for index, playlist in enumerate(self.library.playlists):
            item = NavItem(self.nav_lists, G_LIST, playlist["name"],
                           lambda index=index: self.show_view("playlist", index), SURF, self.nav_w)
            item.pack()
            self.nav_scroll.watch(item)
            self.nav_lists_items.append(item)
        if not self.library.playlists:
            tk.Label(self.nav_lists, text="Belum ada playlist. Tekan + untuk membuat.", bg=SURF, fg=SILVER,
                     font=font(13), wraplength=px(160), justify="left").pack(anchor="w", padx=px(16), pady=px(4))
        self.mark_nav()

    def mark_nav(self):
        kind, arg = self.view
        wanted = [(self.nav_items[key], kind == key or (key == "search" and kind == "browse"))
                  for key, _, _ in NAV]
        wanted.append((self.nav_settings, kind == "settings"))
        wanted += [(item, kind == "playlist" and arg == i) for i, item in enumerate(self.nav_lists_items)]
        for item, active in wanted:
            if item.active != active:
                item.active = active
                item.paint()

    def actions_for(self, kind):
        if kind in ("home", "search"):
            return [self.add_btn, self.save_btn]
        if kind in ("browse", "history", "favorites"):
            return [self.play_all_btn, self.add_btn, self.save_btn]
        if kind == "playlist":
            return [self.play_all_btn, self.add_btn, self.drop_btn]
        if kind == "local":
            if not self.cfg["local_dir"]:
                return [self.choose_btn]
            return [self.play_all_btn, self.add_btn, self.save_btn, self.rescan_btn, self.choose_btn]
        return []

    def show_view(self, kind, arg=None):
        """Ganti isi panel tengah. kind: home, search, browse (arg = judul koleksi YouTube), history,
        favorites, local, playlist (arg = indeks playlist sendiri), atau settings."""
        if kind == "playlist" and not (isinstance(arg, int) and 0 <= arg < len(self.library.playlists)):
            kind, arg = "search", None
        self.view = (kind, arg)
        self.hide_suggest()
        pages = {"settings": self.settings_view, "player": self.player_view}
        for name, page in pages.items():
            if name != kind:
                page.pack_forget()
        if kind in pages:
            self.actions.pack_forget()
            self.res_list.pack_forget()
            pages[kind].pack(fill="both", expand=True, padx=(px(8), px(2)), pady=(0, px(10)))
            if kind == "settings":
                self.settings_view.sync()
            else:
                self.player_view.show(self.now_track(), force=True)  # warna bisa berubah dari Pengaturan
                self.load_lyrics()
                self.lyrics_tick()
        elif not self.res_list.winfo_manager():
            self.actions.pack(fill="x", padx=px(13), pady=(0, px(6)))
            self.res_list.pack(fill="both", expand=True, padx=(px(8), px(2)), pady=(0, px(10)))
        self.paint_center(self.player_view.color if kind == "player" else SURF)
        if kind == "browse":
            title = arg
        elif kind == "playlist":
            title = self.library.playlists[arg]["name"]
        else:
            title = TITLES[kind]
        self.view_title.configure(text=fit(title, font(24, True), px(300)))
        self.say("")
        self.draw_view(kind, arg)
        for button in self.action_buttons:
            button.place_forget()
        self.shown_actions = self.actions_for(kind)
        for button, wanted in ((self.drop_list_btn, kind == "playlist"), (self.clear_hist_btn, kind == "history")):
            if wanted:
                button.pack(side="right")
            else:
                button.pack_forget()
        self.flow()
        self.mark_nav()

    def paint_center(self, fill):
        """Warnai panel tengah: warna cover di halaman Sedang diputar, #181818 di tampilan lain."""
        if self.center.fill != fill:
            self.center.set_fill(fill)
            for widget in (self.center_head, self.view_title, self.status):
                widget.configure(bg=fill)
            self.status.configure(fg=SILVER if fill == SURF else FG)

    def flow(self):
        """Susun tombol aksi dari kiri; yang tidak muat turun ke baris berikutnya."""
        width, x, y, row_h = self.actions.winfo_width(), 0, 0, px(38)
        for button in self.shown_actions:
            bw, row_h = button.winfo_reqwidth(), button.winfo_reqheight()
            if x and x + bw > width:
                x, y = 0, y + row_h + px(2)
            button.place(x=x, y=y)
            x += bw + px(2)
        self.actions.configure(height=(y + row_h) if self.shown_actions else 1)

    def say(self, text):
        self.status.configure(text=text)

    def sync_queue(self):
        total = len(self.queue)
        self.count.configure(text="%d lagu" % total if total else "")
        if not total:
            self.q_list.say("Antrean kosong", "Klik dua kali lagu di hasil pencarian untuk memutarnya.")

    def click_anywhere(self, event):
        if self.suggest.shown and event.widget not in (self.suggest, self.search, self.search.entry):
            self.hide_suggest()

    def hide_if_unfocused(self):
        if self.root.focus_get() is not self.search.entry:
            self.hide_suggest()

    def show_shortcuts(self):
        return show_shortcuts(self.root)

    # ---------- jendela ----------
    def window_changed(self, event):
        """Jendela di-minimize atau disembunyikan ke tray: tampilkan pulau mini. Dipulihkan: sembunyikan lagi."""
        if event.widget is not self.root or not self.alive:
            return
        hidden = self.root.state() in ("iconic", "withdrawn")
        if hidden and self.queue and self.cfg["island"]:
            if self.island is None:
                self.island = Island(self)
            self.island_on = True
            self.island.state_args, self.island.track = self.now_args, self.now_args[2]
            self.island.appear()
        elif self.island is not None and self.island_on:
            self.island_on = False
            self.island.vanish()

    def set_island(self, on):
        self.cfg["island"] = bool(on)
        self.save_cfg()

    def restore_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def request_close(self):
        """Tombol tutup: sembunyikan ke tray bila diaktifkan, selain itu keluar."""
        if self.tray and self.cfg["tray_close"]:
            self.hide_suggest()
            self.root.withdraw()
            if not self.cfg["tray_told"]:
                self.tray.notify("ClixMax tetap memutar musik di tray. Klik kanan ikonnya lalu pilih Keluar untuk "
                                 "menutup.")
                self.cfg["tray_told"] = True
                self.save_cfg()
        else:
            self.close()

    def close(self):
        if not self.alive:
            return
        self.save_session()
        self.cfg.update(volume=int(self.vol.value), radio=self.radio_on)
        self.save_cfg()
        self.alive = False
        for job in (getattr(self, "pump_job", None), getattr(self, "autosave_job", None), self.lyrics_job,
                    self.suggest_job):
            if job:
                try:
                    self.root.after_cancel(job)
                except Exception:
                    pass
        self.worker.join(3)
        self.media.close()
        if self.tray:
            self.tray.stop()
        self.root.destroy()

    # ---------- keyboard dan roda tetikus ----------
    def bind_shortcuts(self):
        mod = system.SHORTCUT
        actions = {
            "k": self.focus_search, "l": self.focus_search, "m": self.toggle_mute, "s": self.shuffle,
            "r": self.cycle_repeat, "j": self.toggle_lyrics, "h": self.show_shortcuts,
            "p": lambda: self.show_view("player"),
        }
        for letter, action in actions.items():
            for key in (letter, letter.upper()):
                self.root.bind("<%s-%s>" % (mod, key), lambda e, action=action: self.shortcut(action))
        moves = {"Right": lambda: self.send("playlist-next"), "Left": lambda: self.send("playlist-prev"),
                 "Up": lambda: self.nudge_volume(5), "Down": lambda: self.nudge_volume(-5)}
        for key, action in moves.items():
            self.root.bind("<%s-%s>" % (mod, key), lambda e, action=action: self.shortcut(action, typing_ok=False))
        for number, (key, _, _) in enumerate(NAV, start=1):
            self.root.bind("<%s-Key-%d>" % (mod, number), lambda e, key=key: self.shortcut(lambda: self.show_view(key)))
        self.root.bind("<%s-comma>" % mod, lambda e: self.shortcut(lambda: self.show_view("settings")))
        self.root.bind("<space>", lambda e: self.shortcut(self.toggle, typing_ok=False))
        self.root.bind_all("<MouseWheel>", self.route_wheel)
        if system.LINUX:  # roda tetikus di X11 datang sebagai tombol 4/5
            self.root.bind_all("<Button-4>", lambda e: self.route_wheel(e, -1))
            self.root.bind_all("<Button-5>", lambda e: self.route_wheel(e, 1))

    def shortcut(self, action, typing_ok=True):
        """Jalankan pintasan; yang bentrok dengan mengetik (Spasi, Ctrl+panah) dilewati di kotak teks."""
        if not typing_ok and isinstance(self.root.focus_get(), tk.Entry):
            return None
        action()
        return "break"

    def focus_search(self):
        self.search.entry.focus_set()
        self.search.entry.select_range(0, "end")

    def route_wheel(self, event, direction=None):
        """Roda tetikus menggulir daftar yang ada di bawah kursor, bukan yang sedang difokus."""
        if direction is None:
            direction = -1 if event.delta > 0 else 1
        widget = event.widget.winfo_containing(event.x_root, event.y_root) if hasattr(event.widget,
                                                                                       "winfo_containing") else None
        while widget is not None and not hasattr(widget, "scroll_by"):
            widget = widget.master
        if widget is not None:
            widget.scroll_by(direction)
            return "break"
        return None

    # ---------- gambar ----------
    def art(self, track, w, h=None, wide=False):
        """Gambar yang sudah siap, atau None. Yang belum ada diunduh di latar; semua tampilan
        disegarkan begitu selesai (lihat on_art)."""
        if not track:
            return None
        h = h or w
        url = artwork.art_url(track, w, h, wide)
        if not url:
            return None
        key = (url, w, h)
        image = self.art_cache.get(key)
        if image is None and key not in self.art_pending and key not in self.art_failed:
            self.art_pending.add(key)
            self.artq.put(key)
        return image

    def art_loop(self):
        while True:
            key = self.artq.get()
            data = None
            try:
                data = artwork.fetch(*key)
            except Exception:
                pass
            self.uiq.put(("art", key, data))

    def on_art(self, key, data):
        self.art_pending.discard(key)
        image = None
        if data:
            try:
                image = tk.PhotoImage(data=data[0])
            except tk.TclError:
                image = None
        if image is None:
            self.art_failed.add(key)
            return
        if len(self.art_cache) > 500:
            self.art_cache.pop(next(iter(self.art_cache)))
        self.art_cache[key] = image
        self.art_tint[key[0]], self.art_vivid[key[0]] = data[1], data[2]
        self.res_list.refresh_art()
        self.q_list.refresh_art()
        self.now.show(*self.now.args)
        self.now_card.load(self.now_args[2])
        self.refresh_tint()
        if self.view[0] == "player":
            self.player_view.paint()
        if self.island_on:
            self.island.show_state(*self.now_args)

    def open_player(self):
        """Ke halaman Sedang diputar (dari klik gambar, judul, atau lirik; juga dari pulau mini)."""
        if self.root.state() != "normal":
            self.restore_window()
        self.show_view("player")

    def set_island_style(self, style):
        self.cfg["island_style"] = style
        self.save_cfg()
        self.settings_view.sync()
        if self.island is not None:
            self.island.apply_style()

    def set_word_lyrics(self, on):
        self.cfg["word_lyrics"] = bool(on)
        self.save_cfg()
        self.settings_view.sync()
        if on and self.lyrics_visible():
            self.load_lyrics(force=True)  # cari ulang supaya lagu ini dapat waktu per kata bila ada

    def set_island_tuck(self, on):
        self.cfg["island_tuck"] = bool(on)
        self.save_cfg()
        self.settings_view.sync()
        if not on and self.island is not None and self.island.mode == "tuck":
            self.island.set_mode("compact")

    def set_island_alpha(self, value):
        value = round(min(0.6, max(0.0, float(value))), 2)
        if value != self.cfg["island_alpha"]:
            self.cfg["island_alpha"] = value
            self.save_cfg()
            if self.island is not None:
                self.island.apply_style()

    def set_tint(self, on):
        self.cfg["tint"] = bool(on)
        self.refresh_tint()
        self.save_cfg()

    def set_tray_close(self, on):
        self.cfg["tray_close"] = bool(on)
        self.save_cfg()


def create(startup_query=""):
    """Bangun jendela dan aplikasinya (dipisah dari main supaya bisa diuji)."""
    system.prepare_process()
    if config.OLD_CFG and not os.path.exists(config.CFG) and os.path.exists(config.OLD_CFG):
        os.makedirs(os.path.dirname(config.CFG), exist_ok=True)
        shutil.copyfile(config.OLD_CFG, config.CFG)  # bawa setelan dari nama lama
    cfg = read_json(config.CFG, {})
    root = tk.Tk()
    root.withdraw()
    UI.scale = system.ui_scale(root)
    UI.family = pick_family(root)
    try:
        if not (os.path.exists(config.ICON) and os.path.exists(config.ICON_PNG)):
            artwork.make_icon(config.ICON, config.ICON_PNG)
        system.set_window_icon(root, config.ICON, config.ICON_PNG)
    except Exception:
        log_error(traceback.format_exc())
    app = App(root, cfg, startup_query)
    root.update_idletasks()
    system.dark_titlebar(root)
    root.deiconify()
    return root, app


def write_tone(path, seconds):
    """Berkas WAV berisi nada 440 Hz, untuk menguji pemutaran tanpa internet."""
    import math
    import struct
    import wave
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(b"".join(struct.pack("<h", int(3000 * math.sin(2 * math.pi * 440 * i / 22050)))
                               for i in range(22050 * seconds)))


def selftest(report):
    """Uji diri untuk versi build: jendela terbangun, mpv menjawab, yt-dlp ditemukan, lalu satu lagu hasil
    pencarian YouTube Music benar-benar diputar (tanpa suara). Memakai data dan pipe sementara supaya tidak
    menyentuh setelan pengguna. Hasil ditulis ke berkas report; kode keluar 0 bila lolos."""
    import tempfile
    from . import music, player
    work = tempfile.mkdtemp(prefix="clixmax-selftest-")
    player.Mpv.extra = ["--ao=null"]  # mesin build tidak punya kartu suara
    config.PIPE = system.ipc_path("clixmax-selftest")
    for name in ("CFG", "LOG", "LIB", "SESSION", "LYRICS", "LOCAL"):
        setattr(config, name, os.path.join(work, os.path.basename(getattr(config, name))))
    config.OLD_CFG = None
    lines, ok = [], False
    try:
        root, app = create("")
        end = time.time() + 40
        while time.time() < end and app.state is None:
            root.update()
            time.sleep(0.05)
        mpv, ytdlp = player.find_exe("mpv"), player.find_exe("yt-dlp")
        lines += ["jendela: %s" % root.title(), "mpv: %s (%s)" % ("menjawab" if app.state else "tidak menjawab", mpv),
                  "yt-dlp: %s" % ytdlp, "tray: %s" % ("ada" if app.tray else "tidak ada")]
        ok = app.state is not None and bool(ytdlp)

        def plays(track, seconds):
            app.clear_queue()
            app.add([track], play=True)
            end = time.time() + seconds
            while time.time() < end and not ((app.state or {}).get("t") or 0) > 2:
                root.update()
                time.sleep(0.05)
            return ((app.state or {}).get("t") or 0) > 2

        if ok:  # berkas lokal: membuktikan mpv dan jalur pemutaran tanpa bergantung pada YouTube
            tone = os.path.join(work, "nada.wav")
            write_tone(tone, 6)
            local = plays({"title": "Nada uji", "artist": "", "url": tone, "kind": "local", "id": "", "dur": "0:06",
                           "art": None}, 20)
            lines.append("memutar berkas lokal: %s" % ("ya" if local else "tidak"))
            ok = local
        if ok:
            rows = [row for row in music.search(app.ytm(), "lofi hip hop", "songs") if "url" in row]
            lines.append("pencarian YouTube Music: %d lagu" % len(rows))
            streamed = bool(rows) and plays(dict(rows[0]), 60)
            lines.append("memutar dari YouTube: %s" % ("ya, %s" % rows[0]["title"] if streamed else "tidak"))
            if rows and not streamed:
                # Tampilkan alasan yt-dlp apa adanya; YouTube sering menolak alamat IP pusat data (mesin build).
                run = subprocess.run([ytdlp, "--simulate", "--no-warnings", "-f", "bestaudio/best", rows[0]["url"]],
                                     capture_output=True, timeout=120, creationflags=system.HIDDEN)
                reason = (run.stderr or b"").decode("utf-8", "replace").strip().splitlines()[-1:] or ["(kosong)"]
                lines.append("yt-dlp: %s" % reason[0])
                blocked = any(mark in reason[0] for mark in ("Sign in to confirm", "not a bot"))
                lines.append("catatan: YouTube menolak alamat IP mesin ini (bukan galat ClixMax)" if blocked else
                             "catatan: pemutaran YouTube gagal karena sebab lain")
                ok = blocked and bool(os.environ.get("CI"))  # hanya dimaafkan di mesin build, tidak di komputer pengguna
            else:
                ok = streamed
        app.close()
    except Exception:
        lines.append(traceback.format_exc())
    lines.append("LOLOS" if ok else "GAGAL")
    with open(report, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    sys.exit(0 if ok else 1)


def main():
    for arg in sys.argv[1:]:
        if arg.startswith("--selftest="):
            selftest(arg.split("=", 1)[1])
    if not system.single_instance("clixmax"):
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo(APP, "ClixMax sudah berjalan.")
        root.destroy()
        return
    try:
        root, _ = create(" ".join(sys.argv[1:]).strip())
        root.mainloop()
    except Exception:
        log_error(traceback.format_exc())
        raise
