"""Bagian App untuk menjelajah: cari dan saran, beranda, koleksi, riwayat, musik lokal,
favorit, playlist sendiri, dan menu klik kanan."""
import datetime
import re
import threading
import time
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox

from . import music
from .config import APP, KINDS, log_error
from .theme import FG, RAISED, RED, SELECT, font
from .widgets import ask_text

DAYS = ("Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu")
MONTHS = ("Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober",
          "November", "Desember")


def day_label(day):
    try:
        date = datetime.date.fromisoformat(day)
    except ValueError:
        return "Sebelumnya"
    today = datetime.date.today()
    if date == today:
        return "Hari ini"
    if date == today - datetime.timedelta(days=1):
        return "Kemarin"
    return "%s, %d %s %d" % (DAYS[date.weekday()], date.day, MONTHS[date.month - 1], date.year)


class Browsing:
    # ---------- latar ----------
    def ytm(self):
        with self.ytm_lock:
            if self.ytm_client is None:
                from ytmusicapi import YTMusic
                self.ytm_client = YTMusic()
            return self.ytm_client

    def background(self, work, on_error):
        """Jalankan work() di thread latar; hasilnya (atau on_error(exc)) dikirim ke antrean UI."""
        def run():
            try:
                self.uiq.put(work())
            except Exception as exc:
                log_error(traceback.format_exc())
                self.uiq.put(on_error(exc))

        threading.Thread(target=run, daemon=True).start()

    def draw_view(self, kind, arg):
        if kind == "search":
            self.search_draw()
            self.say(self.search_note)
        elif kind == "home":
            self.draw_home()
        elif kind == "history":
            self.draw_history()
        elif kind == "local":
            self.draw_local()
        elif kind in ("favorites", "playlist"):
            mine = self.library.playlists[arg] if kind == "playlist" else None
            source = mine["tracks"] if mine else self.library.favorites
            if source:
                self.res_list.fill([dict(t) for t in source])
                self.say("%d lagu" % len(source))
            elif mine:
                self.res_list.say("Playlist ini masih kosong",
                                  "Pilih lagu di hasil pencarian, lalu tekan Simpan ke playlist.")
            else:
                self.res_list.say("Belum ada favorit", "Tekan ikon hati di samping lagu untuk menyimpannya di sini.")

    # ---------- pencarian dan saran ----------
    def pick_kind(self, name):
        self.kind = name
        for label, chip in self.chips.items():
            chip.on = label == name
            chip.paint()
        if self.search.text() and not re.match(r"https?://", self.search.text()):
            self.submit()

    def submit(self, text=None, autoplay=False):
        if text is None:
            picked = self.suggest.current()
            if picked:
                self.search.put(picked)
            text = picked or self.search.text()
        self.hide_suggest()
        text = text.strip()
        if not text:
            self.search.entry.focus_set()
            return
        if re.match(r"https?://", text):
            self.open_url(text)
            return
        self.search_token += 1
        token, kind = self.search_token, dict(KINDS)[self.kind]
        self.search_draw, self.search_note = self.res_list.wait, "Mencari…"
        self.show_view("search")

        def work():
            rows = music.search(self.ytm(), text, kind)
            first = next((row for row in rows if "url" in row), None)
            if autoplay and first:
                self.uiq.put(("add", [dict(first)], True, None))
            return "results", token, rows, "%d hasil" % len(rows) if rows else ""

        self.background(work, lambda exc: ("failed", token, str(exc)))

    def on_typing(self, text):
        if self.suggest_job:
            self.root.after_cancel(self.suggest_job)
            self.suggest_job = None
        if not text or re.match(r"https?://", text):
            self.suggest.hide()
            return
        self.suggest_job = self.root.after(250, lambda: self.fetch_suggestions(text))

    def fetch_suggestions(self, text):
        self.suggest_job = None
        self.suggest_token += 1
        token = self.suggest_token
        self.background(lambda: ("suggest", token, text, self.ytm().get_search_suggestions(text)[:7]),
                        lambda exc: ("suggest", token, text, []))

    def on_suggest(self, token, text, items):
        items = [item for item in items if isinstance(item, str)]
        if (token != self.suggest_token or self.search.text() != text
                or self.root.focus_get() is not self.search.entry):
            return
        if items:
            self.suggest.show(items, self.search)
        else:
            self.suggest.hide()

    def suggest_arrow(self, delta):
        return self.suggest.move(delta)

    def hide_suggest(self):
        if self.suggest_job:
            self.root.after_cancel(self.suggest_job)
            self.suggest_job = None
        self.suggest.hide()

    def pick_suggestion(self, text):
        self.search.put(text)
        self.submit(text)

    def on_results(self, token, tracks, note):
        if token != self.search_token:
            return
        if tracks:
            self.search_draw = lambda: self.res_list.fill(tracks)
        else:
            self.search_draw = lambda: self.res_list.say("Tidak ada hasil",
                                                         "Coba kata kunci lain, atau ganti filter di kanan atas.")
        self.search_note = note
        if self.view[0] == "search":  # kalau pengguna sudah pindah tampilan, hasilnya menunggu di sana
            self.show_view("search")

    def on_failed(self, token, reason):
        if token != self.search_token:
            return
        self.search_draw = lambda: self.res_list.say(
            "Pencarian gagal", "%s\nPeriksa koneksi internet, lalu tekan Enter lagi di kotak cari." % reason, RED)
        self.search_note = ""
        if self.view[0] == "search":
            self.show_view("search")

    # ---------- koleksi YouTube Music dan link ----------
    def activate_results(self, play):
        picked = [self.res_list.rows[i] for i in self.res_list.selection()]
        if not picked:
            self.say("Pilih lagu di daftar dulu")
            return
        songs = [dict(t) for t in picked if "url" in t]
        self.add(songs, play)
        if songs and not play:
            self.say("%d lagu ditambahkan ke antrean" % len(songs))
        opens = [t for t in picked if "open" in t]
        if opens and not songs:
            self.open_collection(opens[0])

    def open_collection(self, row):
        """Buka isi artis, album, atau playlist YouTube Music di panel tengah."""
        kind, ident = row["open"]
        self.browse_token += 1
        token = self.browse_token
        self.show_view("browse", row["title"])
        self.res_list.wait()
        self.say("Membuka…")
        self.background(lambda: ("browse", token, music.collection(self.ytm(), kind, ident), ""),
                        lambda exc: ("browse", token, [], "%s\nPeriksa koneksi internet, lalu coba buka lagi." % exc))

    def on_browse(self, token, tracks, failure):
        if token != self.browse_token or self.view[0] != "browse":
            return
        if failure:
            self.res_list.say("Gagal dibuka", failure, RED)
        elif tracks:
            self.res_list.fill(tracks)
        else:
            self.res_list.say("Tidak ada lagu di sini", "Kembali ke Cari di menu kiri untuk mencari yang lain.")
        self.say("%d lagu" % len(tracks) if tracks else "")

    def open_url(self, url):
        track = music.single_link(url)
        if track:
            self.add([track], play=True)
            self.say("Link ditambahkan ke antrean")
            return
        self.say("Membaca link…")

        def work():
            tracks = music.read_link(url)
            return "add", tracks, True, "%d lagu dari link" % len(tracks)

        self.background(work, lambda exc: ("say", "Link gagal dibaca: %s" % exc))

    def on_add(self, tracks, play, note):
        self.add(tracks, play)
        if note:
            self.say(note)

    def on_say(self, text):
        self.say(text)

    # ---------- beranda ----------
    def draw_home(self):
        if self.home_rows:
            self.res_list.fill([dict(row) for row in self.home_rows])
        else:
            self.res_list.wait()
        if self.home_rows is None or time.time() - self.home_at > 1800:
            self.load_home()

    def load_home(self):
        self.home_token += 1
        token, self.home_at = self.home_token, time.time()
        self.background(lambda: ("home", token, music.home(self.ytm()), ""), lambda exc: ("home", token, None, str(exc)))

    def on_home(self, token, rows, failure):
        if token != self.home_token:
            return
        if rows is not None:
            self.home_rows = rows
        if self.view[0] != "home":
            return
        if failure and not self.home_rows:
            self.home_at = 0
            self.res_list.say("Beranda gagal dimuat", "%s\nPeriksa koneksi internet, lalu buka Beranda lagi." % failure,
                              RED)
        elif rows:
            self.res_list.fill([dict(row) for row in rows])
        elif rows is not None:
            self.res_list.say("Beranda kosong", "YouTube Music belum memberi rekomendasi. Coba cari lagu dulu.")

    # ---------- riwayat ----------
    def draw_history(self):
        rows, last = [], None
        for entry in self.library.history:
            day = entry["at"][:10]
            if day != last:
                rows.append({"header": day_label(day)})
                last = day
            rows.append(dict(entry, tag=entry["at"][11:16]))
        if rows:
            self.res_list.fill(rows)
            self.say("%d lagu" % len(self.library.history))
        else:
            self.res_list.say("Belum ada riwayat", "Lagu yang kamu putar akan tercatat di sini.")
            self.say("")

    def clear_history(self):
        if not self.library.history:
            return
        if messagebox.askyesno(APP, "Hapus seluruh riwayat putar?\n\nTindakan ini tidak bisa dibatalkan. Favorit "
                                    "dan playlist tidak ikut terhapus."):
            self.library.clear_history()
            self.show_view("history")

    # ---------- musik lokal ----------
    def draw_local(self):
        if not self.cfg["local_dir"]:
            self.res_list.say("Belum ada folder musik", "Tekan Pilih folder, lalu pilih folder berisi lagu "
                                                        "(MP3, FLAC, M4A, OGG, OPUS, WAV).")
            return
        if self.local_rows is not None:
            self.fill_local()
        else:
            self.res_list.wait()
        if not self.local_scanned:
            self.scan_local()

    def fill_local(self):
        if self.local_rows:
            self.res_list.fill([dict(t) for t in self.local_rows])
            self.say("%d lagu" % len(self.local_rows))
        else:
            self.res_list.say("Tidak ada lagu di folder ini", "ClixMax membaca MP3, FLAC, M4A, OGG, OPUS, dan WAV, "
                                                              "termasuk di dalam subfolder.")
            self.say("")

    def scan_local(self):
        self.local_scanned = True
        self.local_token += 1
        token, folder = self.local_token, self.cfg["local_dir"]
        self.say("Memindai folder…")
        self.background(lambda: ("local", token, self.local_index.scan(folder), ""),
                        lambda exc: ("local", token, None, str(exc)))

    def on_local(self, token, tracks, failure):
        if token != self.local_token:
            return
        if tracks is not None:
            self.local_rows = tracks
        if self.view[0] != "local":
            return
        if failure:
            self.res_list.say("Folder gagal dibaca", "%s\nPeriksa foldernya masih ada, lalu tekan Pindai ulang." % failure,
                              RED)
            self.say("")
        else:
            self.fill_local()

    def choose_folder(self):
        folder = filedialog.askdirectory(parent=self.root, title="Pilih folder musik", mustexist=True)
        if not folder:
            return
        self.cfg["local_dir"] = folder
        self.save_cfg()
        self.local_rows, self.local_scanned = None, False
        self.settings_view.sync()
        self.show_view("local")

    def rescan_local(self):
        self.local_scanned = False
        if self.view[0] == "local":
            self.draw_local()

    # ---------- favorit dan playlist ----------
    def toggle_fav(self, track):
        self.library.toggle_fav(track)
        self.after_fav_change()

    def set_fav(self, tracks, liked):
        for track in tracks:
            if self.library.is_fav(track) != liked:
                self.library.toggle_fav(track)
        self.after_fav_change()
        self.say("%d lagu %s" % (len(tracks), "ditambahkan ke Favorit" if liked else "dihapus dari Favorit"))

    def after_fav_change(self):
        if self.view[0] == "favorites":
            self.show_view("favorites")
        else:
            self.res_list.repaint()
        self.q_list.repaint()

    def selected_tracks(self, lst=None):
        lst = lst or self.res_list
        return [lst.rows[i] for i in lst.selection() if "url" in lst.rows[i]]

    def new_playlist(self):
        name = ask_text(self.root, "Playlist baru", "Nama playlist")
        if not name:
            return None
        index = self.library.create(name)
        self.rebuild_nav()
        return index

    def menu(self):
        if getattr(self, "open_menu", None) is not None:
            self.open_menu.destroy()
        self.open_menu = tk.Menu(self.root, tearoff=0, bg=RAISED, fg=FG, activebackground=SELECT,
                                 activeforeground=FG, bd=0, font=font(14))
        return self.open_menu

    def build_save_menu(self, tracks=None, parent=None):
        menu = tk.Menu(parent, tearoff=0, bg=RAISED, fg=FG, activebackground=SELECT, activeforeground=FG, bd=0,
                       font=font(14)) if parent else self.menu()
        for index, playlist in enumerate(self.library.playlists):
            menu.add_command(label=playlist["name"], command=lambda index=index: self.save_to(index, tracks))
        if self.library.playlists:
            menu.add_separator()
        menu.add_command(label="Playlist baru…", command=lambda: self.save_to_new(tracks))
        return menu

    def save_menu(self):
        if not self.selected_tracks():
            self.say("Pilih lagu di daftar dulu")
            return
        button = self.save_btn
        self.build_save_menu().tk_popup(button.winfo_rootx(), button.winfo_rooty() + button.winfo_height())

    def save_to(self, index, tracks=None):
        added = self.library.add_to(index, tracks if tracks is not None else self.selected_tracks())
        name = self.library.playlists[index]["name"]
        self.say("%d lagu disimpan ke %s" % (added, name) if added else "Lagu itu sudah ada di %s" % name)

    def save_to_new(self, tracks=None):
        tracks = list(tracks) if tracks is not None else list(self.selected_tracks())
        index = self.new_playlist()
        if index is not None:
            self.save_to(index, tracks)

    def drop_from_playlist(self):
        kind, index = self.view
        if kind != "playlist":
            return
        chosen = self.res_list.selection()
        if not chosen:
            self.say("Pilih lagu di daftar dulu")
            return
        self.library.drop(index, chosen)
        self.show_view("playlist", index)

    def delete_playlist(self):
        kind, index = self.view
        if kind != "playlist":
            return
        name = self.library.playlists[index]["name"]
        if not messagebox.askyesno(APP, "Hapus playlist %s?\n\nLagu di dalamnya tidak ikut terhapus dari favorit "
                                        "atau antrean." % name):
            return
        self.library.delete(index)
        self.rebuild_nav()
        self.show_view("search")

    def play_all(self):
        tracks = [dict(t) for t in self.res_list.rows if "url" in t]
        if not tracks:
            self.say("Belum ada lagu untuk diputar")
            return
        self.clear_queue()
        self.add(tracks, play=True)

    # ---------- menu klik kanan ----------
    def row_menu(self, lst, x, y):
        menu = self.build_row_menu(lst)
        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def build_row_menu(self, lst):
        rows = [lst.rows[i] for i in lst.selection()]
        playable = [r for r in rows if "url" in r]
        opens = [r for r in rows if "open" in r]
        menu = self.menu()
        if lst is self.q_list:
            menu.add_command(label="Putar", command=self.play_selected)
            menu.add_command(label="Hapus dari antrean", command=self.remove_selected)
        elif opens and not playable:
            menu.add_command(label="Buka", command=lambda: self.open_collection(opens[0]))
            return menu
        else:
            menu.add_command(label="Putar", command=lambda: self.activate_results(play=True))
            menu.add_command(label="Putar berikutnya", command=lambda: self.play_next([dict(r) for r in playable]))
            menu.add_command(label="Tambah ke antrean", command=lambda: self.activate_results(play=False))
        if playable:
            menu.add_separator()
            menu.add_cascade(label="Simpan ke playlist", menu=self.build_save_menu(list(playable), parent=menu))
            liked = all(self.library.is_fav(r) for r in playable)
            menu.add_command(label="Hapus dari Favorit" if liked else "Tambahkan ke Favorit",
                             command=lambda: self.set_fav(list(playable), not liked))
            if len(playable) == 1 and playable[0].get("artist"):
                menu.add_command(label="Buka artis", command=lambda: self.open_artist(playable[0]))
            if len(playable) == 1:
                local = playable[0].get("kind") == "local"
                menu.add_command(label="Salin lokasi berkas" if local else "Salin link",
                                 command=lambda: self.copy_link(playable[0]))
        if lst is self.res_list and self.view[0] == "playlist":
            menu.add_command(label="Hapus dari playlist", command=self.drop_from_playlist)
        return menu

    def open_artist(self, track):
        """Halaman artis lagu ini: YouTube Music (lewat ID artis, atau dicari dari namanya bila belum ada),
        atau untuk musik lokal, semua lagu artis itu di folder musik."""
        if not track or not track.get("artist"):
            return
        if self.root.state() != "normal":
            self.restore_window()
        name = track["artist"].split(",")[0].strip()
        self.browse_token += 1
        token = self.browse_token
        self.show_view("browse", name)
        if track.get("kind") == "local":
            rows = [dict(t) for t in (self.local_rows or []) if t["artist"] == track["artist"]]
            self.on_browse(token, rows, "" if rows else "Lagu artis ini tidak ada di folder musik.")
            return
        self.res_list.wait()
        self.say("Membuka…")
        known = track.get("artist_id")

        def work():
            api, ident = self.ytm(), known
            if not ident:
                found = api.search(name, filter="artists", limit=3)
                ident = next((item.get("browseId") for item in found if item.get("browseId")), None)
            if ident:
                try:
                    rows = music.collection(api, "artist", ident)
                    if rows:
                        return "browse", token, rows, ""
                except Exception:
                    pass  # sebagian kanal YouTube punya halaman artis berformat lain; pakai pencarian di bawah
            rows = [row for row in music.search(api, name, "songs") if "url" in row]
            rows = rows or [row for row in music.search(api, name, "videos") if "url" in row]
            return "browse", token, rows, "" if rows else "Lagu %s tidak ditemukan di YouTube Music." % name

        self.background(work, lambda exc: ("browse", token, [], "%s\nPeriksa koneksi internet, lalu coba lagi." % exc))

    def copy_link(self, track):
        self.root.clipboard_clear()
        self.root.clipboard_append(track["url"])
        self.say("Lokasi berkas disalin" if track.get("kind") == "local" else "Link disalin")
