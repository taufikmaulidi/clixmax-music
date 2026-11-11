"""Sumber musik: pencarian dan isi koleksi YouTube Music (ytmusicapi), plus link lewat yt-dlp.

Fungsi di sini memblokir (jaringan); App memanggilnya dari thread latar.
"""
import re

from .config import LOADING, fmt_time
from .player import ytdl

YT_ID = re.compile(r"(?:v=|youtu\.be/|/shorts/|/live/)([A-Za-z0-9_-]{11})")


def art_base(item):
    """Alamat dasar cover dari server gambar Google (ukurannya ditentukan belakangan), atau None."""
    thumbs = item.get("thumbnails") or item.get("thumbnail") or []
    url = thumbs[-1].get("url", "") if isinstance(thumbs, list) and thumbs else ""
    return url.split("=")[0] if "googleusercontent.com" in url and "=" in url else None


def track_kind(item, art):
    """"song" (punya cover album) atau "video" (punya thumbnail video)."""
    if item.get("resultType") in ("song", "video"):
        return item["resultType"]
    video_type = item.get("videoType") or ""
    if video_type:
        return "song" if video_type == "MUSIC_VIDEO_TYPE_ATV" else "video"
    return "song" if art else "video"


def track_from_ytm(item, tag="", art=None):
    artists = ", ".join(a["name"] for a in (item.get("artists") or []) if a.get("name"))
    vid, art = item["videoId"], art_base(item) or art
    owner = next((a for a in (item.get("artists") or []) if a.get("id")), None)
    return {"id": vid, "title": item.get("title") or vid, "artist": artists, "tag": tag,
            "artist_id": owner["id"] if owner else None,
            "dur": item.get("duration") or item.get("length") or "", "art": art,
            "kind": track_kind(item, art), "url": "https://music.youtube.com/watch?v=" + vid}


def row_from_ytm(item):
    """Satu baris hasil pencarian: lagu/video bisa diputar (punya "url"); artis, album, dan
    playlist bisa dibuka (punya "open"). Jenis lain (podcast, profil) dilewati dengan None."""
    kind, browse = item.get("resultType"), item.get("browseId") or ""
    names = ", ".join(a["name"] for a in (item.get("artists") or []) if a.get("name"))
    if kind in ("song", "video") and item.get("videoId"):
        return track_from_ytm(item, "Lagu" if kind == "song" else "Video")
    if kind == "artist" and browse:
        return {"open": ("artist", browse), "title": item.get("artist") or item.get("title") or "?", "artist": "",
                "tag": "Artis", "dur": "", "art": art_base(item)}
    if kind == "album" and browse:
        return {"open": ("album", browse), "title": item.get("title") or "?", "artist": names, "tag": "Album",
                "dur": "", "art": art_base(item)}
    if kind == "playlist" and browse.startswith("VL"):
        return {"open": ("playlist", browse[2:]), "title": item.get("title") or "?",
                "artist": item.get("author") or "", "tag": "Playlist", "art": art_base(item),
                "dur": "%s lagu" % item["itemCount"] if item.get("itemCount") else ""}
    return None


def search(api, text, kind):
    rows = [row for row in map(row_from_ytm, api.search(text, filter=kind, limit=30)) if row]
    if kind:  # di bawah filter, jenisnya sudah jelas; label "Lagu"/"Video" tidak perlu diulang
        for row in rows:
            if "url" in row:
                row["tag"] = ""
    return rows


def collection(api, kind, ident):
    """Lagu-lagu di dalam playlist, album, atau halaman artis YouTube Music."""
    art = None
    if kind == "playlist":
        items = api.get_playlist(ident, limit=300).get("tracks") or []
    elif kind == "album":
        data = api.get_album(ident)
        items, art = data.get("tracks") or [], art_base(data)
    else:
        data = api.get_artist(ident)
        items = (((data.get("songs") or {}).get("results") or [])
                 + ((data.get("videos") or {}).get("results") or []))
    return [track_from_ytm(t, art=art) for t in items if t.get("videoId")]


def home(api):
    """Beranda YouTube Music: baris judul rak ("header") diikuti isinya."""
    rows = []
    for shelf in api.get_home(limit=6):
        items = []
        for item in shelf.get("contents") or []:
            browse = item.get("browseId") or ""
            if item.get("videoId"):
                track = track_from_ytm(item)
                track["tag"] = "Lagu" if track["kind"] == "song" else "Video"
                items.append(track)
            elif item.get("playlistId"):
                items.append({"open": ("playlist", item["playlistId"]), "title": item.get("title") or "?",
                              "artist": item.get("description") or "", "tag": "Playlist", "dur": "",
                              "art": art_base(item)})
            elif browse.startswith("MPRE"):
                names = ", ".join(a["name"] for a in (item.get("artists") or []) if a.get("name"))
                items.append({"open": ("album", browse), "title": item.get("title") or "?", "artist": names,
                              "tag": "Album", "dur": "", "art": art_base(item)})
            elif browse.startswith("UC"):
                items.append({"open": ("artist", browse), "title": item.get("title") or "?", "artist": "",
                              "tag": "Artis", "dur": "", "art": art_base(item)})
        if items:
            rows.append({"header": shelf.get("title") or "Untukmu"})
            rows.extend(items[:12])
    return rows


def radio(api, seed):
    """Lagu sejenis untuk melanjutkan antrean secara otomatis."""
    data = api.get_watch_playlist(videoId=seed, limit=25)
    return [track_from_ytm(t) for t in data.get("tracks") or [] if t.get("videoId")]


def single_link(url):
    """Lagu dari link satu video YouTube (tanpa daftar putar), atau None bila bukan link seperti itu."""
    match = YT_ID.search(url)
    if not match or "list=" in url:
        return None
    vid = match.group(1)
    return {"id": vid, "title": LOADING, "artist": "", "dur": "", "art": None, "kind": "video",
            "url": "https://www.youtube.com/watch?v=" + vid}


def read_link(url):
    """Semua lagu dari link lain (playlist, situs lain yang didukung yt-dlp)."""
    with ytdl(extract_flat="in_playlist") as ydl:
        info = ydl.extract_info(url, download=False)
    entries = info.get("entries") if info.get("_type") == "playlist" else [info]
    tracks = []
    for e in entries or []:
        link = e.get("url") or e.get("webpage_url") or ""
        if not link.startswith("http"):
            link = "https://www.youtube.com/watch?v=%s" % e.get("id")
        vid = e.get("id") if "youtu" in link and len(e.get("id") or "") == 11 else None
        tracks.append({"id": vid, "title": e.get("title") or link, "art": None, "kind": "video",
                       "artist": e.get("uploader") or e.get("channel") or "",
                       "dur": fmt_time(e["duration"]) if e.get("duration") else "", "url": link})
    return tracks
