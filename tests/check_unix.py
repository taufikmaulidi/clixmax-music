"""Uji jalur Linux ClixMax yang tidak butuh tampilan (tanpa tkinter dan mpv), misalnya di Ubuntu WSL.

Jalankan dari folder proyek: python3 tests/check_unix.py
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from clixmax import config, library, music, player, system  # noqa: E402

results = []


def check(name, ok, detail=""):
    results.append(bool(ok))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name, ("  [%s]" % detail) if detail else ""), flush=True)


check("deteksi OS: Linux", system.LINUX and not system.WINDOWS and not system.MAC, sys.platform)
check("folder data mengikuti XDG", system.data_dir() == os.path.join(
    os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"), "clixmax"), system.data_dir())
check("lokasi berkas config ada di folder data", config.CFG.startswith(system.data_dir()) and config.OLD_CFG is None)
check("tanpa flag jendela Windows", system.HIDDEN == 0)
check("pintasan Ctrl dan pilih-banyak Ctrl", system.SHORTCUT == "Control" and system.MULTI_SELECT == 0x4)
check("petunjuk pasang mpv untuk Linux", "apt" in system.install_hint("mpv"), system.install_hint("mpv"))

path = system.ipc_path("clixmax-uji")
check("alamat kendali mpv berupa Unix socket", path.endswith(".sock") and os.path.isabs(path), path)
try:
    system.ipc_connect(path).close()
    refused = False
except OSError:
    refused = True
check("sambung sebelum mpv jalan: ditolak (OSError)", refused)
open(path, "w").close()
try:
    system.ipc_connect(path).close()
    stale = False
except OSError:
    stale = True
system.ipc_cleanup(path)
check("berkas socket basi: ditolak lalu dibersihkan", stale and not os.path.exists(path))

server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
server.bind(path)
server.listen(1)
seen = []


def fake_mpv():
    """Meniru mpv: kirim pesan event dulu, lalu jawaban dengan request_id yang sama."""
    conn, _ = server.accept()
    buf = b""
    while True:
        data = conn.recv(4096)
        if not data:
            break
        buf += data
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            request = json.loads(line)
            seen.append(request["command"])
            if request["command"][0] == "quit":
                conn.close()
                return
            conn.sendall(b'{"event":"playback-restart"}\n')
            reply = {"data": request["command"][-1], "request_id": request.get("request_id"), "error": "success"}
            conn.sendall(json.dumps(reply).encode() + b"\n")


worker = threading.Thread(target=fake_mpv, daemon=True)
worker.start()
mpv = player.Mpv()
mpv.pipe = system.ipc_connect(path)
check("perintah ke mpv lewat Unix socket, pesan event dilewati",
      mpv.get("volume") == "volume" and mpv.get("pause") == "pause"
      and mpv.cmd("loadfile", "https://x", "append")["error"] == "success")
mpv.proc = None
mpv.stop()
worker.join(2)
check("berhenti: perintah quit terkirim dan socket ditutup", seen and seen[-1] == ["quit"] and not worker.is_alive())
server.close()
system.ipc_cleanup(path)

probe = ("import sys, time; sys.path.insert(0, %r); from clixmax import system; "
         "print(system.single_instance('clixmax-uji'), flush=True); time.sleep(float(sys.argv[1]))" % ROOT)
first = subprocess.Popen([sys.executable, "-c", probe, "3"], stdout=subprocess.PIPE, text=True)
got_first = first.stdout.readline().strip()
got_second = subprocess.run([sys.executable, "-c", probe, "0"], capture_output=True, text=True).stdout.strip()
first.wait()
got_third = subprocess.run([sys.executable, "-c", probe, "0"], capture_output=True, text=True).stdout.strip()
check("satu instance: yang kedua ditolak, setelah yang pertama tutup boleh lagi",
      (got_first, got_second, got_third) == ("True", "False", "True"), "%s %s %s" % (got_first, got_second, got_third))
lock = os.path.join(system.data_dir(), "clixmax-uji.lock")
if os.path.exists(lock):
    os.remove(lock)
if os.path.isdir(system.data_dir()) and not os.listdir(system.data_dir()):
    os.rmdir(system.data_dir())

check("cari program lewat PATH", player.find_exe("python3") == shutil.which("python3"), player.find_exe("python3"))
check("program yang tidak ada: None", player.find_exe("tidak-ada-xyz") is None)
try:
    player.find_exe = lambda name: None
    player.Mpv().start(70)
    message = ""
except RuntimeError as exc:
    message = str(exc)
check("mpv belum terpasang: pesan jelas dengan perintah apt", "mpv tidak ditemukan" in message and "apt" in message,
      message)

work = tempfile.mkdtemp()
lib = library.Library(os.path.join(work, "library.json"))
song = {"id": "abcdefghijk", "title": "Uji", "artist": "A", "dur": "3:00", "art": None, "kind": "song",
        "url": "https://music.youtube.com/watch?v=abcdefghijk", "tag": "Lagu"}
liked = lib.toggle_fav(song)
index = lib.create("Daftar")
added = lib.add_to(index, [song, song])
again = library.Library(os.path.join(work, "library.json"))
check("pustaka tersimpan dan terbaca ulang (path Linux)", liked and added == 1 and again.is_fav(song)
      and again.playlists[0]["tracks"][0]["kind"] == "song" and "tag" not in again.favorites[0])
library.save_session(os.path.join(work, "session.json"), [song], 0, 61.5)
check("sesi tersimpan dan terbaca ulang", library.load_session(os.path.join(work, "session.json"))[1:] == (0, 61.5))
shutil.rmtree(work)
check("link satu video dikenali", (music.single_link("https://youtu.be/abcdefghijk") or {}).get("id") == "abcdefghijk")

print("\n%d dari %d lolos" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
