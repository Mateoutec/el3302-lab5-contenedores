"""Almacén de archivos (fotos y videos) en el volumen montado en MEDIA_DIR."""
from __future__ import annotations

import uuid
from pathlib import Path

from PIL import Image


class AlmacenArchivos:
    def __init__(self, raiz: Path):
        self.raiz = Path(raiz)
        self.raiz.mkdir(parents=True, exist_ok=True)

    def nueva_carpeta(self) -> str:
        relativa = f"campanas/{uuid.uuid4().hex[:12]}"
        (self.raiz / relativa).mkdir(parents=True, exist_ok=True)
        return relativa

    def ruta(self, relativa: str) -> Path:
        destino = (self.raiz / relativa).resolve()
        if self.raiz.resolve() not in destino.parents and destino != self.raiz.resolve():
            raise ValueError("Ruta fuera del almacén")
        return destino

    def guardar_imagen(self, carpeta: str, nombre: str, imagen: Image.Image, calidad: int = 90) -> str:
        relativa = f"{carpeta}/{nombre}"
        imagen.save(self.ruta(relativa), format="JPEG", quality=calidad, optimize=True)
        return relativa

    def abrir_imagen(self, relativa: str) -> Image.Image:
        with Image.open(self.ruta(relativa)) as imagen:
            return imagen.convert("RGB")

    def relativa(self, absoluta: Path) -> str:
        return Path(absoluta).resolve().relative_to(self.raiz.resolve()).as_posix()
