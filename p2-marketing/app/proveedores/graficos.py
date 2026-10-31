"""Utilidades de imagen: carga segura, análisis de color, recortes, tipografía."""
from __future__ import annotations

import colorsys
import io
import re
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps, ImageStat

try:  # fotos HEIC de iPhone
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:  # pragma: no cover
    pass

_FUENTES = {
    True: [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ],
    False: [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ],
}

_COLORES_NOMBRADOS = {
    "rojo": (200, 40, 40), "naranja": (235, 130, 30), "amarillo": (235, 205, 50),
    "verde": (60, 150, 70), "turquesa": (40, 170, 170), "azul": (40, 90, 200),
    "morado": (120, 60, 170), "rosado": (230, 120, 170), "marrón": (120, 75, 40),
    "beige": (220, 200, 165), "negro": (20, 20, 20), "blanco": (245, 245, 245), "gris": (128, 128, 128),
}


class FotoInvalida(ValueError):
    pass


def cargar_foto(datos: bytes, lado_minimo: int = 300) -> Image.Image:
    try:
        imagen = Image.open(io.BytesIO(datos))
        imagen = ImageOps.exif_transpose(imagen)  # respeta la orientación del celular
        imagen = imagen.convert("RGB")
    except Exception as error:
        raise FotoInvalida("El archivo no es una imagen válida (usa JPG, PNG, WEBP o HEIC).") from error
    if min(imagen.size) < lado_minimo:
        raise FotoInvalida(f"La foto es muy pequeña: mínimo {lado_minimo}px por lado.")
    return imagen


@lru_cache(maxsize=64)
def fuente(tamano: int, negrita: bool = True) -> ImageFont.FreeTypeFont:
    for ruta in _FUENTES[negrita]:
        if Path(ruta).exists():
            return ImageFont.truetype(ruta, tamano)
    return ImageFont.load_default(size=tamano)


def limpiar_texto(texto: str) -> str:
    """Quita emojis y símbolos que las fuentes del contenedor no pueden dibujar."""
    texto = re.sub(r"[\U00010000-\U0010FFFF\u2600-\u27BF\uFE0F\u200D]", "", texto or "")
    return re.sub(r"\s+", " ", texto).strip()


def envolver(texto: str, letra: ImageFont.FreeTypeFont, ancho_max: int, max_lineas: int | None = None) -> list[str]:
    palabras = limpiar_texto(texto).split()
    lineas: list[str] = []
    actual = ""
    for palabra in palabras:
        prueba = f"{actual} {palabra}".strip()
        if letra.getlength(prueba) <= ancho_max or not actual:
            actual = prueba
        else:
            lineas.append(actual)
            actual = palabra
    if actual:
        lineas.append(actual)
    if max_lineas and len(lineas) > max_lineas:
        lineas = lineas[:max_lineas]
        lineas[-1] = lineas[-1].rstrip(".,;:") + "…"
    return lineas


def texto_ajustado(texto: str, ancho_max: int, max_lineas: int, tamano: int, minimo: int = 34,
                   negrita: bool = True) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    """Reduce el tamaño de letra hasta que el texto quepa en max_lineas."""
    while True:
        letra = fuente(tamano, negrita)
        lineas = envolver(texto, letra, ancho_max)
        if len(lineas) <= max_lineas or tamano <= minimo:
            return letra, envolver(texto, letra, ancho_max, max_lineas)
        tamano -= 4


def dibujar_lineas(dibujo: ImageDraw.ImageDraw, lineas: list[str], letra, x: int, y: int,
                   color, interlineado: float = 1.18, centrado_en: int | None = None, sombra: bool = False) -> int:
    alto = int(letra.size * interlineado)
    for linea in lineas:
        px = x if centrado_en is None else int(centrado_en - letra.getlength(linea) / 2)
        if sombra:
            dibujo.text((px + 3, y + 3), linea, font=letra, fill=(0, 0, 0, 140))
        dibujo.text((px, y), linea, font=letra, fill=color)
        y += alto
    return y


def cubrir(imagen: Image.Image, ancho: int, alto: int) -> Image.Image:
    return ImageOps.fit(imagen, (ancho, alto), method=Image.Resampling.LANCZOS, centering=(0.5, 0.45))


def contener(imagen: Image.Image, ancho: int, alto: int) -> Image.Image:
    copia = imagen.copy()
    copia.thumbnail((ancho, alto), Image.Resampling.LANCZOS)
    return copia


def fondo_desenfocado(imagen: Image.Image, ancho: int, alto: int, oscurecer: float = 0.45) -> Image.Image:
    fondo = cubrir(imagen, ancho // 4, alto // 4).filter(ImageFilter.GaussianBlur(8)).resize((ancho, alto))
    capa = Image.new("RGB", (ancho, alto), (0, 0, 0))
    return Image.blend(fondo, capa, oscurecer)


def esquinas_redondeadas(imagen: Image.Image, radio: int) -> Image.Image:
    mascara = Image.new("L", imagen.size, 0)
    ImageDraw.Draw(mascara).rounded_rectangle((0, 0, *imagen.size), radio, fill=255)
    salida = imagen.convert("RGBA")
    salida.putalpha(mascara)
    return salida


def degradado_inferior(ancho: int, alto: int, desde: float = 0.35, opacidad: int = 225) -> Image.Image:
    capa = Image.new("RGBA", (ancho, alto), (0, 0, 0, 0))
    dibujo = ImageDraw.Draw(capa)
    inicio = int(alto * desde)
    for y in range(inicio, alto):
        alfa = int(opacidad * ((y - inicio) / (alto - inicio)) ** 1.4)
        dibujo.line([(0, y), (ancho, y)], fill=(0, 0, 0, alfa))
    return capa


def paleta(imagen: Image.Image, colores: int = 5) -> list[str]:
    pequena = imagen.copy()
    pequena.thumbnail((160, 160))
    cuantizada = pequena.quantize(colors=colores, method=Image.Quantize.MEDIANCUT)
    paleta_rgb = cuantizada.getpalette()[: colores * 3]
    conteo = sorted(cuantizada.getcolors(), reverse=True)
    salida = []
    for _, indice in conteo:
        r, g, b = paleta_rgb[indice * 3: indice * 3 + 3]
        salida.append(f"#{r:02x}{g:02x}{b:02x}")
    return salida


def hex_a_rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def color_acento(colores: list[str]) -> tuple[int, int, int]:
    """El color más saturado de la paleta, ajustado para que sirva de fondo de texto."""
    mejor, puntaje = (47, 107, 255), -1.0
    for color in colores:
        r, g, b = hex_a_rgb(color)
        h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
        valor = s * (1 - abs(l - 0.5))
        if valor > puntaje:
            mejor, puntaje = (r, g, b), valor
    if puntaje < 0.12:  # foto casi sin color: usamos un azul de marca
        return (36, 72, 190)
    h, l, s = colorsys.rgb_to_hls(*(c / 255 for c in mejor))
    r, g, b = colorsys.hls_to_rgb(h, min(max(l, 0.32), 0.45), max(s, 0.55))
    return int(r * 255), int(g * 255), int(b * 255)


def contraste(color: tuple[int, int, int]) -> tuple[int, int, int]:
    r, g, b = color
    luminancia = 0.299 * r + 0.587 * g + 0.114 * b
    return (20, 20, 20) if luminancia > 160 else (255, 255, 255)


def nombre_color(color: str) -> str:
    r, g, b = hex_a_rgb(color)
    return min(_COLORES_NOMBRADOS, key=lambda n: sum((a - c) ** 2 for a, c in zip((r, g, b), _COLORES_NOMBRADOS[n])))


def describir_foto(imagen: Image.Image, colores: list[str]) -> str:
    ancho, alto = imagen.size
    orientacion = "vertical" if alto > ancho * 1.05 else "horizontal" if ancho > alto * 1.05 else "cuadrada"
    gris = imagen.convert("L").resize((64, 64))
    brillo = ImageStat.Stat(gris).mean[0]
    luz = "muy luminosa" if brillo > 170 else "luminosa" if brillo > 120 else "de tonos oscuros"
    nombres = []
    for c in colores:
        n = nombre_color(c)
        if n not in nombres:
            nombres.append(n)
    return (f"Foto {orientacion} ({ancho}x{alto}), {luz}; colores predominantes: "
            f"{', '.join(nombres[:3])}.")
