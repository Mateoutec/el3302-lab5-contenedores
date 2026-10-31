"""Acceso a datos: traduce entre filas ORM y entidades de dominio."""
from __future__ import annotations

from datetime import timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.datos.modelos import PartidoORM, PrediccionORM
from app.dominio.entidades import EstadoPartido, Partido, Prediccion, Resultado


def _utc(fecha):
    # SQLite devuelve fechas sin zona horaria; PostgreSQL las devuelve con zona.
    if fecha is not None and fecha.tzinfo is None:
        return fecha.replace(tzinfo=timezone.utc)
    return fecha


def _a_partido(fila: PartidoORM) -> Partido:
    return Partido(
        id=fila.id,
        id_externo=fila.id_externo,
        competicion=fila.competicion,
        etapa=fila.etapa,
        jornada=fila.jornada,
        fecha_utc=_utc(fila.fecha_utc),
        estado=EstadoPartido(fila.estado),
        equipo_local=fila.equipo_local,
        equipo_visitante=fila.equipo_visitante,
        escudo_local=fila.escudo_local,
        escudo_visitante=fila.escudo_visitante,
        goles_local=fila.goles_local,
        goles_visitante=fila.goles_visitante,
        actualizado_en=_utc(fila.actualizado_en),
    )


def _a_prediccion(fila: PrediccionORM) -> Prediccion:
    return Prediccion(
        id=fila.id,
        partido_id=fila.partido_id,
        autor=fila.autor,
        resultado=Resultado(fila.resultado),
        goles_local=fila.goles_local,
        goles_visitante=fila.goles_visitante,
        creado_en=_utc(fila.creado_en),
        partido=_a_partido(fila.partido) if fila.partido is not None else None,
    )


class RepositorioPartidos:
    def __init__(self, sesion: Session):
        self.sesion = sesion

    def guardar_o_actualizar(self, partidos: list[Partido]) -> tuple[int, int]:
        """Inserta los partidos nuevos y actualiza los existentes (clave: id_externo)."""
        existentes = {
            fila.id_externo: fila
            for fila in self.sesion.scalars(
                select(PartidoORM).where(PartidoORM.id_externo.in_([p.id_externo for p in partidos]))
            )
        }
        nuevos = actualizados = 0
        for partido in partidos:
            fila = existentes.get(partido.id_externo)
            if fila is None:
                fila = PartidoORM(id_externo=partido.id_externo)
                self.sesion.add(fila)
                nuevos += 1
            else:
                actualizados += 1
            fila.competicion = partido.competicion
            fila.etapa = partido.etapa
            fila.jornada = partido.jornada
            fila.fecha_utc = partido.fecha_utc
            fila.estado = partido.estado.value
            fila.equipo_local = partido.equipo_local
            fila.equipo_visitante = partido.equipo_visitante
            fila.escudo_local = partido.escudo_local
            fila.escudo_visitante = partido.escudo_visitante
            fila.goles_local = partido.goles_local
            fila.goles_visitante = partido.goles_visitante
        self.sesion.flush()
        return nuevos, actualizados

    def listar(self, estado: EstadoPartido | None = None, jornada: int | None = None) -> list[Partido]:
        consulta = select(PartidoORM).order_by(PartidoORM.fecha_utc, PartidoORM.id)
        if estado is not None:
            consulta = consulta.where(PartidoORM.estado == estado.value)
        if jornada is not None:
            consulta = consulta.where(PartidoORM.jornada == jornada)
        return [_a_partido(fila) for fila in self.sesion.scalars(consulta)]

    def obtener(self, partido_id: int) -> Partido | None:
        fila = self.sesion.get(PartidoORM, partido_id)
        return _a_partido(fila) if fila else None

    def jornadas(self) -> list[int]:
        consulta = select(PartidoORM.jornada).where(PartidoORM.jornada.is_not(None)).distinct()
        return sorted(self.sesion.scalars(consulta))

    def contar(self) -> int:
        return self.sesion.scalar(select(func.count()).select_from(PartidoORM)) or 0


class RepositorioPredicciones:
    def __init__(self, sesion: Session):
        self.sesion = sesion

    def crear(self, prediccion: Prediccion) -> Prediccion:
        fila = PrediccionORM(
            partido_id=prediccion.partido_id,
            autor=prediccion.autor,
            resultado=prediccion.resultado.value,
            goles_local=prediccion.goles_local,
            goles_visitante=prediccion.goles_visitante,
        )
        self.sesion.add(fila)
        self.sesion.flush()
        self.sesion.refresh(fila)
        return _a_prediccion(fila)

    def listar(self, partido_id: int | None = None) -> list[Prediccion]:
        consulta = (
            select(PrediccionORM)
            .options(joinedload(PrediccionORM.partido))
            .order_by(PrediccionORM.creado_en.desc(), PrediccionORM.id.desc())
        )
        if partido_id is not None:
            consulta = consulta.where(PrediccionORM.partido_id == partido_id)
        return [_a_prediccion(fila) for fila in self.sesion.scalars(consulta)]

    def contar_por_partido(self) -> dict[int, int]:
        consulta = select(PrediccionORM.partido_id, func.count()).group_by(PrediccionORM.partido_id)
        return {partido_id: total for partido_id, total in self.sesion.execute(consulta)}
