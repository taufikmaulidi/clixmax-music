"""Efek suara lewat filter mpv: perataan volume dan nada.

Kecepatan memakai properti `speed` mpv (scaletempo2 menjaga nada), jadi tidak ada di sini.
mpv build Windows tidak punya filter rubberband, jadi nada digeser dengan filter FFmpeg biasa:
resample ke 48 kHz yang pasti, ubah sample rate (nada dan tempo naik), lalu kembalikan tempo.
"""

# Perataan dinamis: lagu pelan dinaikkan, lagu keras diturunkan, tanpa memotong puncak.
NORMALIZE = "lavfi=[dynaudnorm=f=500:g=31:p=0.9:m=10]"
RATE = 48000


def pitch_filter(semitones):
    if not semitones:
        return ""
    ratio = 2 ** (semitones / 12)
    return "lavfi=[aresample=%d,asetrate=%d,aresample=%d,atempo=%.5f]" % (RATE, round(RATE * ratio), RATE, 1 / ratio)


def chain(normalize, semitones):
    """Nilai properti `af` mpv untuk setelan ini (string kosong = tanpa filter)."""
    return ",".join(part for part in (NORMALIZE if normalize else "", pitch_filter(semitones)) if part)
