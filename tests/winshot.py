"""Tangkapan layar satu jendela Tk di Windows (PrintWindow), disimpan sebagai PNG tanpa pustaka tambahan."""
import ctypes
import struct
from ctypes import wintypes

from clixmax import theme


def capture(window, path):
    """Simpan isi jendela (termasuk bingkainya) ke path. Mengembalikan (lebar, tinggi)."""
    u, g = ctypes.windll.user32, ctypes.windll.gdi32
    vp = ctypes.c_void_p
    u.GetParent.restype, u.GetParent.argtypes = vp, [vp]
    u.GetDC.restype, u.GetDC.argtypes = vp, [vp]
    u.ReleaseDC.argtypes = [vp, vp]
    u.GetWindowRect.argtypes = [vp, ctypes.POINTER(wintypes.RECT)]
    u.PrintWindow.argtypes = [vp, vp, ctypes.c_uint]
    g.CreateCompatibleDC.restype, g.CreateCompatibleDC.argtypes = vp, [vp]
    g.CreateCompatibleBitmap.restype, g.CreateCompatibleBitmap.argtypes = vp, [vp, ctypes.c_int, ctypes.c_int]
    g.SelectObject.restype, g.SelectObject.argtypes = vp, [vp, vp]
    g.GetDIBits.argtypes = [vp, vp, ctypes.c_uint, ctypes.c_uint, vp, vp, ctypes.c_uint]
    g.DeleteObject.argtypes = [vp]
    g.DeleteDC.argtypes = [vp]
    window.update()
    hwnd = u.GetParent(window.winfo_id()) or window.winfo_id()
    rect = wintypes.RECT()
    u.GetWindowRect(hwnd, ctypes.byref(rect))
    w, h = rect.right - rect.left, rect.bottom - rect.top
    screen = u.GetDC(None)
    mem = g.CreateCompatibleDC(screen)
    bmp = g.CreateCompatibleBitmap(screen, w, h)
    old = g.SelectObject(mem, bmp)
    u.PrintWindow(hwnd, mem, 2)  # 2 = PW_RENDERFULLCONTENT, supaya isi jendela tanpa bingkai ikut tergambar
    g.SelectObject(mem, old)
    buf = ctypes.create_string_buffer(w * h * 4)
    info = struct.pack("<IiiHHIIiiII", 40, w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    g.GetDIBits(mem, bmp, 0, h, buf, info, 0)
    g.DeleteObject(bmp)
    g.DeleteDC(mem)
    u.ReleaseDC(None, screen)
    rows = []
    for y in range(h):
        row = bytearray(buf.raw[y * w * 4:(y + 1) * w * 4])
        row[0::4], row[2::4] = row[2::4], row[0::4]  # BGRA ke RGBA
        row[3::4] = b"\xff" * w
        rows.append(bytes(row))
    with open(path, "wb") as f:
        f.write(theme.png(w, h, rows))
    return w, h
