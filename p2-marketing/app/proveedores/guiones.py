"""Generadores de guiones: Claude (visión + salida estructurada) o plantillas locales."""
from __future__ import annotations

import base64
import io
import json
import logging
import os
from typing import Protocol

from PIL import Image
from pydantic import BaseModel, ValidationError

from app.dominio.entidades import Brief, Escena, Guion, PropuestaGuiones, RedSocial
from app.proveedores.graficos import describir_foto, paleta

log = logging.getLogger(__name__)


class ErrorProveedor(RuntimeError):
    """Falla de un servicio externo (IA o red social); el mensaje se muestra al usuario."""


class GeneradorGuiones(Protocol):
    nombre: str

    def proponer(self, brief: Brief, foto: Image.Image) -> PropuestaGuiones: ...


# --------------------------------------------------------------------------- Claude

class _EscenaIA(BaseModel):
    texto_en_pantalla: str
    descripcion_visual: str
    narracion: str


class _GuionIA(BaseModel):
    titulo: str
    enfoque: str
    gancho: str
    escenas: list[_EscenaIA]
    llamado_accion: str
    caption: str
    hashtags: list[str]


class _RespuestaIA(BaseModel):
    descripcion_foto: str
    guiones: list[_GuionIA]


def _esquema_estricto(modelo: type[BaseModel]) -> dict:
    """JSON Schema de Pydantic con additionalProperties=false en cada objeto."""
    esquema = modelo.model_json_schema()
    definiciones = esquema.pop("$defs", {})

    def resolver(nodo):
        if isinstance(nodo, dict):
            if "$ref" in nodo:
                return resolver(definiciones[nodo["$ref"].split("/")[-1]])
            nodo = {k: resolver(v) for k, v in nodo.items() if k != "title"}
            if nodo.get("type") == "object":
                nodo["additionalProperties"] = False
                nodo["required"] = list(nodo.get("properties", {}))
            return nodo
        if isinstance(nodo, list):
            return [resolver(v) for v in nodo]
        return nodo

    return resolver(esquema)


SISTEMA = """Eres director creativo de una agencia de marketing digital que trabaja con \
pequeñas y medianas empresas de Latinoamérica. Recibes la foto de un producto o \
servicio y un brief. Analizas la foto con atención (qué se ve, materiales, colores, \
ambiente, calidad) y propones contenido para redes sociales en español neutro.

Reglas:
- Propón exactamente 3 guiones con enfoques claramente distintos (por ejemplo: \
problema-solución, estilo de vida/aspiracional, oferta o prueba social).
- Cada guion tiene exactamente 3 escenas, pensadas para un video vertical corto \
(9:16, 12-15 segundos) y para un carrusel de 3 fotos.
- texto_en_pantalla: máximo 8 palabras, sin emojis, impactante y legible.
- descripcion_visual: cómo debe verse la foto de esa escena (encuadre, fondo, luz, \
props), siempre mostrando el producto real de la foto sin cambiar su forma ni marca.
- narracion: una frase de locución de máximo 20 palabras.
- caption: adaptado a la red social indicada, con el tono pedido; puede llevar emojis.
- hashtags: entre 5 y 8, sin espacios, empezando con #.
- No inventes precios, descuentos, premios ni datos que no estén en el brief."""


class GeneradorGuionesClaude:
    nombre = "claude"

    def __init__(self, modelo: str = "claude-opus-5-5", cliente=None):
        self.modelo = modelo
        self._cliente = cliente

    @property
    def cliente(self):
        if self._cliente is None:
            import anthropic

            self._cliente = anthropic.Anthropic()
        return self._cliente

    @staticmethod
    def _foto_base64(foto: Image.Image) -> str:
        copia = foto.copy()
        copia.thumbnail((1568, 1568))  # tamaño recomendado para visión
        buffer = io.BytesIO()
        copia.save(buffer, format="JPEG", quality=88)
        return base64.standard_b64encode(buffer.getvalue()).decode()

    def proponer(self, brief: Brief, foto: Image.Image) -> PropuestaGuiones:
        import anthropic

        red = "Instagram (carrusel + Reel)" if brief.red_social == RedSocial.INSTAGRAM else "TikTok (video vertical)"
        pedido = (
            f"Empresa: {brief.empresa}\nProducto o servicio: {brief.producto}\n"
            f"Público objetivo: {brief.publico}\nTono: {brief.tono}\nRed social: {red}\n\n"
            "Describe brevemente la foto y propón los 3 guiones."
        )
        try:
            respuesta = self.cliente.beta.messages.create(
                model=self.modelo,
                max_tokens=16000,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                output_config={
                    "effort": "medium",
                    "format": {"type": "json_schema", "schema": _esquema_estricto(_RespuestaIA)},
                },
                system=SISTEMA,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                     "data": self._foto_base64(foto)}},
                        {"type": "text", "text": pedido},
                    ],
                }],
            )
        except anthropic.AuthenticationError:
            raise ErrorProveedor("La clave ANTHROPIC_API_KEY no es válida.") from None
        except anthropic.RateLimitError:
            raise ErrorProveedor("Claude está limitando las solicitudes; intenta en un minuto.") from None
        except anthropic.APIStatusError as error:
            raise ErrorProveedor(f"Claude respondió {error.status_code}: {error.message}") from None
        except anthropic.APIConnectionError:
            raise ErrorProveedor("No se pudo conectar con la API de Claude.") from None

        if respuesta.stop_reason == "refusal":
            raise ErrorProveedor("Claude no pudo generar guiones para esta foto. Prueba con otra imagen.")
        if respuesta.stop_reason == "max_tokens":
            raise ErrorProveedor("La respuesta de Claude quedó incompleta; vuelve a intentarlo.")
        texto = next((b.text for b in respuesta.content if b.type == "text"), "")
        try:
            datos = _RespuestaIA.model_validate(json.loads(texto))
        except (json.JSONDecodeError, ValidationError) as error:
            raise ErrorProveedor(f"Respuesta de Claude con formato inesperado: {error}") from None
        guiones = [g for g in datos.guiones if len(g.escenas) >= 3][:3]
        if len(guiones) < 3:
            raise ErrorProveedor("Claude devolvió menos de 3 guiones completos; vuelve a intentarlo.")
        log.info("Guiones generados con %s (request %s)", self.modelo, getattr(respuesta, "_request_id", ""))
        return PropuestaGuiones(
            descripcion_foto=datos.descripcion_foto,
            proveedor=f"claude:{self.modelo}",
            guiones=[
                Guion(
                    orden=i, titulo=g.titulo, enfoque=g.enfoque, gancho=g.gancho,
                    escenas=[Escena(**e.model_dump()) for e in g.escenas[:3]],
                    llamado_accion=g.llamado_accion, caption=g.caption,
                    hashtags=[h if h.startswith("#") else f"#{h}" for h in g.hashtags][:8],
                )
                for i, g in enumerate(guiones, start=1)
            ],
        )


# --------------------------------------------------------------------------- Plantillas

_TONOS = {
    "cercano": {"adj": "hecho para ti", "cierre": "Te esperamos", "verbo": "Descubre"},
    "profesional": {"adj": "calidad que se nota", "cierre": "Contáctanos hoy", "verbo": "Conoce"},
    "divertido": {"adj": "imposible no quererlo", "cierre": "¡Corre por el tuyo!", "verbo": "Mira"},
    "premium": {"adj": "una experiencia superior", "cierre": "Reserva el tuyo", "verbo": "Vive"},
}


_VACIAS = {"de", "del", "la", "el", "los", "las", "en", "y", "con", "para", "por", "un", "una", "al", "a"}


def _etiqueta(texto: str, palabras: int = 2) -> str:
    """'café de especialidad de Villa Rica, 250 g' -> '#CaféEspecialidad'."""
    utiles = [w for w in texto.replace(",", " ").split() if w.lower() not in _VACIAS and w.isalpha()]
    limpio = "".join(w[:1].upper() + w[1:].lower() for w in utiles[:palabras])
    return f"#{limpio}" if limpio else ""


def _mayuscula(texto: str) -> str:
    return texto[:1].upper() + texto[1:]


class GeneradorGuionesPlantilla:
    """Funciona sin claves de API: arma 3 guiones a partir del brief y del análisis de color de la foto."""

    nombre = "plantilla"

    def proponer(self, brief: Brief, foto: Image.Image) -> PropuestaGuiones:
        t = _TONOS.get(brief.tono.lower(), _TONOS["cercano"])
        colores = paleta(foto)
        descripcion = describir_foto(foto, colores)
        producto, empresa, publico = brief.producto, brief.empresa, brief.publico or "todos"
        Producto = _mayuscula(producto)  # para inicio de oración
        red = "TikTok" if brief.red_social == RedSocial.TIKTOK else "Instagram"
        base_tags = [_etiqueta(empresa, 3), _etiqueta(producto), "#emprendimiento", "#compralocal"]
        if red == "TikTok":
            base_tags += ["#tiktokmehizocomprarlo", "#parati"]
        else:
            base_tags += ["#instashop", "#reels"]
        base_tags = [h for h in base_tags if h]

        guiones = [
            Guion(
                orden=1, titulo="Problema → solución",
                enfoque=f"Muestra una necesidad cotidiana de {publico} y presenta {producto} como la respuesta.",
                gancho=f"¿Todavía no conoces {producto}?",
                escenas=[
                    Escena("¿Buscas algo diferente?", f"Plano cerrado de {producto} con fondo neutro, luz suave lateral.",
                           f"Si buscas algo distinto, esto es para ti."),
                    Escena(f"{t['verbo']} {producto}", f"{Producto} en uso, en un ambiente real y luminoso.",
                           f"{Producto} de {empresa}: {t['adj']}."),
                    Escena(t["cierre"], f"{Producto} junto al logo o nombre de {empresa}, fondo de color de marca.",
                           f"{t['cierre']}. Escríbenos y pide el tuyo."),
                ],
                llamado_accion=f"{t['cierre']} — escríbenos por mensaje directo.",
                caption=f"¿Todavía no conoces {producto}? En {empresa} lo pensamos para {publico}: {t['adj']}.",
                hashtags=base_tags[:6],
            ),
            Guion(
                orden=2, titulo="Estilo de vida",
                enfoque=f"Asocia {producto} a un momento aspiracional del día a día de {publico}.",
                gancho="Así se ve un buen día",
                escenas=[
                    Escena("Así empieza un buen día", f"Escena cálida de estilo de vida con {producto} en primer plano.",
                           "Hay momentos que merecen lo mejor."),
                    Escena(f"{_mayuscula(producto)}, {t['adj']}", f"Detalle del producto: textura y acabados, luz natural.",
                           f"Por eso elegimos {producto}."),
                    Escena(f"Encuéntralo en {empresa}", f"Toma amplia del producto con espacio libre para texto.",
                           f"Encuéntralo en {empresa}."),
                ],
                llamado_accion=f"Guarda esta publicación y visítanos en {empresa}.",
                caption=f"Los pequeños detalles hacen la diferencia. {Producto} de {empresa}, {t['adj']}.",
                hashtags=(base_tags + ["#estilodevida"])[:7],
            ),
            Guion(
                orden=3, titulo="Lanzamiento con urgencia",
                enfoque="Presenta el producto como novedad disponible por tiempo limitado, sin inventar precios.",
                gancho="Llegó lo que estabas esperando",
                escenas=[
                    Escena("¡Ya llegó!", f"{Producto} centrado, fondo de color intenso, estilo anuncio.",
                           "Atención: ya llegó lo que estabas esperando."),
                    Escena("Stock limitado", f"Varias vistas o unidades de {producto}, composición dinámica.",
                           "Las unidades son limitadas."),
                    Escena("Pide el tuyo hoy", f"{Producto} con el nombre de {empresa} y un botón de acción.",
                           f"Pide el tuyo hoy en {empresa}."),
                ],
                llamado_accion="Pide el tuyo hoy: link en la bio o mensaje directo.",
                caption=f"Nuevo en {empresa}: {producto}. Unidades limitadas, no te quedes sin el tuyo.",
                hashtags=(base_tags + ["#novedad", "#lanzamiento"])[:8],
            ),
        ]
        return PropuestaGuiones(descripcion_foto=descripcion, guiones=guiones, proveedor="plantilla-local")


def crear_generador_guiones(proveedor: str, modelo: str) -> GeneradorGuiones:
    if proveedor == "claude" or (proveedor == "auto" and os.getenv("ANTHROPIC_API_KEY")):
        return GeneradorGuionesClaude(modelo)
    return GeneradorGuionesPlantilla()
