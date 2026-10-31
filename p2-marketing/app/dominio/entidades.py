"""Entidades de dominio de la app de marketing."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class EstadoCampana(str, Enum):
    GENERANDO_GUIONES = "GENERANDO_GUIONES"
    GUIONES_LISTOS = "GUIONES_LISTOS"
    GENERANDO_CONTENIDO = "GENERANDO_CONTENIDO"
    CONTENIDO_LISTO = "CONTENIDO_LISTO"
    PUBLICANDO = "PUBLICANDO"
    PUBLICADA = "PUBLICADA"
    ERROR = "ERROR"


class RedSocial(str, Enum):
    INSTAGRAM = "INSTAGRAM"
    TIKTOK = "TIKTOK"


class TipoRecurso(str, Enum):
    FOTO = "FOTO"
    VIDEO = "VIDEO"


@dataclass
class Brief:
    """Datos que el usuario ingresa junto con la foto."""
    empresa: str
    producto: str
    publico: str
    tono: str
    red_social: RedSocial


@dataclass
class Escena:
    texto_en_pantalla: str
    descripcion_visual: str
    narracion: str


@dataclass
class Guion:
    titulo: str
    enfoque: str
    gancho: str
    escenas: list[Escena]
    llamado_accion: str
    caption: str
    hashtags: list[str]
    orden: int = 0
    id: int | None = None
    campana_id: int | None = None

    def texto_publicacion(self) -> str:
        etiquetas = " ".join(h if h.startswith("#") else f"#{h}" for h in self.hashtags)
        return f"{self.caption}\n\n{self.llamado_accion}\n\n{etiquetas}".strip()


@dataclass
class PropuestaGuiones:
    descripcion_foto: str
    guiones: list[Guion]
    proveedor: str


@dataclass
class Recurso:
    tipo: TipoRecurso
    ruta: str  # relativa a MEDIA_DIR
    orden: int
    proveedor: str
    id: int | None = None
    campana_id: int | None = None


@dataclass
class Publicacion:
    red_social: RedSocial
    modo: str  # SIMULADO | REAL
    estado: str  # PUBLICADO | ERROR
    id_externo: str = ""
    url: str = ""
    detalle: str = ""
    id: int | None = None
    campana_id: int | None = None
    creado_en: datetime | None = None


@dataclass
class Campana:
    brief: Brief
    foto: str  # ruta relativa a MEDIA_DIR
    estado: EstadoCampana
    id: int | None = None
    descripcion_foto: str = ""
    paleta: list[str] = field(default_factory=list)
    proveedor_guiones: str = ""
    error: str = ""
    guion_elegido_id: int | None = None
    creado_en: datetime | None = None
    guiones: list[Guion] = field(default_factory=list)
    recursos: list[Recurso] = field(default_factory=list)
    publicaciones: list[Publicacion] = field(default_factory=list)

    @property
    def guion_elegido(self) -> Guion | None:
        return next((g for g in self.guiones if g.id == self.guion_elegido_id), None)

    @property
    def fotos(self) -> list[Recurso]:
        return sorted((r for r in self.recursos if r.tipo == TipoRecurso.FOTO), key=lambda r: r.orden)

    @property
    def video(self) -> Recurso | None:
        return next((r for r in self.recursos if r.tipo == TipoRecurso.VIDEO), None)

    @property
    def en_proceso(self) -> bool:
        return self.estado in {EstadoCampana.GENERANDO_GUIONES, EstadoCampana.GENERANDO_CONTENIDO, EstadoCampana.PUBLICANDO}
