"""Flujo de negocio: foto → 3 guiones → elegir uno → 3 fotos + video → publicar."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from sqlalchemy.orm import sessionmaker

from app.datos.almacen import AlmacenArchivos
from app.datos.repositorio import RepositorioCampanas
from app.dominio.entidades import Brief, Campana, EstadoCampana, Recurso, RedSocial, TipoRecurso
from app.proveedores import graficos
from app.proveedores.guiones import ErrorProveedor, GeneradorGuiones
from app.proveedores.imagenes import GeneradorImagenes
from app.proveedores.redes import Publicador
from app.proveedores.video import GeneradorVideo

log = logging.getLogger(__name__)

TONOS = ["Cercano", "Profesional", "Divertido", "Premium"]
TIPOS_FOTO = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}


class ErrorNegocio(Exception):
    """Error de validación o de estado que se muestra al usuario."""


class CampanaNoEncontrada(ErrorNegocio):
    pass


class ServicioCampanas:
    def __init__(self, fabrica_sesiones: sessionmaker, almacen: AlmacenArchivos,
                 guiones: GeneradorGuiones, imagenes: GeneradorImagenes, video: GeneradorVideo,
                 publicador_para: Callable[[RedSocial], Publicador], url_publica: str, max_mb_foto: int = 10):
        self.fabrica = fabrica_sesiones
        self.almacen = almacen
        self.guiones = guiones
        self.imagenes = imagenes
        self.video = video
        self.publicador_para = publicador_para
        self.url_publica = url_publica.rstrip("/")
        self.max_bytes = max_mb_foto * 1024 * 1024

    # ------------------------------------------------------------------ consultas
    def obtener(self, campana_id: int) -> Campana:
        with self.fabrica() as sesion:
            campana = RepositorioCampanas(sesion).obtener(campana_id)
        if campana is None:
            raise CampanaNoEncontrada(f"No existe la campaña {campana_id}")
        return campana

    def listar(self) -> list[Campana]:
        with self.fabrica() as sesion:
            return RepositorioCampanas(sesion).listar()

    # ------------------------------------------------------------------ paso 1: foto + brief
    def crear(self, empresa: str, producto: str, publico: str, tono: str, red_social: str,
              foto: bytes, tipo_contenido: str = "") -> Campana:
        empresa, producto, publico = (empresa or "").strip(), (producto or "").strip(), (publico or "").strip()
        if not 2 <= len(empresa) <= 80:
            raise ErrorNegocio("El nombre de la empresa debe tener entre 2 y 80 caracteres.")
        if not 2 <= len(producto) <= 160:
            raise ErrorNegocio("Describe el producto o servicio (entre 2 y 160 caracteres).")
        if len(publico) > 160:
            raise ErrorNegocio("El público objetivo no puede pasar de 160 caracteres.")
        if tono not in TONOS:
            raise ErrorNegocio(f"El tono debe ser uno de: {', '.join(TONOS)}.")
        try:
            red = RedSocial(red_social)
        except ValueError:
            raise ErrorNegocio("Elige Instagram o TikTok.") from None
        if not foto:
            raise ErrorNegocio("Sube una foto del producto.")
        if tipo_contenido and tipo_contenido not in TIPOS_FOTO and not tipo_contenido.startswith("image/"):
            raise ErrorNegocio("El archivo debe ser una imagen (JPG, PNG, WEBP o HEIC).")
        if len(foto) > self.max_bytes:
            raise ErrorNegocio(f"La foto pesa más de {self.max_bytes // (1024 * 1024)} MB.")
        try:
            imagen = graficos.cargar_foto(foto)
        except graficos.FotoInvalida as error:
            raise ErrorNegocio(str(error)) from None

        imagen.thumbnail((2048, 2048))
        carpeta = self.almacen.nueva_carpeta()
        ruta_foto = self.almacen.guardar_imagen(carpeta, "original.jpg", imagen, calidad=92)
        brief = Brief(empresa=empresa, producto=producto, publico=publico or "público general", tono=tono,
                      red_social=red)
        with self.fabrica.begin() as sesion:
            return RepositorioCampanas(sesion).crear(brief, ruta_foto, graficos.paleta(imagen))

    def generar_guiones(self, campana_id: int) -> None:
        """Tarea en segundo plano: pide los 3 guiones al generador (Claude o plantillas)."""
        campana = self.obtener(campana_id)
        try:
            propuesta = self.guiones.proponer(campana.brief, self.almacen.abrir_imagen(campana.foto))
        except Exception as error:
            self._fallo(campana_id, "No se pudieron generar los guiones", error)
            return
        with self.fabrica.begin() as sesion:
            RepositorioCampanas(sesion).guardar_guiones(campana_id, propuesta.descripcion_foto,
                                                        propuesta.proveedor, propuesta.guiones)

    # ------------------------------------------------------------------ paso 2: elegir guion
    def elegir_guion(self, campana_id: int, guion_id: int) -> None:
        campana = self.obtener(campana_id)
        if campana.estado not in {EstadoCampana.GUIONES_LISTOS, EstadoCampana.CONTENIDO_LISTO, EstadoCampana.ERROR}:
            raise ErrorNegocio("La campaña no está lista para elegir guion.")
        if not any(g.id == guion_id for g in campana.guiones):
            raise ErrorNegocio("Ese guion no pertenece a la campaña.")
        if campana.publicaciones:
            raise ErrorNegocio("La campaña ya se publicó; crea una nueva para otro guion.")
        with self.fabrica.begin() as sesion:
            RepositorioCampanas(sesion).elegir_guion(campana_id, guion_id)

    def generar_contenido(self, campana_id: int) -> None:
        """Tarea en segundo plano: 3 fotos (una por escena) + video vertical."""
        campana = self.obtener(campana_id)
        guion = campana.guion_elegido
        try:
            if guion is None:
                raise ErrorNegocio("No hay guion elegido.")
            foto = self.almacen.abrir_imagen(campana.foto)
            carpeta = str(Path(campana.foto).parent.as_posix())
            piezas = self.imagenes.generar(foto, campana.brief, guion, campana.paleta)
            recursos = [
                Recurso(tipo=TipoRecurso.FOTO, orden=i, proveedor=self.imagenes.nombre,
                        ruta=self.almacen.guardar_imagen(carpeta, f"foto_{i}.jpg", pieza))
                for i, pieza in enumerate(piezas, start=1)
            ]
            video = self.video.generar(piezas, campana.brief, guion, graficos.color_acento(campana.paleta),
                                       self.almacen.ruta(carpeta))
            recursos.append(Recurso(tipo=TipoRecurso.VIDEO, orden=1, proveedor=self.video.nombre,
                                    ruta=self.almacen.relativa(video)))
        except Exception as error:
            self._fallo(campana_id, "No se pudo generar el contenido", error)
            return
        with self.fabrica.begin() as sesion:
            RepositorioCampanas(sesion).reemplazar_recursos(campana_id, recursos)

    # ------------------------------------------------------------------ paso 3: publicar
    def solicitar_publicacion(self, campana_id: int) -> None:
        campana = self.obtener(campana_id)
        if campana.estado != EstadoCampana.CONTENIDO_LISTO or not campana.video:
            raise ErrorNegocio("Primero genera las fotos y el video.")
        with self.fabrica.begin() as sesion:
            RepositorioCampanas(sesion).cambiar_estado(campana_id, EstadoCampana.PUBLICANDO)

    def publicar(self, campana_id: int) -> None:
        """Tarea en segundo plano: envía el contenido a la red social elegida."""
        campana = self.obtener(campana_id)
        try:
            publicador = self.publicador_para(campana.brief.red_social)
            fotos = [self.almacen.ruta(r.ruta) for r in campana.fotos]
            video = self.almacen.ruta(campana.video.ruta)
            publicacion = publicador.publicar(campana, campana.guion_elegido, fotos, video, self.url_media)
        except Exception as error:
            # Si falla la red social el contenido sigue disponible: vuelve a CONTENIDO_LISTO.
            log.exception("Fallo al publicar la campaña %s", campana_id)
            with self.fabrica.begin() as sesion:
                RepositorioCampanas(sesion).cambiar_estado(campana_id, EstadoCampana.CONTENIDO_LISTO,
                                                           f"No se pudo publicar: {self._mensaje(error)}")
            return
        with self.fabrica.begin() as sesion:
            repo = RepositorioCampanas(sesion)
            repo.agregar_publicacion(campana_id, publicacion)
            repo.cambiar_estado(campana_id, EstadoCampana.PUBLICADA)

    def url_media(self, absoluta: Path) -> str:
        return f"{self.url_publica}/media/{self.almacen.relativa(absoluta)}"

    # ------------------------------------------------------------------ reintentos y errores
    def reintentar(self, campana_id: int) -> str:
        """Devuelve el paso a relanzar: 'guiones' o 'contenido'."""
        campana = self.obtener(campana_id)
        if campana.estado != EstadoCampana.ERROR:
            raise ErrorNegocio("La campaña no tiene errores pendientes.")
        with self.fabrica.begin() as sesion:
            repo = RepositorioCampanas(sesion)
            if campana.guion_elegido_id:
                repo.elegir_guion(campana_id, campana.guion_elegido_id)
                return "contenido"
            repo.cambiar_estado(campana_id, EstadoCampana.GENERANDO_GUIONES)
            return "guiones"

    @staticmethod
    def _mensaje(error: Exception) -> str:
        if isinstance(error, (ErrorProveedor, ErrorNegocio)):
            return str(error)
        return f"{type(error).__name__}: {error}"

    def _fallo(self, campana_id: int, contexto: str, error: Exception) -> None:
        log.exception("%s (campaña %s)", contexto, campana_id)
        with self.fabrica.begin() as sesion:
            RepositorioCampanas(sesion).cambiar_estado(campana_id, EstadoCampana.ERROR,
                                                       f"{contexto}: {self._mensaje(error)}")
