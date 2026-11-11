"""Bangun ClixMax untuk OS yang sedang dipakai, dengan PyInstaller.

    pip install -r requirements.txt -r packaging/requirements-build.txt
    python packaging/build.py

Hasil di dist/:
- Windows: ClixMax-windows-x64-setup.exe (installer, butuh Inno Setup 6: winget install JRSoftware.InnoSetup)
           dan ClixMax-windows-x64.zip (tanpa dipasang). libmpv ikut di bin/ dan yt-dlp ikut sebagai modul
           Python; keduanya berjalan di dalam ClixMax.exe, jadi Task Manager hanya menampilkan satu proses.
- Linux:   ClixMax-linux-x64.deb (apt sekalian memasang libmpv dari distro) dan ClixMax-linux-x64.tar.gz
           (mpv dipasang sendiri: sudo apt install mpv).
- macOS:   ClixMax-macos-arm64.dmg dan .zip berisi ClixMax.app; mpv dari Homebrew (brew install mpv).
Di Linux dan macOS libmpv dari sistem dimuat di dalam proses ClixMax juga; program yt-dlp yang ikut di bin/
hanya cadangan bila libmpv itu tidak bisa dimuat dan ClixMax kembali menjalankan program mpv.

mpv dan yt-dlp yang diunduh dikunci ke versi tertentu dan diperiksa SHA-256-nya, supaya build bisa diulang
dan berkas yang ikut dibagikan tidak bisa ditukar diam-diam. Modul yt-dlp dikunci di requirements-build.txt.
"""
import hashlib
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUILD = os.path.join(ROOT, "build")
DIST = os.path.join(ROOT, "dist")
sys.path.insert(0, ROOT)

WINDOWS, MAC = sys.platform == "win32", sys.platform == "darwin"
# Versi rilis: dari tag v* di CI (lihat .github/workflows/build.yml), selain itu versi pengembangan.
VERSION = os.environ.get("CLIXMAX_VERSION") or "0.0.0-dev"
# Sama dengan versi modul yt-dlp di packaging/requirements-build.txt (dicek di main).
YTDLP_VERSION = "2026.10.26"
YTDLP = {  # program yt-dlp untuk mpv di macOS/Linux: nama berkas rilis, SHA-256
    "linux": ("yt-dlp_linux", "767ba9dce7052aa196f8b12652f433d76de128ba168966fa84b6394d5e6c6795"),
    "darwin": ("yt-dlp_macos", "0f922c15ccc0b83eefa1c8bc9104e434318c4bf16e408e1ee93b7745a6efe0aa"),
}
LIBMPV_WINDOWS = ("https://github.com/shinchiro/mpv-winbuild-cmake/releases/download/20261021/"
                  "mpv-dev-x86_64-20261021-git-e471496c56.7z",
                  "efc719eff3dc5954b4a5efc800632808bcec01cc9034940dd14e5eb7fe9ea633")
MPV_NOTE = """libmpv-2.dll di folder ini adalah build dari shinchiro/mpv-winbuild-cmake rilis 20261021
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
    """Yang ikut dibagikan di bin/: libmpv di Windows (yt-dlp ikut sebagai modul), program yt-dlp di lainnya."""
    os.makedirs(bin_dir, exist_ok=True)
    note = YTDLP_NOTE % YTDLP_VERSION
    if WINDOWS:
        archive = os.path.join(BUILD, "mpv-dev.7z")
        download(LIBMPV_WINDOWS[0], archive, LIBMPV_WINDOWS[1])
        # Arsip mpv memakai filter BCJ2 yang tidak bisa dibuka modul Python; 7-Zip ada di mesin build GitHub.
        seven = shutil.which("7z") or os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "7-Zip",
                                                   "7z.exe")
        if not os.path.exists(seven):
            raise SystemExit("7-Zip dibutuhkan untuk membuka arsip mpv: winget install 7zip.7zip")
        subprocess.run([seven, "e", "-y", "-o" + bin_dir, archive, "libmpv-2.dll"], check=True,
                       stdout=subprocess.DEVNULL)
        if not os.path.exists(os.path.join(bin_dir, "libmpv-2.dll")):
            raise SystemExit("libmpv-2.dll tidak ada di arsip mpv")
        note = MPV_NOTE + "\n" + note
    else:
        name, sha = YTDLP[sys.platform]
        target = os.path.join(bin_dir, "yt-dlp")
        download("https://github.com/yt-dlp/yt-dlp/releases/download/%s/%s" % (YTDLP_VERSION, name), target, sha)
        os.chmod(target, 0o755)
    with open(os.path.join(bin_dir, "PROGRAM-PENDAMPING.txt"), "w", encoding="utf-8") as f:
        f.write(note)


def find_iscc():
    """Pengompilasi Inno Setup: dari PATH, pemasangan biasa, atau pemasangan per pengguna lewat winget."""
    places = [os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"),
              os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs")]
    for path in [shutil.which("iscc")] + [os.path.join(p, "Inno Setup 6", "ISCC.exe") for p in places if p]:
        if path and os.path.isfile(path):
            return path
    raise SystemExit("Inno Setup 6 dibutuhkan untuk membuat installer: winget install JRSoftware.InnoSetup")


def version_file(path, numbers):
    """Keterangan berkas ClixMax.exe: nama yang tampil di Task Manager dan versi di Properties."""
    fields = {"FileDescription": "ClixMax", "ProductName": "ClixMax", "InternalName": "ClixMax",
              "OriginalFilename": "ClixMax.exe", "FileVersion": VERSION, "ProductVersion": VERSION,
              "LegalCopyright": "GPLv3"}
    with open(path, "w", encoding="utf-8") as f:
        f.write("VSVersionInfo(ffi=FixedFileInfo(filevers=%r, prodvers=%r), kids=[StringFileInfo([StringTable("
                "'040904B0', [%s])]), VarFileInfo([VarStruct('Translation', [1033, 1200])])])\n"
                % (numbers, numbers, ", ".join("StringStruct(%r, %r)" % item for item in fields.items())))


def main():
    from clixmax.artwork import make_icon
    import PyInstaller.__main__
    import yt_dlp.version

    if yt_dlp.version.__version__ != YTDLP_VERSION:
        raise SystemExit("modul yt-dlp %s terpasang, build ini memakai %s: pip install -r "
                         "packaging/requirements-build.txt" % (yt_dlp.version.__version__, YTDLP_VERSION))
    iscc = find_iscc() if WINDOWS else None  # gagal di awal, bukan setelah PyInstaller selesai
    numbers = tuple(int(n) for n in re.findall(r"\d+", VERSION)[:3]) + (0,)
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
        version_file(os.path.join(BUILD, "version.txt"), numbers)
        args += ["--icon", ico, "--collect-submodules", "winrt", "--version-file", os.path.join(BUILD, "version.txt")]
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
        print("hasil:", out, "%.1f MB" % (os.path.getsize(out) / 1048576), flush=True)
        name = "ClixMax-windows-%s-setup" % arch
        subprocess.run([iscc, "/Q", "/DAppVersion=" + VERSION, "/DNumericVersion=%d.%d.%d.%d" % numbers,
                        "/DSourceDir=" + app, "/DOutputDir=" + DIST, "/DOutputName=" + name, "/DIconFile=" + ico,
                        os.path.join(ROOT, "packaging", "clixmax.iss")], check=True)
        out = os.path.join(DIST, name + ".exe")
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
        print("hasil:", out, "%.1f MB" % (os.path.getsize(out) / 1048576), flush=True)
        out = disk_image(app, os.path.join(DIST, "ClixMax-macos-%s.dmg" % arch))
    else:
        out = shutil.make_archive(os.path.join(DIST, "ClixMax-linux-%s" % arch), "gztar", DIST, "ClixMax")
        print("hasil:", out, "%.1f MB" % (os.path.getsize(out) / 1048576), flush=True)
        out = deb_package(app, png, arch, os.path.join(DIST, "ClixMax-linux-%s.deb" % arch))
    print("hasil:", out, "%.1f MB" % (os.path.getsize(out) / 1048576), flush=True)


def disk_image(app, out):
    """Image disk macOS berisi ClixMax.app dan pintasan ke Applications: dibuka, lalu ClixMax diseret ke sana."""
    stage = os.path.join(BUILD, "dmg")
    shutil.rmtree(stage, ignore_errors=True)
    os.makedirs(stage)
    subprocess.run(["ditto", app, os.path.join(stage, "ClixMax.app")], check=True)  # ditto menjaga tanda tangan
    os.symlink("/Applications", os.path.join(stage, "Applications"))
    command = ["hdiutil", "create", "-volname", "ClixMax", "-srcfolder", stage, "-ov", "-format", "UDZO", out]
    for attempt in range(3):  # hdiutil di mesin build GitHub kadang gagal sesaat ("Resource busy")
        if subprocess.run(command).returncode == 0:
            return out
        time.sleep(5)
    raise SystemExit("hdiutil gagal membuat %s" % out)


DESKTOP = """[Desktop Entry]
Type=Application
Name=ClixMax
GenericName=Pemutar musik
Comment=Pemutar YouTube Music yang hemat RAM
Exec=clixmax
Icon=clixmax
Terminal=false
Categories=AudioVideo;Audio;Player;
StartupWMClass=ClixMax
"""
CONTROL = """Package: clixmax
Version: %(version)s
Architecture: %(arch)s
Maintainer: ClixMax <https://github.com/taufikmaulidi/clixmax-music>
Installed-Size: %(size)d
Depends: libc6 (>= 2.39), libmpv2
Recommends: mpv
Section: sound
Priority: optional
Homepage: https://github.com/taufikmaulidi/clixmax-music
Description: Pemutar YouTube Music yang hemat RAM
 Memutar audio saja dari YouTube Music dan musik di folder sendiri, dengan lirik
 tersinkron, antrean, dan pulau mini.
"""


def deb_package(app, icon, arch, out):
    """Paket .deb untuk Ubuntu 24.04+/Debian 13+: ClixMax di /opt/clixmax, perintah clixmax, dan menu aplikasi.

    libmpv2 jadi kebutuhan paket, jadi apt sekalian memasang mpv dari distro; ClixMax memuatnya di dalam prosesnya
    sendiri. Program mpv (Recommends) hanya cadangan bila libmpv dari distro tidak bisa dimuat.
    """
    root = os.path.join(BUILD, "deb")
    shutil.rmtree(root, ignore_errors=True)
    shutil.copytree(app, os.path.join(root, "opt", "clixmax"), symlinks=True)
    for folder in ("DEBIAN", "usr/bin", "usr/share/applications", "usr/share/icons/hicolor/256x256/apps"):
        os.makedirs(os.path.join(root, folder))
    os.symlink("/opt/clixmax/ClixMax", os.path.join(root, "usr", "bin", "clixmax"))
    with open(os.path.join(root, "usr", "share", "applications", "clixmax.desktop"), "w", encoding="utf-8") as f:
        f.write(DESKTOP)
    shutil.copy2(icon, os.path.join(root, "usr", "share", "icons", "hicolor", "256x256", "apps", "clixmax.png"))
    size = sum(os.path.getsize(os.path.join(d, n)) for d, _, names in os.walk(root) for n in names
               if not os.path.islink(os.path.join(d, n)))
    with open(os.path.join(root, "DEBIAN", "control"), "w", encoding="utf-8") as f:
        f.write(CONTROL % {"version": VERSION.replace("-", "~"), "arch": {"x64": "amd64"}.get(arch, arch),
                           "size": size // 1024})
    subprocess.run(["dpkg-deb", "--root-owner-group", "-Zxz", "--build", root, out], check=True)
    return out


if __name__ == "__main__":
    main()
