"""API REST (JSON). La documentación interactiva queda en /docs."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.datos.cliente_api_partidos import ErrorApiPartidos
from app.dominio.entidades import EstadoPartido, Partido, Prediccion, Resultado
from app.negocio.servicios import (
    PartidoNoEncontrado,
    PrediccionInvalida,
    ServicioPartidos,
    ServicioPredicciones,
)
from app.presentacion.dependencias import servicio_partidos, servicio_predicciones

router = APIRouter(prefix="/api", tags=["API"])


class PartidoSalida(BaseModel):
    id: int
    id_externo: int
    competicion: str
    etapa: str
    jornada: int | None
    fecha_utc: datetime
    estado: EstadoPartido
    equipo_local: str
    equipo_visitante: str
    goles_local: int | None
    goles_visitante: int | None
    resultado: Resultado | None
    admite_predicciones: bool

    @classmethod
    def desde(cls, p: Partido) -> "PartidoSalida":
        return cls(
            id=p.id, id_externo=p.id_externo, competicion=p.competicion, etapa=p.etapa,
            jornada=p.jornada, fecha_utc=p.fecha_utc, estado=p.estado,
            equipo_local=p.equipo_local, equipo_visitante=p.equipo_visitante,
            goles_local=p.goles_local, goles_visitante=p.goles_visitante,
            resultado=p.resultado, admite_predicciones=p.admite_predicciones,
        )


class PrediccionEntrada(BaseModel):
    partido_id: int
    autor: str = Field(min_length=1, max_length=60)
    resultado: Resultado
    goles_local: int = Field(ge=0, le=20)
    goles_visitante: int = Field(ge=0, le=20)


class PrediccionSalida(BaseModel):
    id: int
    partido_id: int
    partido: str
    autor: str
    resultado: Resultado
    marcador: str
    creado_en: datetime | None
    resultado_real: str | None
    puntos: int | None

    @classmethod
    def desde(cls, p: Prediccion) -> "PrediccionSalida":
        partido = p.partido
        real = None
        if partido is not None and partido.resultado is not None:
            real = f"{partido.goles_local}-{partido.goles_visitante}"
        return cls(
            id=p.id, partido_id=p.partido_id,
            partido=f"{partido.equipo_local} vs {partido.equipo_visitante}" if partido else "",
            autor=p.autor, resultado=p.resultado, marcador=f"{p.goles_local}-{p.goles_visitante}",
            creado_en=p.creado_en, resultado_real=real, puntos=p.puntos,
        )


@router.get("/partidos", response_model=list[PartidoSalida])
def listar_partidos(estado: EstadoPartido | None = None, jornada: int | None = None,
                    servicio: ServicioPartidos = Depends(servicio_partidos)):
    return [PartidoSalida.desde(p) for p in servicio.listar(estado, jornada)]


@router.get("/partidos/{partido_id}", response_model=PartidoSalida)
def obtener_partido(partido_id: int, servicio: ServicioPartidos = Depends(servicio_partidos)):
    try:
        return PartidoSalida.desde(servicio.obtener(partido_id))
    except PartidoNoEncontrado as error:
        raise HTTPException(404, str(error)) from None


@router.post("/sincronizar")
def sincronizar(servicio: ServicioPartidos = Depends(servicio_partidos)):
    try:
        return servicio.sincronizar().__dict__
    except ErrorApiPartidos as error:
        raise HTTPException(502, str(error)) from None


@router.get("/predicciones", response_model=list[PrediccionSalida])
def listar_predicciones(partido_id: int | None = None,
                        servicio: ServicioPredicciones = Depends(servicio_predicciones)):
    return [PrediccionSalida.desde(p) for p in servicio.listar(partido_id)]


@router.post("/predicciones", response_model=PrediccionSalida, status_code=201)
def crear_prediccion(datos: PrediccionEntrada, servicio: ServicioPredicciones = Depends(servicio_predicciones)):
    try:
        prediccion = servicio.registrar(datos.partido_id, datos.autor, datos.resultado,
                                        datos.goles_local, datos.goles_visitante)
    except PartidoNoEncontrado as error:
        raise HTTPException(404, str(error)) from None
    except PrediccionInvalida as error:
        raise HTTPException(422, str(error)) from None
    return PrediccionSalida.desde(prediccion)
