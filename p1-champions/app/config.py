"""Configuración leída de variables de entorno (ver .env.example)."""
from __future__ import annotations

import os
from dataclasses import dataclass


def _bool(valor: str | None, por_defecto: bool) -> bool:
    if valor is None or valor == "":
        return por_defecto
    return valor.strip().lower() in {"1", "true", "si", "sí", "yes", "on"}


@dataclass(frozen=True)
class Config:
    database_url: str
    api_partidos_url: str
    api_partidos_token: str
    competicion: str
    temporada: str
    sincronizar_al_iniciar: bool
    intentos_sincronizacion: int
    zona_horaria: str


def cargar_config() -> Config:
    return Config(
        database_url=os.getenv("DATABASE_URL", "sqlite:///./champions.db"),
        # Por defecto apunta a la API simulada (mock_api), que imita el
        # contrato v4 de football-data.org. Para la API real:
        # API_PARTIDOS_URL=https://api.football-data.org/v4 y un token gratuito.
        api_partidos_url=os.getenv("API_PARTIDOS_URL", "http://localhost:8081/v4").rstrip("/"),
        api_partidos_token=os.getenv("API_PARTIDOS_TOKEN", ""),
        competicion=os.getenv("COMPETICION", "CL"),
        temporada=os.getenv("TEMPORADA", ""),
        sincronizar_al_iniciar=_bool(os.getenv("SINCRONIZAR_AL_INICIAR"), True),
        intentos_sincronizacion=int(os.getenv("INTENTOS_SINCRONIZACION", "10")),
        zona_horaria=os.getenv("ZONA_HORARIA", "America/Lima"),
    )
