"""Acceso a datos de campañas, guiones, recursos y publicaciones."""
from __future__ import annotations

from dataclasses import asdict
from datetime import timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from app.datos.modelos import CampanaORM, GuionORM, PublicacionORM, RecursoORM
from app.dominio.entidades import (
    Brief,
    Campana,
    Escena,
    EstadoCampana,
    Guion,
    Publicacion,
    Recurso,
    RedSocial,
    TipoRecurso,
)


def _utc(fecha):
    if fecha is not None and fecha.tzinfo is None:
        return fecha.replace(tzinfo=timezone.utc)
    return fecha


def _a_guion(f: GuionORM) -> Guion:
    return Guion(
        id=f.id, campana_id=f.campana_id, orden=f.orden, titulo=f.titulo, enfoque=f.enfoque,
        gancho=f.gancho, escenas=[Escena(**e) for e in f.escenas], llamado_accion=f.llamado_accion,
        caption=f.caption, hashtags=list(f.hashtags),
    )


def _a_campana(f: CampanaORM) -> Campana:
    return Campana(
        id=f.id,
        brief=Brief(empresa=f.empresa, producto=f.producto, publico=f.publico, tono=f.tono,
                    red_social=RedSocial(f.red_social)),
        foto=f.foto,
        estado=EstadoCampana(f.estado),
        descripcion_foto=f.descripcion_foto or "",
        paleta=list(f.paleta or []),
        proveedor_guiones=f.proveedor_guiones or "",
        error=f.error or "",
        guion_elegido_id=f.guion_elegido_id,
        creado_en=_utc(f.creado_en),
        guiones=[_a_guion(g) for g in f.guiones],
        recursos=[Recurso(id=r.id, campana_id=r.campana_id, tipo=TipoRecurso(r.tipo), ruta=r.ruta,
                          orden=r.orden, proveedor=r.proveedor) for r in f.recursos],
        publicaciones=[Publicacion(id=p.id, campana_id=p.campana_id, red_social=RedSocial(p.red_social),
                                   modo=p.modo, estado=p.estado, id_externo=p.id_externo, url=p.url,
                                   detalle=p.detalle, creado_en=_utc(p.creado_en)) for p in f.publicaciones],
    )


class RepositorioCampanas:
    def __init__(self, sesion: Session):
        self.sesion = sesion

    def _fila(self, campana_id: int) -> CampanaORM | None:
        return self.sesion.get(CampanaORM, campana_id)

    def crear(self, brief: Brief, foto: str, paleta: list[str]) -> Campana:
        fila = CampanaORM(empresa=brief.empresa, producto=brief.producto, publico=brief.publico,
                          tono=brief.tono, red_social=brief.red_social.value, foto=foto, paleta=paleta,
                          estado=EstadoCampana.GENERANDO_GUIONES.value)
        self.sesion.add(fila)
        self.sesion.flush()
        return _a_campana(fila)

    def obtener(self, campana_id: int) -> Campana | None:
        consulta = (
            select(CampanaORM)
            .where(CampanaORM.id == campana_id)
            .options(selectinload(CampanaORM.guiones), selectinload(CampanaORM.recursos),
                     selectinload(CampanaORM.publicaciones))
        )
        fila = self.sesion.scalars(consulta).first()
        return _a_campana(fila) if fila else None

    def listar(self) -> list[Campana]:
        consulta = (
            select(CampanaORM)
            .order_by(CampanaORM.id.desc())
            .options(selectinload(CampanaORM.guiones), selectinload(CampanaORM.recursos),
                     selectinload(CampanaORM.publicaciones))
        )
        return [_a_campana(f) for f in self.sesion.scalars(consulta)]

    def cambiar_estado(self, campana_id: int, estado: EstadoCampana, error: str = "") -> None:
        fila = self._fila(campana_id)
        fila.estado = estado.value
        fila.error = error

    def guardar_guiones(self, campana_id: int, descripcion_foto: str, proveedor: str, guiones: list[Guion]) -> None:
        fila = self._fila(campana_id)
        fila.descripcion_foto = descripcion_foto
        fila.proveedor_guiones = proveedor
        fila.guiones.clear()
        for orden, g in enumerate(guiones, start=1):
            fila.guiones.append(GuionORM(
                orden=orden, titulo=g.titulo, enfoque=g.enfoque, gancho=g.gancho,
                escenas=[asdict(e) for e in g.escenas], llamado_accion=g.llamado_accion,
                caption=g.caption, hashtags=list(g.hashtags),
            ))
        fila.estado = EstadoCampana.GUIONES_LISTOS.value
        fila.error = ""

    def elegir_guion(self, campana_id: int, guion_id: int) -> None:
        fila = self._fila(campana_id)
        fila.guion_elegido_id = guion_id
        fila.estado = EstadoCampana.GENERANDO_CONTENIDO.value
        fila.error = ""

    def reemplazar_recursos(self, campana_id: int, recursos: list[Recurso]) -> None:
        fila = self._fila(campana_id)
        fila.recursos.clear()
        for r in recursos:
            fila.recursos.append(RecursoORM(tipo=r.tipo.value, orden=r.orden, ruta=r.ruta, proveedor=r.proveedor))
        fila.estado = EstadoCampana.CONTENIDO_LISTO.value
        fila.error = ""

    def agregar_publicacion(self, campana_id: int, publicacion: Publicacion) -> None:
        fila = self._fila(campana_id)
        fila.publicaciones.append(PublicacionORM(
            red_social=publicacion.red_social.value, modo=publicacion.modo, estado=publicacion.estado,
            id_externo=publicacion.id_externo, url=publicacion.url, detalle=publicacion.detalle,
        ))

    def marcar_interrumpidas(self) -> int:
        """Al reiniciar el contenedor, las tareas que estaban en curso se marcan con error."""
        en_curso = [EstadoCampana.GENERANDO_GUIONES.value, EstadoCampana.GENERANDO_CONTENIDO.value,
                    EstadoCampana.PUBLICANDO.value]
        resultado = self.sesion.execute(
            update(CampanaORM).where(CampanaORM.estado.in_(en_curso))
            .values(estado=EstadoCampana.ERROR.value, error="La tarea se interrumpió por un reinicio. Pulsa «Reintentar».")
        )
        return resultado.rowcount or 0
