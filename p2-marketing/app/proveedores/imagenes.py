"""Generación de las 3 fotos de la campaña (una por escena del guion elegido)."""
from __future__ import annotations

import base64
import io
import logging
from typing import Protocol

from PIL import Image, ImageDraw, ImageEnhance

from app.dominio.entidades import Brief, Guion
from app.proveedores import graficos as g
from app.proveedores.guiones import ErrorProveedor

log = logging.getLogger(__name__)

ANCHO, ALTO = 1080, 1350  # 4:5, formato recomendado para el feed


class GeneradorImagenes(Protocol):
    nombre: str

    def generar(self, foto: Image.Image, brief: Brief, guion: Guion, paleta: list[str]) -> list[Image.Image]: ...


def _marca(dibujo: ImageDraw.ImageDraw, empresa: str, acento, x: int, y: int) -> None:
    letra = g.fuente(34)
    texto = g.limpiar_texto(empresa).upper()[:28]
    ancho = int(letra.getlength(texto))
    dibujo.rounded_rectangle((x, y, x + ancho + 44, y + 60), 30, fill=acento)
    dibujo.text((x + 22, y + 11), texto, font=letra, fill=g.contraste(acento))


def disenar_gancho(base: Image.Image, titular: str, empresa: str, acento) -> Image.Image:
    """Foto a sangre completa con degradado y titular grande abajo."""
    lienzo = g.cubrir(base, ANCHO, ALTO).convert("RGBA")
    lienzo.alpha_composite(g.degradado_inferior(ANCHO, ALTO, 0.38))
    dibujo = ImageDraw.Draw(lienzo)
    _marca(dibujo, empresa, acento, 60, 60)
    letra, lineas = g.texto_ajustado(titular, ANCHO - 140, 4, 96)
    alto_texto = int(letra.size * 1.18) * len(lineas)
    y = ALTO - 110 - alto_texto
    dibujo.rectangle((60, y - 34, 190, y - 24), fill=acento)
    g.dibujar_lineas(dibujo, lineas, letra, 60, y, (255, 255, 255), sombra=True)
    return lienzo.convert("RGB")


def disenar_beneficio(base: Image.Image, titular: str, empresa: str, acento) -> Image.Image:
    """Fondo desenfocado, titular arriba y la foto en una tarjeta redondeada."""
    lienzo = g.fondo_desenfocado(base, ANCHO, ALTO, 0.5).convert("RGBA")
    dibujo = ImageDraw.Draw(lienzo)
    letra, lineas = g.texto_ajustado(titular, ANCHO - 160, 3, 78)
    y = g.dibujar_lineas(dibujo, lineas, letra, 0, 90, (255, 255, 255), centrado_en=ANCHO // 2, sombra=True)
    espacio = ALTO - y - 170
    tarjeta = g.contener(base, ANCHO - 200, max(espacio, 400))
    tarjeta = g.esquinas_redondeadas(tarjeta, 36)
    x = (ANCHO - tarjeta.width) // 2
    ty = y + 40 + (espacio - tarjeta.height) // 2
    sombra = Image.new("RGBA", lienzo.size, (0, 0, 0, 0))
    ImageDraw.Draw(sombra).rounded_rectangle((x + 10, ty + 16, x + tarjeta.width + 10, ty + tarjeta.height + 16),
                                             36, fill=(0, 0, 0, 110))
    lienzo.alpha_composite(sombra)
    lienzo.alpha_composite(tarjeta, (x, ty))
    letra_marca = g.fuente(36)
    texto = g.limpiar_texto(empresa).upper()
    dibujo = ImageDraw.Draw(lienzo)
    dibujo.text(((ANCHO - letra_marca.getlength(texto)) / 2, ALTO - 100), texto, font=letra_marca, fill=acento
                if sum(acento) > 300 else (255, 255, 255))
    return lienzo.convert("RGB")


def disenar_cierre(base: Image.Image, titular: str, llamado: str, empresa: str, acento) -> Image.Image:
    """Foto arriba y panel de color con el llamado a la acción."""
    alto_foto = int(ALTO * 0.6)
    lienzo = Image.new("RGB", (ANCHO, ALTO), acento)
    foto = ImageEnhance.Contrast(g.cubrir(base, ANCHO, alto_foto)).enhance(1.06)
    lienzo.paste(foto, (0, 0))
    dibujo = ImageDraw.Draw(lienzo)
    tinta = g.contraste(acento)
    letra, lineas = g.texto_ajustado(titular, ANCHO - 140, 2, 80)
    y = g.dibujar_lineas(dibujo, lineas, letra, 70, alto_foto + 50, tinta)
    boton, lineas_boton = g.texto_ajustado(llamado or "Escríbenos", ANCHO - 240, 2, 36, minimo=28)
    ancho_boton = int(max(boton.getlength(linea) for linea in lineas_boton)) + 70
    alto_boton = int(boton.size * 1.18) * len(lineas_boton) + 36
    y += 24
    dibujo.rounded_rectangle((70, y, 70 + ancho_boton, y + alto_boton), 30, fill=tinta)
    g.dibujar_lineas(dibujo, lineas_boton, boton, 105, y + 16, acento)
    letra_marca = g.fuente(30, negrita=False)
    marca = g.limpiar_texto(empresa)
    dibujo.text((ANCHO - 70 - letra_marca.getlength(marca), ALTO - 70), marca, font=letra_marca, fill=tinta)
    return lienzo


class GeneradorImagenesLocal:
    """Diseña las piezas con Pillow sobre la foto original (sin costo ni claves)."""

    nombre = "local-pillow"

    def generar(self, foto: Image.Image, brief: Brief, guion: Guion, paleta: list[str]) -> list[Image.Image]:
        acento = g.color_acento(paleta)
        e1, e2, e3 = guion.escenas[:3]
        variante = ImageEnhance.Color(foto).enhance(1.12)
        return [
            disenar_gancho(variante, e1.texto_en_pantalla, brief.empresa, acento),
            disenar_beneficio(foto, e2.texto_en_pantalla, brief.empresa, acento),
            disenar_cierre(variante, e3.texto_en_pantalla, guion.llamado_accion, brief.empresa, acento),
        ]


class GeneradorImagenesOpenAI:
    """Crea una foto nueva por escena con gpt-image-1 usando la foto como referencia
    y luego le aplica el diseño con el texto del guion."""

    nombre = "openai"

    def __init__(self, modelo: str = "gpt-image-1", cliente=None):
        self.modelo = modelo
        self._cliente = cliente

    @property
    def cliente(self):
        if self._cliente is None:
            from openai import OpenAI

            self._cliente = OpenAI()
        return self._cliente

    def _foto_ia(self, foto: Image.Image, brief: Brief, descripcion: str) -> Image.Image:
        buffer = io.BytesIO()
        referencia = foto.copy()
        referencia.thumbnail((1536, 1536))
        referencia.save(buffer, format="PNG")
        buffer.name = "referencia.png"
        buffer.seek(0)
        prompt = (
            f"Fotografía publicitaria profesional para la marca {brief.empresa}. Producto: {brief.producto}. "
            f"Escena: {descripcion}. Conserva el producto de la imagen de referencia sin cambiar su forma, "
            "colores ni etiquetas. Formato vertical, iluminación de estudio, alta calidad. No agregues texto."
        )
        try:
            respuesta = self.cliente.images.edit(model=self.modelo, image=buffer, prompt=prompt, size="1024x1536")
        except Exception as error:  # el SDK de OpenAI usa sus propias excepciones
            raise ErrorProveedor(f"OpenAI no pudo generar la imagen: {error}") from None
        datos = base64.b64decode(respuesta.data[0].b64_json)
        return Image.open(io.BytesIO(datos)).convert("RGB")

    def generar(self, foto: Image.Image, brief: Brief, guion: Guion, paleta: list[str]) -> list[Image.Image]:
        acento = g.color_acento(paleta)
        e1, e2, e3 = guion.escenas[:3]
        fotos = [self._foto_ia(foto, brief, e.descripcion_visual) for e in (e1, e2, e3)]
        log.info("3 fotos generadas con %s", self.modelo)
        return [
            disenar_gancho(fotos[0], e1.texto_en_pantalla, brief.empresa, acento),
            disenar_beneficio(fotos[1], e2.texto_en_pantalla, brief.empresa, acento),
            disenar_cierre(fotos[2], e3.texto_en_pantalla, guion.llamado_accion, brief.empresa, acento),
        ]


def crear_generador_imagenes(proveedor: str, modelo_openai: str) -> GeneradorImagenes:
    if proveedor == "openai":
        return GeneradorImagenesOpenAI(modelo_openai)
    return GeneradorImagenesLocal()
