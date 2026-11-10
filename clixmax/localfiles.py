"""Musik lokal: memindai folder, membaca tag (judul, artis, durasi), dan cover yang tertanam."""
import base64
import os

from .config import fmt_time, read_json, write_json

AUDIO = {".mp3", ".flac", ".m4a", ".mp4", ".aac", ".ogg", ".oga", ".opus", ".wav", ".wma", ".aif", ".aiff"}
COVERS = ("cover.jpg", "folder.jpg", "front.jpg", "cover.png", "folder.png", "album.jpg")
LIMIT = 10000


def read_tags(path):
    """(judul, artis, detik) dari tag berkas; judul jatuh ke nama berkas bila tag kosong."""
    title, artist, seconds = os.path.splitext(os.path.basename(path))[0], "", None
    try:
        from mutagen import File
        audio = File(path, easy=True)
        if audio is not None:
            tags = audio.tags or {}
            title = (tags.get("title") or [title])[0] or title
            artist = (tags.get("artist") or tags.get("albumartist") or [""])[0]
            seconds = getattr(audio.info, "length", None)
    except Exception:
        pass
    return title, artist, seconds


def as_track(path, title, artist, seconds):
    return {"id": None, "title": title, "artist": artist or "", "dur": fmt_time(seconds) if seconds else "",
            "art": None, "kind": "local", "url": path}


def cover_bytes(path):
    """Gambar cover tertanam di berkas (ID3, MP4, FLAC, Ogg), lalu cover.jpg di foldernya."""
    try:
        from mutagen import File
        audio = File(path)
        if audio is not None:
            if getattr(audio, "pictures", None):
                return audio.pictures[0].data
            tags = audio.tags
            if tags is not None:
                for key in list(tags.keys()):
                    if str(key).startswith("APIC"):
                        return tags[key].data
                if "covr" in tags and tags["covr"]:
                    return bytes(tags["covr"][0])
                if "metadata_block_picture" in tags:
                    from mutagen.flac import Picture
                    return Picture(base64.b64decode(tags["metadata_block_picture"][0])).data
    except Exception:
        pass
    folder = os.path.dirname(path)
    for name in COVERS:
        candidate = os.path.join(folder, name)
        if os.path.isfile(candidate):
            with open(candidate, "rb") as f:
                return f.read()
    return None


class LocalIndex:
    """Daftar lagu di folder musik. Tag hanya dibaca ulang untuk berkas yang berubah sejak pindaian lalu."""

    def __init__(self, path):
        self.path = path
        data = read_json(path, {})
        self.files = data.get("files") if isinstance(data.get("files"), dict) else {}

    def scan(self, folder):
        tracks, seen = [], {}
        for base, dirs, names in os.walk(folder):
            dirs.sort()
            for name in sorted(names):
                if os.path.splitext(name)[1].lower() not in AUDIO:
                    continue
                path = os.path.join(base, name)
                try:
                    mtime = os.path.getmtime(path)
                except OSError:
                    continue
                cached = self.files.get(path)
                entry = cached if cached and cached[0] == mtime else [mtime, *read_tags(path)]
                seen[path] = entry
                tracks.append(as_track(path, *entry[1:]))
                if len(tracks) >= LIMIT:
                    break
        self.files = seen
        write_json(self.path, {"folder": folder, "files": seen})
        return sorted(tracks, key=lambda t: (t["artist"].casefold(), t["title"].casefold()))
