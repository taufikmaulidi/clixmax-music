"""Data milik pengguna yang disimpan di disk: favorit, playlist sendiri, riwayat, dan sesi terakhir."""
import time

from .config import read_json, slim, write_json

HISTORY_LIMIT = 300


def _tracks(items):
    return [t for t in items or [] if isinstance(t, dict) and t.get("url")]


class Library:
    """Favorit dan playlist sendiri. Setiap perubahan langsung ditulis ke berkas."""

    def __init__(self, path):
        self.path = path
        data = read_json(path, {})
        self.favorites = _tracks(data.get("favorites"))
        self.playlists = [{"name": str(p["name"]), "tracks": _tracks(p.get("tracks"))}
                          for p in data.get("playlists") or [] if isinstance(p, dict) and p.get("name")]
        self.fav_urls = {t["url"] for t in self.favorites}
        self.history = [t for t in _tracks(data.get("history")) if isinstance(t.get("at"), str)]

    def save(self):
        write_json(self.path, {"favorites": self.favorites, "playlists": self.playlists, "history": self.history})

    def log_play(self, track):
        """Catat lagu yang mulai diputar. Lagu yang sama berturut-turut di hari yang sama tidak dicatat dua kali."""
        entry = dict(slim(track), at=time.strftime("%Y-%m-%d %H:%M"))
        last = self.history[0] if self.history else None
        if last and last["url"] == entry["url"] and last["at"][:10] == entry["at"][:10]:
            return False
        self.history.insert(0, entry)
        del self.history[HISTORY_LIMIT:]
        self.save()
        return True

    def clear_history(self):
        self.history = []
        self.save()

    def is_fav(self, track):
        return track.get("url") in self.fav_urls

    def toggle_fav(self, track):
        """Favoritkan atau batalkan. Mengembalikan True bila sekarang jadi favorit."""
        url = track["url"]
        if url in self.fav_urls:
            self.fav_urls.discard(url)
            self.favorites = [t for t in self.favorites if t["url"] != url]
        else:
            self.fav_urls.add(url)
            self.favorites.insert(0, slim(track))
        self.save()
        return url in self.fav_urls

    def create(self, name):
        self.playlists.append({"name": name, "tracks": []})
        self.save()
        return len(self.playlists) - 1

    def add_to(self, index, tracks):
        """Tambah lagu ke playlist tanpa menggandakan. Mengembalikan jumlah yang benar-benar baru."""
        playlist = self.playlists[index]
        have = {t["url"] for t in playlist["tracks"]}
        fresh = []
        for track in tracks:
            if track["url"] not in have:
                have.add(track["url"])
                fresh.append(slim(track))
        playlist["tracks"].extend(fresh)
        self.save()
        return len(fresh)

    def drop(self, index, positions):
        tracks = self.playlists[index]["tracks"]
        for i in sorted(positions, reverse=True):
            del tracks[i]
        self.save()

    def delete(self, index):
        del self.playlists[index]
        self.save()


def load_session(path):
    """(lagu-lagu antrean, posisi, detik) dari sesi terakhir."""
    data = read_json(path, {})
    tracks = _tracks(data.get("queue"))
    pos = data.get("pos")
    pos = pos if isinstance(pos, int) and 0 <= pos < len(tracks) else -1
    try:
        seconds = float(data.get("t") or 0)
    except (TypeError, ValueError):
        seconds = 0.0
    return tracks, pos, seconds


def save_session(path, tracks, pos, seconds):
    write_json(path, {"queue": [slim(t) for t in tracks], "pos": pos, "t": seconds or 0})
