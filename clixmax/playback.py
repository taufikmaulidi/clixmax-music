"""Bagian App yang mengurus pemutaran: mpv, antrean, efek suara, lirik, riwayat, dan media OS."""
import queue
import time
import traceback
from tkinter import messagebox

from . import artwork, audio, config, music
from . import lyrics as lyricsmod
from .config import APP, LOADING, TITLE, fmt_time, log_error, seconds_of
from .library import load_session, save_session
from .player import start_mpv
from .theme import RED, SURF, G_LYRICS, G_MUTE, G_PAUSE, G_PLAY, G_REPEAT, G_REPEAT_ONE, G_VOL


class Playback:
    # ---------- mpv ----------
    def send(self, *args):
        self.cmdq.put(args)

    def mpv_loop(self):
        mpv = None
        try:
            mpv = self.engine = start_mpv(int(self.cfg.get("volume", 70)))
            last = 0.0
            while self.alive:
                try:
                    item = self.cmdq.get(timeout=0.25)
                    if item[0] == "@playlist":  # minta urutan antrean versi mpv (setelah diacak)
                        self.uiq.put(("playlist", mpv.get("playlist")))
                    else:
                        mpv.cmd(*item)
                except queue.Empty:
                    pass
                if time.time() - last >= 0.5 and self.cmdq.empty():
                    last = time.time()
                    self.uiq.put(("state", {name: mpv.get(prop) for name, prop in (
                        ("pos", "playlist-pos"), ("t", "time-pos"), ("dur", "duration"), ("pause", "pause"),
                        ("idle", "idle-active"), ("title", "media-title"), ("mute", "mute"), ("vol", "volume"))}))
        except Exception as exc:
            if self.alive:
                log_error(traceback.format_exc())
                self.uiq.put(("fatal", str(exc)))
        finally:
            if mpv:
                mpv.stop()

    def pump(self):
        """Proses pesan dari thread lain. Error satu pesan dicatat dan tidak menghentikan pesan berikutnya."""
        try:
            while True:
                msg = self.uiq.get_nowait()
                try:
                    getattr(self, "on_" + msg[0])(*msg[1:])
                except Exception:
                    log_error(traceback.format_exc())
                if not self.alive:  # pesan tadi menutup aplikasi (Keluar dari tray): sisa pesan diabaikan
                    return
        except queue.Empty:
            pass
        if self.alive:
            self.pump_job = self.root.after(120, self.pump)

    def now_track(self):
        pos = (self.state or {}).get("pos")
        return self.queue[pos] if isinstance(pos, int) and 0 <= pos < len(self.queue) else None

    def on_state(self, st):
        self.state, self.state_at = st, time.time()
        rows = self.queue
        pos = st["pos"] if isinstance(st["pos"], int) else -1
        track = rows[pos] if 0 <= pos < len(rows) else None
        if track and track["title"] == LOADING and st["title"] and not st["title"].startswith("watch?"):
            track["title"] = st["title"]
            self.q_list.retitle(pos)
        changed = pos != self.pos
        if changed:
            self.pos = pos
            self.q_list.mark_now(pos)
        loading = track is not None and st["t"] is None and not st["idle"]
        if track:
            title, sub = track["title"], "Memuat…" if loading else track["artist"]
            self.root.title("%s - %s" % (title, APP))
        else:
            title, sub = "Antrean selesai" if rows else "Belum ada yang diputar", ""
            self.root.title(TITLE)
        playing = track is not None and not st["pause"]
        self.now.show(title, sub, track)
        self.now_side.show(title, sub, track)
        self.now_card.load(track)
        self.refresh_tint()
        self.now_args = (title, sub, track, playing)
        if self.island_on:
            self.island.show_state(*self.now_args)
        if self.resume_at:  # lanjutkan dari detik terakhir begitu lagu sesi lalu selesai dimuat
            if pos == self.resume_at[0] and st["t"] is not None:
                if self.resume_at[1] > 5:
                    self.send("seek", self.resume_at[1], "absolute")
                self.resume_at = None
            elif pos >= 0 and pos != self.resume_at[0]:
                self.resume_at = None
        dur = st["dur"] or 0
        self.t_now.configure(text=fmt_time(st["t"]) if track else "-:--")
        self.t_end.configure(text=fmt_time(dur) if dur else "-:--")
        self.seek.span(max(dur, 1))
        if not self.seek.dragging:
            self.seek.set(st["t"] or 0)
        self.play_btn.show(G_PLAY if (st["pause"] or not track) else G_PAUSE)
        if track is not None and st["t"] is not None and self.logged is not track:
            self.logged = track
            if self.library.log_play(track) and self.view[0] == "history":
                self.draw_history()
        if self.view[0] == "player":
            self.player_view.show(track)
        if changed and self.lyrics_visible():
            self.load_lyrics()
        self.update_os_media(title, track, playing)
        self.maybe_radio(pos)

    def update_os_media(self, title, track, playing):
        url = None
        if track:
            url = artwork.art_url(track, 300, 300, wide=artwork.is_video(track))
            if url and url.startswith(artwork.LOCAL):
                url = None  # panel media OS hanya menerima alamat web
        self.media.update(title if track else "", (track or {}).get("artist", ""), url, playing, track is not None)
        if self.tray:
            self.tray.set_playing(playing, title if track else "")

    def refresh_tint(self):
        url = self.now_card.art.url
        color = self.art_tint.get(url) if (self.cfg["tint"] and url) else None
        self.now_card.set_tint(color or SURF)

    def on_key(self, action):
        """Aksi dari tombol media, panel media OS, atau tray."""
        if action == "toggle":
            self.toggle()
        elif action == "play":
            if (self.state or {}).get("pos") in (None, -1) and self.queue:
                self.toggle()
            else:
                self.send("set_property", "pause", False)
        elif action == "pause":
            self.send("set_property", "pause", True)
        elif action in ("next", "prev"):
            self.send("playlist-next" if action == "next" else "playlist-prev")
        elif action == "show":
            self.restore_window()
        elif action == "quit":
            self.close()

    def on_fatal(self, text):
        self.say("Pemutar berhenti: " + text)
        messagebox.showerror(APP, "Pemutar audio berhenti:\n\n%s\n\nRincian ada di %s" % (text, config.LOG))

    # ---------- antrean ----------
    def add(self, tracks, play=False):
        if not tracks:
            return
        start = len(self.queue)
        for track in tracks:
            track.pop("tag", None)  # label jenis hanya untuk daftar hasil pencarian
        self.q_list.append(tracks)
        for i, t in enumerate(tracks):
            self.send("loadfile", t["url"], "append" if (play and i == 0) else "append-play")
        if play:
            self.send("playlist-play-index", start)
            self.send("set_property", "pause", False)
        self.pos = None  # paksa penanda "sedang diputar" digambar ulang
        self.sync_queue()

    def play_next(self, tracks):
        """Sisipkan tepat setelah lagu yang sedang diputar."""
        if not tracks:
            return
        current = (self.state or {}).get("pos")
        at = current + 1 if isinstance(current, int) and current >= 0 else len(self.queue)
        for k, track in enumerate(tracks):
            track.pop("tag", None)
            # Ditambahkan di ujung lalu dipindah, bukan "loadfile ... insert-at" yang baru ada sejak mpv 0.38
            # (libmpv yang ikut di versi macOS adalah mpv 0.36).
            self.send("loadfile", track["url"], "append")
            self.send("playlist-move", len(self.queue) + k, at + k)
        self.q_list.insert(at, tracks)
        self.pos = None
        self.sync_queue()
        self.say("%d lagu diputar berikutnya" % len(tracks))

    def play_selected(self):
        chosen = self.q_list.selection()
        if chosen:
            self.send("playlist-play-index", chosen[0])
            self.send("set_property", "pause", False)

    def remove_selected(self):
        chosen = self.q_list.selection()
        if not chosen:
            self.say("Pilih lagu di antrean dulu")
            return
        for i in reversed(chosen):
            self.send("playlist-remove", i)
        self.q_list.remove(chosen)
        self.pos = None
        self.sync_queue()

    def move_queue(self, src, dst):
        """Geser lagu di antrean (seret atau Alt+panah); mpv diberi tahu urutan barunya."""
        if src == dst or not (0 <= src < len(self.queue) and 0 <= dst < len(self.queue)):
            return
        # playlist-move menaruh lagu di depan entri tujuan, jadi saat bergeser ke bawah tujuannya +1.
        self.send("playlist-move", src, dst + 1 if dst > src else dst)
        self.q_list.move(src, dst)
        self.pos = None

    def clear_queue(self):
        self.send("stop")
        self.q_list.remove(range(len(self.queue)))
        self.sync_queue()

    def toggle(self):
        if self.pos == -1 and self.queue:
            self.send("playlist-play-index", 0)
            self.send("set_property", "pause", False)
        else:
            self.send("cycle", "pause")

    def shuffle(self):
        if len(self.queue) < 2:
            self.say("Antrean butuh minimal dua lagu untuk diacak")
            return
        self.send("playlist-shuffle")
        self.cmdq.put(("@playlist",))

    def on_playlist(self, entries):
        """Samakan urutan daftar dengan urutan mpv setelah diacak."""
        buckets = {}
        for track in self.queue:
            buckets.setdefault(track["url"], []).append(track)
        order = []
        for entry in entries or []:
            same = buckets.get(entry.get("filename"))
            if same:
                order.append(same.pop(0))
        placed = {id(track) for track in order}
        order += [track for track in self.queue if id(track) not in placed]
        self.q_list.fill(order)
        self.pos = None
        self.sync_queue()
        self.say("Antrean diacak")

    def cycle_repeat(self):
        self.repeat = (self.repeat + 1) % 3
        self.send("set_property", "loop-playlist", "inf" if self.repeat == 1 else "no")
        self.send("set_property", "loop-file", "inf" if self.repeat == 2 else "no")
        self.repeat_btn.show(G_REPEAT_ONE if self.repeat == 2 else G_REPEAT, active=self.repeat > 0)
        self.say(("Ulangi: mati", "Ulangi: seluruh antrean", "Ulangi: satu lagu")[self.repeat])

    def maybe_radio(self, pos):
        if (not self.radio_on or self.radio_busy or self.repeat or not self.queue
                or pos not in (-1, len(self.queue) - 1)):
            return
        seed = self.queue[-1].get("id")
        if not seed or seed in self.radio_seeds:
            return
        self.radio_busy = True
        self.background(lambda: ("radio", seed, music.radio(self.ytm(), seed)), lambda exc: ("radio", seed, []))

    def on_radio(self, seed_id, tracks):
        self.radio_busy = False
        self.radio_seeds.add(seed_id)
        have = {t["id"] for t in self.queue}
        self.add([t for t in tracks if t["id"] not in have][:20])

    def set_radio(self, on):
        self.radio_on = on

    # ---------- suara ----------
    def apply_audio(self):
        self.send("set_property", "af", audio.chain(self.cfg["normalize"], self.cfg["pitch"]))
        self.send("set_property", "speed", float(self.cfg["speed"]))

    def set_normalize(self, on):
        self.cfg["normalize"] = bool(on)
        self.apply_audio()
        self.save_cfg()

    def set_speed(self, value):
        value = round(round(min(2.0, max(0.5, float(value))) / 0.05) * 0.05, 2)
        if abs(value - self.cfg["speed"]) > 1e-6:
            self.cfg["speed"] = value
            self.send("set_property", "speed", value)
            self.save_cfg()

    def set_pitch(self, value):
        value = int(round(min(6, max(-6, float(value)))))
        if value != self.cfg["pitch"]:
            self.cfg["pitch"] = value
            self.apply_audio()
            self.save_cfg()

    def reset_audio(self):
        self.cfg.update(speed=1.0, pitch=0)
        self.apply_audio()
        self.save_cfg()
        self.settings_view.sync()

    def toggle_mute(self):
        self.muted = not self.muted
        self.send("set_property", "mute", self.muted)
        self.mute_btn.show(G_MUTE if self.muted else G_VOL)

    def nudge_volume(self, delta):
        self.vol.set(self.vol.value + delta)
        self.send("set_property", "volume", int(self.vol.value))

    # ---------- lirik ----------
    def toggle_lyrics(self):
        self.lyrics_open = not self.lyrics_open
        if self.lyrics_open:
            self.queue_box.pack_forget()
            self.lyrics_box.pack(fill="both", expand=True)
            self.load_lyrics()
            self.lyrics_tick()
        else:
            self.lyrics_box.pack_forget()
            self.queue_box.pack(fill="both", expand=True)
        self.lyrics_btn.show(G_LYRICS, active=self.lyrics_open)

    def lyric_spots(self):
        """Tempat lirik tampil: panel kanan dan halaman Sedang diputar, masing-masing (lirik, sumber, coba lagi)."""
        return ((self.lyrics_view, self.lyrics_source, self.lyrics_retry),
                (self.player_view.lyrics, self.player_view.source, self.player_view.retry))

    def lyrics_visible(self):
        return self.lyrics_open or self.view[0] == "player"

    def load_lyrics(self, force=False):
        track = self.now_track()
        for _, _, retry in self.lyric_spots():
            retry.pack_forget()
        if not track:
            self.lyrics_key = None
            for view, source, _ in self.lyric_spots():
                source.configure(text="")
                view.say("Belum ada yang diputar", "Putar lagu untuk melihat liriknya di sini.")
            return
        key = track["url"]
        if key == self.lyrics_key and not force:
            return
        self.lyrics_key = key
        cached = None if force else self.lyrics_cache.get(key)
        if cached:
            self.show_lyrics(cached)
            return
        for view, source, _ in self.lyric_spots():
            view.wait()
            source.configure(text="Mencari…")
        self.lyrics_token += 1
        token, snapshot, words = self.lyrics_token, dict(track), self.cfg["word_lyrics"]
        seconds = (self.state or {}).get("dur") or seconds_of(track.get("dur"))
        self.background(lambda: ("lyrics", token, key, lyricsmod.lookup(snapshot, seconds, words)),
                        lambda exc: ("lyrics", token, key, {"error": str(exc)}))

    def on_lyrics(self, token, key, result):
        if token != self.lyrics_token:
            return
        if "error" not in result:
            self.lyrics_cache.put(key, result)
        if key == self.lyrics_key:
            self.show_lyrics(result)

    def show_lyrics(self, result):
        for view, source, retry in self.lyric_spots():
            self.show_lyrics_in(view, source, retry, result)

    def show_lyrics_in(self, view, source, retry, result):
        origin = result.get("source") or "LRCLIB"  # simpanan lama hanya dari LRCLIB
        if "error" in result:
            view.say("Lirik gagal dimuat", "%s\nPeriksa koneksi internet, lalu tekan Coba lagi." % result["error"], RED)
            source.configure(text="")
            retry.pack(side="right")
        elif result.get("instrumental"):
            view.say("Lagu instrumental", "Lagu ini tidak punya lirik.")
            source.configure(text="Dari %s" % origin)
        elif result.get("lines"):
            words = result.get("words")
            view.show_synced(result["lines"], words)
            source.configure(text="Dari %s%s" % (origin, ", per kata" if words else ""))
        elif result.get("plain"):
            view.show_plain(result["plain"])
            source.configure(text="Dari %s, tanpa waktu" % origin)
        else:
            names = [name for name, _ in lyricsmod.SOURCES if self.cfg["word_lyrics"] or name != "Better Lyrics"]
            view.say("Lirik tidak ditemukan", "Dicari di %s, dan %s dari judul, artis, dan durasi. Set DJ, remix, "
                                              "dan video biasanya tidak punya lirik." % (", ".join(names[:-1]),
                                                                                         names[-1]))
            source.configure(text="")

    def lyrics_tick(self):
        """Sorot baris lirik mengikuti waktu lagu; posisi ditaksir di antara laporan mpv (tiap 0,5 detik)."""
        if self.lyrics_job:
            self.root.after_cancel(self.lyrics_job)
        self.lyrics_job = None
        if not self.lyrics_visible() or not self.alive:
            return
        seconds = self.position_now()
        if seconds is not None:
            for view, _, _ in self.lyric_spots():
                view.at_time(seconds)
        self.lyrics_job = self.root.after(150, self.lyrics_tick)

    def position_now(self):
        """Posisi lagu sekarang: laporan mpv terakhir ditambah waktu yang sudah lewat sejak itu."""
        st = self.state or {}
        seconds = st.get("t")
        if seconds is None:
            return None
        if not st.get("pause"):
            seconds += (time.time() - self.state_at) * float(self.cfg["speed"])
        return seconds

    def lyric_now(self, track):
        """Baris lirik yang sedang dinyanyikan (untuk pulau mini), atau None. Lirik yang belum ada
        dicari diam-diam di latar tanpa mengubah panel Lirik."""
        if not track:
            return None
        data = self.lyrics_cache.get(track["url"])
        if data is None:
            self.fetch_lyrics_quietly(track)
            return None
        lines, seconds = data.get("lines") or [], self.position_now()
        if not lines or seconds is None:
            return None
        current = [text for start, text in lines if start <= seconds + 0.2]
        return current[-1] if current and current[-1] else None

    def fetch_lyrics_quietly(self, track):
        key = track["url"]
        if key in self.lyrics_quiet:
            return
        self.lyrics_quiet.add(key)  # dicoba sekali per lagu per sesi, supaya tidak membanjiri sumber lirik
        snapshot, words = dict(track), self.cfg["word_lyrics"]
        seconds = (self.state or {}).get("dur") or seconds_of(track.get("dur"))
        self.background(lambda: ("lyrics_quiet", key, lyricsmod.lookup(snapshot, seconds, words)),
                        lambda exc: ("lyrics_quiet", key, None))

    def on_lyrics_quiet(self, key, result):
        if result is not None:
            self.lyrics_cache.put(key, result)

    def seek_to(self, seconds):
        self.send("seek", round(float(seconds), 2), "absolute")

    # ---------- sesi terakhir ----------
    def save_session(self):
        pos = (self.state or {}).get("pos")
        save_session(config.SESSION, self.queue, pos if isinstance(pos, int) else -1, (self.state or {}).get("t"))

    def autosave(self):
        if self.alive:
            self.save_session()
            self.autosave_job = self.root.after(20000, self.autosave)

    def restore_session(self):
        """Pulihkan antrean terakhir dalam keadaan dijeda, di posisi lagu terakhir."""
        tracks, pos, seconds = load_session(config.SESSION)
        if not tracks:
            return
        self.q_list.append(tracks)
        for track in tracks:
            self.send("loadfile", track["url"], "append")
        if pos >= 0:
            self.send("set_property", "pause", True)
            self.send("playlist-play-index", pos)
            self.resume_at = (pos, seconds)
        self.pos = None
        self.sync_queue()
        self.say("Antrean terakhir dipulihkan. Tekan putar untuk melanjutkan.")
