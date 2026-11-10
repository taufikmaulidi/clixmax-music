"""Bangun ClixMax untuk OS yang sedang dipakai, dengan PyInstaller.

    pip install -r requirements.txt -r packaging/requirements-build.txt
    python packaging/build.py

Hasil di dist/:
- Windows: ClixMax-windows-x64.zip. mpv dan yt-dlp ikut di bin/, jadi tidak perlu memasang apa pun.
- Linux:   ClixMax-linux-x64.tar.gz. yt-dlp ikut; mpv dipasang dari distro (sudo apt install mpv).
- macOS:   ClixMax-macos-arm64.zip berisi ClixMax.app. yt-dlp ikut; mpv dari Homebrew (brew install mpv).

mpv dan yt-dlp yang diunduh dikunci ke versi tertentu dan diperiksa SHA-256-nya, supaya build bisa diulang
dan berkas yang ikut dibagikan tidak bisa ditukar diam-diam.
"""
import hashlib
import os
import platform
import shutil
import subprocess
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "build")
DIST = os.path.join(ROOT, "dist")
sys.path.insert(0, ROOT)

WINDOWS, MAC = sys.platform == "win32", sys.platform == "darwin"
# Versi rilis: dari tag v* di CI (lihat .github/workflows/build.yml), selain itu versi pengembangan.
VERSION = os.environ.get("CLIXMAX_VERSION") or "0.0.0-dev"
YTDLP_VERSION = "2026.10.26"
YTDLP = {  # nama berkas rilis, SHA-256
    "win32": ("yt-dlp.exe", "f5389d3698ecde4ef06f4e6b1ce0294fe9ac1396228c8990b8d3416d6d177a7d"),
    "linux": ("yt-dlp_linux", "767ba9dce7052aa196f8b12652f433d76de128ba168966fa84b6394d5e6c6795"),
    "darwin": ("yt-dlp_macos", "0f922c15ccc0b83eefa1c8bc9104e434318c4bf16e408e1ee93b7745a6efe0aa"),
}
MPV_WINDOWS = ("https://github.com/shinchiro/mpv-winbuild-cmake/releases/download/20261021/"
               "mpv-x86_64-20261021-git-e471496c56.7z",
               "4a355f3e89c83fabc730d33fb4e759dfec747806ed2287b61a90d1681b83e8d3")
MPV_NOTE = """mpv untuk Windows di folder ini adalah build dari shinchiro/mpv-winbuild-cmake rilis 20261021
(https://github.com/shinchiro/mpv-winbuild-cmake/releases/tag/20261021), dibagikan ulang tanpa diubah.
mpv berlisensi GPLv2 atau lebih baru; kode sumbernya di https://github.com/mpv-player/mpv dan
skrip build-nya di https://github.com/shinchiro/mpv-winbuild-cmake.
"""
YTDLP_NOTE = "yt-dlp %s (https://github.com/yt-dlp/yt-dlp) berlisensi Unlicense, dibagikan ulang tanpa diubah.\n"


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def download(url, path, sha256):
    if not (os.path.exists(path) and digest(path) == sha256):
        print("unduh", url, flush=True)
        request = urllib.request.Request(url, headers={"User-Agent": "clixmax-build"})
        with urllib.request.urlopen(request, timeout=300) as reply, open(path, "wb") as out:
            shutil.copyfileobj(reply, out)
    found = digest(path)
    if found != sha256:
        os.remove(path)
        raise SystemExit("SHA-256 %s tidak cocok: %s, seharusnya %s" % (os.path.basename(path), found, sha256))


def tools(bin_dir):
    """Program pendamping yang ikut dibagikan: yt-dlp di semua OS, mpv di Windows."""
    os.makedirs(bin_dir, exist_ok=True)
    name, sha = YTDLP[sys.platform]
    target = os.path.join(bin_dir, "yt-dlp.exe" if WINDOWS else "yt-dlp")
    download("https://github.com/yt-dlp/yt-dlp/releases/download/%s/%s" % (YTDLP_VERSION, name), target, sha)
    os.chmod(target, 0o755)
    note = YTDLP_NOTE % YTDLP_VERSION
    if WINDOWS:
        archive = os.path.join(BUILD, "mpv.7z")
        download(MPV_WINDOWS[0], archive, MPV_WINDOWS[1])
        unpacked = os.path.join(BUILD, "mpv")
        shutil.rmtree(unpacked, ignore_errors=True)
        # Arsip mpv memakai filter BCJ2 yang tidak bisa dibuka modul Python; 7-Zip ada di mesin build GitHub.
        seven = shutil.which("7z") or os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "7-Zip",
                                                   "7z.exe")
        if not os.path.exists(seven):
            raise SystemExit("7-Zip dibutuhkan untuk membuka arsip mpv: winget install 7zip.7zip")
        subprocess.run([seven, "x", "-y", "-o" + unpacked, archive], check=True, stdout=subprocess.DEVNULL)
        for entry in os.listdir(unpacked):
            if entry.lower() in ("mpv.exe", "mpv.com") or entry.lower().endswith(".dll"):
                shutil.copy2(os.path.join(unpacked, entry), bin_dir)
        if not os.path.exists(os.path.join(bin_dir, "mpv.exe")):
            raise SystemExit("mpv.exe tidak ada di arsip mpv")
        note = MPV_NOTE + "\n" + note
    with open(os.path.join(bin_dir, "PROGRAM-PENDAMPING.txt"), "w", encoding="utf-8") as f:
        f.write(note)


def main():
    from clixmax.artwork import make_icon
    import PyInstaller.__main__

    shutil.rmtree(DIST, ignore_errors=True)
    os.makedirs(BUILD, exist_ok=True)
    ico, png = os.path.join(BUILD, "clixmax.ico"), os.path.join(BUILD, "clixmax.png")
    make_icon(ico, png)
    bin_dir = os.path.join(BUILD, "bin")
    shutil.rmtree(bin_dir, ignore_errors=True)
    tools(bin_dir)

    args = [os.path.join(ROOT, "start.pyw"), "--name", "ClixMax", "--windowed", "--noconfirm", "--clean",
            "--distpath", DIST, "--workpath", os.path.join(BUILD, "pyinstaller"), "--specpath", BUILD,
            "--collect-data", "ytmusicapi", "--collect-submodules", "pystray",
            "--hidden-import", "PIL._tkinter_finder"]
    if WINDOWS:
        args += ["--icon", ico, "--collect-submodules", "winrt"]
    elif MAC:
        args += ["--icon", png, "--hidden-import", "MediaPlayer",
                 "--osx-bundle-identifier", "io.github.taufikmaulidi.clixmax"]
    else:
        args += ["--collect-submodules", "dbus_next"]
    PyInstaller.__main__.run(args)

    if MAC:
        app = os.path.join(DIST, "ClixMax.app")
        home = os.path.join(app, "Contents", "MacOS")
        extras = os.path.join(app, "Contents", "Resources")
    else:
        app = home = extras = os.path.join(DIST, "ClixMax")
    shutil.copytree(bin_dir, os.path.join(home, "bin"))
    for path in os.listdir(os.path.join(home, "bin")):
        os.chmod(os.path.join(home, "bin", path), 0o755)
    for name in ("LICENSE", "README.md"):
        shutil.copy2(os.path.join(ROOT, name), extras)

    machine = platform.machine().lower()
    arch = {"amd64": "x64", "x86_64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(machine, machine)
    if WINDOWS:
        out = shutil.make_archive(os.path.join(DIST, "ClixMax-windows-%s" % arch), "zip", DIST, "ClixMax")
    elif MAC:
        import plistlib
        info = os.path.join(app, "Contents", "Info.plist")
        with open(info, "rb") as f:
            plist = plistlib.load(f)
        # Versi minimum ditulis jelas (semua biner di dalamnya dibangun untuk macOS 11 ke atas), dan versi
        # aplikasi diisi supaya Finder dan "About" tidak menampilkan 0.0.0.
        plist.update(LSMinimumSystemVersion="11.0", CFBundleShortVersionString=VERSION, CFBundleVersion=VERSION,
                     CFBundleName="ClixMax", CFBundleDisplayName="ClixMax", NSHighResolutionCapable=True)
        with open(info, "wb") as f:
            plistlib.dump(plist, f)
        # Bundel diubah setelah PyInstaller (bin/, LICENSE, Info.plist): tanda tangan ad-hoc diperbarui supaya sah.
        subprocess.run(["codesign", "--force", "--deep", "--sign", "-", app], check=True)
        out = os.path.join(DIST, "ClixMax-macos-%s.zip" % arch)
        subprocess.run(["ditto", "-c", "-k", "--keepParent", app, out], check=True)
    else:
        out = shutil.make_archive(os.path.join(DIST, "ClixMax-linux-%s" % arch), "gztar", DIST, "ClixMax")
    print("hasil:", out, "%.1f MB" % (os.path.getsize(out) / 1048576), flush=True)


if __name__ == "__main__":
    main()
