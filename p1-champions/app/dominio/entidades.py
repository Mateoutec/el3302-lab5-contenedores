"""Entidades de dominio compartidas por las tres capas.

No dependen de FastAPI ni de SQLAlchemy: la capa de datos las construye a
partir de las filas de la base de datos y la capa de negocio trabaja solo con
ellas.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class EstadoPartido(str, Enum):
    PROGRAMADO = "PROGRAMADO"
    EN_JUEGO = "EN_JUEGO"
    FINALIZADO = "FINALIZADO"
    SUSPENDIDO = "SUSPENDIDO"


class Resultado(str, Enum):
    LOCAL = "LOCAL"
    EMPATE = "EMPATE"
    VISITANTE = "VISITANTE"

    @staticmethod
    def desde_marcador(goles_local: int, goles_visitante: int) -> "Resultado":
        if goles_local > goles_visitante:
            return Resultado.LOCAL
        if goles_local < goles_visitante:
            return Resultado.VISITANTE
        return Resultado.EMPATE


@dataclass
class Partido:
    id_externo: int
    competicion: str
    etapa: str
    jornada: int | None
    fecha_utc: datetime
    estado: EstadoPartido
    equipo_local: str
    equipo_visitante: str
    escudo_local: str | None = None
    escudo_visitante: str | None = None
    goles_local: int | None = None
    goles_visitante: int | None = None
    id: int | None = None
    actualizado_en: datetime | None = None

    @property
    def resultado(self) -> Resultado | None:
        if self.estado != EstadoPartido.FINALIZADO:
            return None
        if self.goles_local is None or self.goles_visitante is None:
            return None
        return Resultado.desde_marcador(self.goles_local, self.goles_visitante)

    @property
    def admite_predicciones(self) -> bool:
        return self.estado == EstadoPartido.PROGRAMADO


@dataclass
class Prediccion:
    partido_id: int
    autor: str
    resultado: Resultado
    goles_local: int
    goles_visitante: int
    id: int | None = None
    creado_en: datetime | None = None
    partido: Partido | None = field(default=None, compare=False)
    puntos: int | None = None
