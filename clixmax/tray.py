"""Ikon di system tray (Windows, Linux): menutup jendela tidak menghentikan musik.

Tidak dipakai di macOS: pystray di sana harus memegang thread utama, yang sudah dipakai Tk,
dan Dock sudah memberi jalan kembali ke jendela.
"""
import threading

from . import system


def available():
    if system.MAC:
        return False
    try:
        import pystray  # noqa: F401
        return True
    except Exception:
        return False


class Tray:
    """Menu: Tampilkan, Putar/Jeda, Berikutnya, Sebelumnya, Keluar. Aksi dikirim lewat on_action."""

    def __init__(self, icon_png, on_action):
        import pystray
        from PIL import Image
        self.playing = False
        item, menu = pystray.MenuItem, pystray.Menu
        self.icon = pystray.Icon("clixmax", Image.open(icon_png), "ClixMax", menu(
            item("Tampilkan ClixMax", lambda: on_action("show"), default=True),
            item(lambda _: "Jeda" if self.playing else "Putar", lambda: on_action("toggle")),
            item("Berikutnya", lambda: on_action("next")),
            item("Sebelumnya", lambda: on_action("prev")),
            menu.SEPARATOR,
            item("Keluar", lambda: on_action("quit"))))
        threading.Thread(target=self.icon.run, daemon=True).start()

    def set_playing(self, playing, title):
        label = ("ClixMax - %s" % title if title else "ClixMax")[:120]
        if playing != self.playing or label != self.icon.title:
            self.playing = playing
            self.icon.title = label
            self.icon.update_menu()

    def notify(self, text):
        try:
            self.icon.notify(text, "ClixMax")
        except Exception:
            pass

    def stop(self):
        try:
            self.icon.visible = False  # stop() saja tidak selalu menghapus ikon dari tray
            self.icon.stop()
        except Exception:
            pass
