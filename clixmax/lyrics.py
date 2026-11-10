"""Lirik dari beberapa sumber, dicoba berurutan sampai ada yang punya lirik berwaktu:

1. Better Lyrics (lyrics-api.boidu.dev): satu-satunya yang memberi waktu per kata, jadi baris bisa disorot
   kata demi kata. Ditanya untuk setiap lagu, karena itu bisa dimatikan di Pengaturan.
2. LRCLIB (lrclib.net): per baris, juga sumber teks biasa bila tidak ada yang berwaktu.
3. YouTube Music: lirik berwaktu milik YouTube sendiri (berlisensi per negara, kadang tidak ada).
4. Netease, QQ Music, Kugou: katalog besar dari Tiongkok, banyak lagu Asia dan Barat. Netease kadang
   juga punya waktu per kata.

Lagu populer punya beberapa versi (album, single, radio edit) yang panjangnya berbeda, dan lirik versi lain
meleset beberapa detik. Karena itu setiap kandidat harus sepanjang lagu yang diputar (selisih paling banyak
TOLERANCE detik). Hasil disimpan di komputer (LyricsCache), jadi memutar ulang lagu langsung tampil.

Bentuk hasil: {"found", "source", "lines": [(detik, teks)], "words": [[(mulai, selesai, teks)] atau None per
baris], "plain", "instrumental"}.
"""
import base64
import html
import json
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from .config import read_json, write_json

VERSION = 2  # hasil "tidak ditemukan" dari versi lama (hanya LRCLIB) dicari ulang di semua sumber
TOLERANCE = 3
LRCLIB = "https://lrclib.net/api"
BETTER = "https://lyrics-api.boidu.dev/getLyrics"
HEADERS = {"User-Agent": "ClixMax/1.0 (pemutar musik desktop pribadi)"}
BROWSER = {"User-Agent": "Mozilla/5.0"}
NOISE = re.compile(r"\s*[\(\[][^\)\]]*\b(official|video|audio|lyrics?|lirik|visuali[sz]er|mv|m/v|hd|4k|"
                   r"remaster(ed)?|explicit|clip)\b[^\)\]]*[\)\]]", re.I)
FEAT = re.compile(r"\s*[\(\[]?\b(feat\.?|ft\.?|featuring)\s.*$", re.I)
STAMP = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\]")
# Baris kredit di awal lirik Netease/QQ/Kugou ("作词 : ...", "Composed by：...") bukan lirik.
CREDIT = re.compile(r"^\s*(作词|作曲|编曲|制作人?|监制|混音|和声|吉他|贝斯|鼓|录音|母带|出品|发行|词|曲|"
                    r"lyrics( written)? by|composed by|arranged by|produced by|written by|lyricist|composer)"
                    r"\s*[:：]", re.I)
INSTRUMENTAL = ("此歌曲为没有填词的纯音乐", "纯音乐，请欣赏", "纯音乐, 请欣赏")
TT = "{http://www.w3.org/ns/ttml}"
TTM = "{http://www.w3.org/ns/ttml#metadata}"
ITUNES = "{http://music.apple.com/lyric-ttml-internal}"


def query_for(track):
    """(judul, artis) yang bersih untuk dicari: tanpa "(Official Video)", "feat.", atau nama kanal."""
    title = (track.get("title") or "").strip()
    artist = (track.get("artist") or "").split(",")[0].replace(" - Topic", "").strip()
    if " - " in title and (track.get("kind") == "video" or not artist):
        artist, title = (part.strip() for part in title.split(" - ", 1))
    title = NOISE.sub("", title)
    title = re.split(r"\s+[|｜]\s+", title)[0]
    return FEAT.sub("", title).strip(" -"), artist


def norm(text):
    """Bentuk pembanding: huruf kecil, tanpa isi kurung, tanpa tanda baca dan spasi."""
    text = unicodedata.normalize("NFKC", text or "").lower()
    text = re.sub(r"[\(\[（【].*?[\)\]）】]", "", text)
    return "".join(ch for ch in text if ch.isalnum())


def same_title(found, wanted):
    a, b = norm(found), norm(wanted)
    return bool(a and b) and (a == b or (min(len(a), len(b)) >= 4 and (a.startswith(b) or b.startswith(a))))


def same_artist(found, wanted):
    a, b = norm(found), norm(wanted)
    return not b or (bool(a) and (b in a or a in b))


def near(found, seconds):
    return not seconds or (found is not None and abs(found - seconds) <= TOLERANCE)


def parse_lrc(text):
    """Teks LRC menjadi [(detik, baris)] terurut, tanpa baris kredit."""
    lines = []
    for raw in text.splitlines():
        stamps = STAMP.findall(raw)
        words = re.sub(r"\[[^\]]*\]", "", raw).strip()
        if CREDIT.match(words):
            continue
        for minutes, seconds in stamps:
            lines.append((int(minutes) * 60 + float(seconds), words))
    return sorted(lines, key=lambda line: line[0])


def from_lrc(text, title=""):
    """Hasil dari teks LRC sumber Tiongkok: buang baris judul di detik nol, kenali tanda instrumental."""
    if any(mark in text for mark in INSTRUMENTAL):
        return {"found": True, "instrumental": True}
    lines = parse_lrc(text)
    while lines and lines[0][0] < 1 and (not lines[0][1] or same_title(lines[0][1].split(" - ")[0], title)):
        lines.pop(0)
    if not any(text for _, text in lines):
        return None
    return {"found": True, "lines": lines}


def _open(url, headers=None, timeout=8):
    return urllib.request.urlopen(urllib.request.Request(url, headers=headers or HEADERS), timeout=timeout)


def _json(url, headers=None, missing=(400, 404)):
    try:
        with _open(url, headers) as reply:
            return json.loads(reply.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        if exc.code in missing:
            return None
        raise


# ---------- Better Lyrics: waktu per kata ----------
def ttml_time(value):
    """"13.274", "1:02.5", atau "0:01:02.5" menjadi detik."""
    total = 0.0
    for part in (value or "0").split(":"):
        total = total * 60 + float(part)
    return total


def parse_ttml(text):
    """TTML (format lirik Apple Music) menjadi hasil. Vokal latar (x-bg) dilewati supaya baris tidak tumpang."""
    root = ET.fromstring(text)
    body = root.find(TT + "body")
    duration = ttml_time(body.get("dur")) if body is not None and body.get("dur") else None
    timing = (root.get(ITUNES + "timing") or "").lower()
    lines, words = [], []
    for p in root.iter(TT + "p"):
        parts = []
        for span in p:
            if span.tag != TT + "span" or span.get(TTM + "role") == "x-bg":
                continue
            word = "".join(span.itertext()) + (span.tail or "")
            parts.append((ttml_time(span.get("begin")), ttml_time(span.get("end")), word))
        text_line = ("".join(w[2] for w in parts) if parts else "".join(p.itertext())).strip()
        lines.append((ttml_time(p.get("begin")), text_line))
        words.append([(b, e, w) for b, e, w in parts if w.strip()] if timing == "word" and parts else None)
    return duration, lines, words


def better_lyrics(title, artist, seconds, track):
    params = {"s": title, "a": artist}
    if seconds:
        params["d"] = int(round(seconds))
    if len(track.get("id") or "") == 11:
        params["videoId"] = track["id"]
    # 429: batas permintaan layanan itu habis; anggap tidak ada, sumber berikutnya yang menjawab.
    data = _json(BETTER + "?" + urllib.parse.urlencode(params), missing=(400, 404, 422, 429))
    if not data or not data.get("ttml"):
        return None
    duration, lines, words = parse_ttml(data["ttml"])
    if not lines or not near(duration, seconds):
        return None
    if not any(words):
        words = None
    return {"found": True, "lines": lines, "words": words}


# ---------- LRCLIB ----------
def lrclib(title, artist, seconds, track):
    hit = None
    if artist:
        params = {"track_name": title, "artist_name": artist}
        if seconds:
            params["duration"] = int(round(seconds))
        hit = _json("%s/get?%s" % (LRCLIB, urllib.parse.urlencode(params)))
        if hit and seconds and not near(hit.get("duration"), seconds):
            hit = None  # /get kadang memberi versi lain bila versi sepanjang ini tidak ada
    if not hit and seconds:  # tanpa durasi, hasil pencarian terlalu mudah salah lagu
        query = {"track_name": title, "artist_name": artist} if artist else {"q": title}
        found = _json("%s/search?%s" % (LRCLIB, urllib.parse.urlencode(query))) or []
        found = [item for item in found if near(item.get("duration"), seconds)]
        found.sort(key=lambda item: not item.get("syncedLyrics"))
        hit = found[0] if found else None
    if not hit:
        return None
    if hit.get("instrumental"):
        return {"found": True, "instrumental": True}
    lines = parse_lrc(hit.get("syncedLyrics") or "")
    plain = (hit.get("plainLyrics") or "").strip()
    return {"found": bool(lines or plain), "lines": lines, "plain": plain} if (lines or plain) else None


# ---------- YouTube Music ----------
_ytm = None


def youtube_music(title, artist, seconds, track):
    """Lirik milik YouTube Music untuk video ini. Video klip (bukan lagu) dilewati: waktunya mengikuti
    versi audio, yang panjangnya sering berbeda dari klipnya."""
    global _ytm
    vid = track.get("id") or ""
    if len(vid) != 11 or track.get("kind") in ("video", "local"):
        return None
    if _ytm is None:
        from ytmusicapi import YTMusic
        _ytm = YTMusic()
    browse = _ytm.get_watch_playlist(vid, limit=1).get("lyrics")
    if not browse:
        return None
    data = _ytm.get_lyrics(browse, timestamps=True) or {}
    found = data.get("lyrics")
    if data.get("hasTimestamps") and found:
        lines = [(line.start_time / 1000, "" if line.text.strip() == "♪" else line.text.strip()) for line in found]
        return {"found": True, "lines": lines}
    if isinstance(found, str) and found.strip():
        return {"found": True, "lines": [], "plain": found.strip()}
    return None


# ---------- Netease ----------
NETEASE = {"User-Agent": "Mozilla/5.0", "Referer": "https://music.163.com/"}


def parse_yrc(text):
    """Lirik per kata Netease: "[mulai,durasi](mulai,durasi,0)kata..." dalam milidetik."""
    lines, words = [], []
    for raw in text.splitlines():
        head = re.match(r"\[(\d+),(\d+)\]", raw)
        if not head:
            continue
        parts = [(int(s) / 1000, (int(s) + int(d)) / 1000, w)
                 for s, d, w in re.findall(r"\((\d+),(\d+),\d+\)([^(]*)", raw[head.end():])]
        text_line = "".join(w for _, _, w in parts).strip()
        if not text_line or CREDIT.match(text_line):
            continue
        lines.append((int(head.group(1)) / 1000, text_line))
        words.append([p for p in parts if p[2].strip()])
    return lines, words


def netease(title, artist, seconds, track):
    query = urllib.parse.urlencode({"s": ("%s %s" % (title, artist)).strip(), "type": 1, "limit": 10})
    songs = ((_json("https://music.163.com/api/search/get?" + query, NETEASE) or {}).get("result") or {})
    for song in songs.get("songs") or []:
        names = " ".join(a.get("name") or "" for a in song.get("artists") or [])
        if not (same_title(song.get("name"), title) and same_artist(names, artist)
                and near((song.get("duration") or 0) / 1000, seconds)):
            continue
        params = urllib.parse.urlencode({"id": song["id"], "lv": 1, "tv": 1, "yv": 1})
        data = _json("https://music.163.com/api/song/lyric?" + params, NETEASE) or {}
        if data.get("pureMusic"):
            return {"found": True, "instrumental": True}
        lines, words = parse_yrc((data.get("yrc") or {}).get("lyric") or "")
        if lines:
            return {"found": True, "lines": lines, "words": words}
        return from_lrc((data.get("lrc") or {}).get("lyric") or "", title)
    return None


# ---------- QQ Music ----------
QQ = {"User-Agent": "Mozilla/5.0", "Referer": "https://y.qq.com/"}


def qq_music(title, artist, seconds, track):
    query = urllib.parse.urlencode({"w": ("%s %s" % (title, artist)).strip(), "format": "json", "p": 1, "n": 10})
    data = _json("https://c.y.qq.com/soso/fcgi-bin/client_search_cp?" + query, QQ) or {}
    for song in ((data.get("data") or {}).get("song") or {}).get("list") or []:
        names = " ".join(s.get("name") or "" for s in song.get("singer") or [])
        if not (same_title(song.get("songname"), title) and same_artist(names, artist)
                and near(song.get("interval"), seconds)):
            continue
        params = urllib.parse.urlencode({"songmid": song["songmid"], "format": "json", "nobase64": 1, "g_tk": 5381})
        found = _json("https://c.y.qq.com/lyric/fcgi-bin/fcg_query_lyric_new.fcg?" + params, QQ) or {}
        if found.get("retcode") == 0 and found.get("lyric"):
            return from_lrc(html.unescape(found["lyric"]), title)
    return None


# ---------- Kugou ----------
def kugou(title, artist, seconds, track):
    if not seconds:  # Kugou mencocokkan lewat durasi; tanpanya hasilnya tebakan
        return None
    query = urllib.parse.urlencode({"ver": 1, "man": "yes", "client": "pc", "duration": int(seconds * 1000),
                                    "keyword": ("%s - %s" % (artist, title)) if artist else title})
    data = _json("http://lyrics.kugou.com/search?" + query, BROWSER) or {}
    for item in data.get("candidates") or []:
        if not (same_title(item.get("song"), title) and same_artist(item.get("singer"), artist)
                and near((item.get("duration") or 0) / 1000, seconds)):
            continue
        params = urllib.parse.urlencode({"ver": 1, "client": "pc", "id": item["id"], "accesskey": item["accesskey"],
                                         "fmt": "lrc", "charset": "utf8"})
        found = _json("http://lyrics.kugou.com/download?" + params, BROWSER) or {}
        if found.get("content"):
            return from_lrc(base64.b64decode(found["content"]).decode("utf-8", "replace"), title)
    return None


SOURCES = (("Better Lyrics", better_lyrics), ("LRCLIB", lrclib), ("YouTube Music", youtube_music),
           ("Netease", netease), ("QQ Music", qq_music), ("Kugou", kugou))


def lookup(track, seconds, words=True):
    """Cari lirik di semua sumber berurutan; berhenti di lirik berwaktu pertama.

    Teks tanpa waktu disimpan sebagai cadangan dan dipakai hanya bila tidak ada sumber yang berwaktu.
    words=False melewati Better Lyrics (judul lagu tidak dikirim ke sana). Bila semua sumber gagal karena
    jaringan, galat pertama dilempar supaya tampilan bisa menawarkan Coba lagi.
    """
    title, artist = query_for(track)
    if not title or (seconds and seconds > 3600):  # lebih dari sejam: set DJ atau mix, tidak ada yang menyimpannya
        return {"found": False, "v": VERSION}
    fallback, errors, asked = None, [], 0
    for name, source in SOURCES:
        if name == "Better Lyrics" and not words:
            continue
        asked += 1
        try:
            hit = source(title, artist, seconds, track)
        except Exception as exc:  # satu sumber mati tidak boleh menghentikan yang lain
            errors.append(exc)
            continue
        if not hit:
            continue
        hit = dict(hit, source=name, v=VERSION)
        if hit.get("instrumental") or hit.get("lines"):
            return hit
        if fallback is None and hit.get("plain"):
            fallback = hit
    if fallback:
        return fallback
    if errors and len(errors) == asked:
        raise errors[0]
    return {"found": False, "v": VERSION}


class LyricsCache:
    """Lirik yang sudah pernah dicari, supaya memutar ulang lagu tidak bertanya lagi ke sumbernya."""
    LIMIT = 300

    def __init__(self, path):
        self.path = path
        self.data = read_json(path, {})

    def get(self, key):
        value = self.data.get(key)
        if value and not value.get("found") and value.get("v", 1) < VERSION:
            return None  # dulu hanya LRCLIB yang ditanya; sekarang ada sumber lain
        if value and value.get("lines"):
            value = dict(value, lines=[tuple(line) for line in value["lines"]])
        return value

    def put(self, key, value):
        self.data.pop(key, None)
        self.data[key] = value
        while len(self.data) > self.LIMIT:
            self.data.pop(next(iter(self.data)))
        write_json(self.path, self.data)
