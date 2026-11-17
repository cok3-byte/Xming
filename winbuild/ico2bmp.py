"""Genera un BMP de 24 bits a partir de la imagen de 32 bits más grande de un .ico.

El código fuente publicado de Xming 6.9.0.31 no incluye X.bmp, que XWin.rc usa
como logotipo del diálogo "Acerca de". Se reconstruye desde X.ico, componiendo
el canal alfa sobre el color de fondo de los diálogos de Windows.

Uso: python ico2bmp.py entrada.ico salida.bmp [R,G,B]
"""
import struct
import sys


def best_32bpp_entry(data):
    count = struct.unpack_from("<H", data, 4)[0]
    best = None
    for i in range(count):
        w, h, _, _, _, bpp, size, off = struct.unpack_from("<BBBBHHII", data, 6 + 16 * i)
        w, h = w or 256, h or 256
        if data[off:off + 4] == b"\x89PNG":
            continue  # entradas PNG no soportadas: no aparecen en X.ico
        if bpp == 32 and (best is None or w > best[0]):
            best = (w, h, off)
    if best is None:
        sys.exit("No hay ninguna imagen DIB de 32 bits en el icono")
    return best


def convert(src, dst, background):
    data = open(src, "rb").read()
    w, h, off = best_32bpp_entry(data)
    header_size = struct.unpack_from("<I", data, off)[0]
    pixels = data[off + header_size:off + header_size + w * h * 4]  # BGRA, de abajo arriba

    row_size = (w * 3 + 3) & ~3
    out = bytearray()
    br, bg, bb = background
    for y in range(h):
        row = bytearray()
        for x in range(w):
            b, g, r, a = pixels[(y * w + x) * 4:(y * w + x) * 4 + 4]
            row += bytes((
                (b * a + bb * (255 - a)) // 255,
                (g * a + bg * (255 - a)) // 255,
                (r * a + br * (255 - a)) // 255,
            ))
        out += row + b"\0" * (row_size - len(row))

    info = struct.pack("<IiiHHIIiiII", 40, w, h, 1, 24, 0, len(out), 2835, 2835, 0, 0)
    file_header = struct.pack("<2sIHHI", b"BM", 14 + len(info) + len(out), 0, 0, 14 + len(info))
    with open(dst, "wb") as f:
        f.write(file_header + info + out)


if __name__ == "__main__":
    if len(sys.argv) not in (3, 4):
        sys.exit(__doc__)
    color = tuple(int(c) for c in sys.argv[3].split(",")) if len(sys.argv) == 4 else (240, 240, 240)
    convert(sys.argv[1], sys.argv[2], color)
