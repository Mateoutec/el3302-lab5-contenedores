"""Cliente HTTP de la API de partidos.

Sigue el contrato v4 de football-data.org (GET /competitions/{codigo}/matches).
La API simulada del proyecto (mock_api) expone exactamente el mismo contrato,
así que cambiar a la API real solo requiere otra URL y un token.
"""
from __future__ import annotations

import logging
from datetime import datetime

import httpx

from app.dominio.entidades import EstadoPartido, Partido

log = logging.getLogger(__name__)

_ESTADOS = {
    "SCHEDULED": EstadoPartido.PROGRAMADO,
    "TIMED": EstadoPartido.PROGRAMADO,
    "IN_PLAY": EstadoPartido.EN_JUEGO,
    "PAUSED": EstadoPartido.EN_JUEGO,
    "LIVE": EstadoPartido.EN_JUEGO,
    "FINISHED": EstadoPartido.FINALIZADO,
    "AWARDED": EstadoPartido.FINALIZADO,
    "POSTPONED": EstadoPartido.SUSPENDIDO,
    "SUSPENDED": EstadoPartido.SUSPENDIDO,
    "CANCELLED": EstadoPartido.SUSPENDIDO,
}


class ErrorApiPartidos(RuntimeError):
    pass


class ClienteApiPartidos:
    def __init__(self, url_base: str, token: str = "", timeout: float = 15.0, transporte=None):
        self.url_base = url_base.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.transporte = transporte  # permite inyectar un transporte falso en las pruebas

    def obtener_partidos(self, competicion: str, temporada: str = "") -> list[Partido]:
        cabeceras = {"X-Auth-Token": self.token} if self.token else {}
        parametros = {"season": temporada} if temporada else {}
        url = f"{self.url_base}/competitions/{competicion}/matches"
        try:
            with httpx.Client(timeout=self.timeout, transport=self.transporte) as http:
                respuesta = http.get(url, headers=cabeceras, params=parametros)
        except httpx.HTTPError as error:
            raise ErrorApiPartidos(f"No se pudo conectar con {url}: {error}") from error
        if respuesta.status_code != 200:
            raise ErrorApiPartidos(f"La API respondió {respuesta.status_code}: {respuesta.text[:200]}")
        cuerpo = respuesta.json()
        codigo = (cuerpo.get("competition") or {}).get("code") or competicion
        partidos = [self._convertir(item, codigo) for item in cuerpo.get("matches", [])]
        log.info("API de partidos: %d partidos recibidos de %s", len(partidos), url)
        return partidos

    @staticmethod
    def _convertir(item: dict, competicion: str) -> Partido:
        local = item.get("homeTeam") or {}
        visitante = item.get("awayTeam") or {}
        marcador = (item.get("score") or {}).get("fullTime") or {}
        return Partido(
            id_externo=int(item["id"]),
            competicion=competicion,
            etapa=item.get("stage") or "",
            jornada=item.get("matchday"),
            fecha_utc=datetime.fromisoformat(item["utcDate"].replace("Z", "+00:00")),
            estado=_ESTADOS.get(item.get("status", ""), EstadoPartido.PROGRAMADO),
            equipo_local=local.get("name") or "Por definir",
            equipo_visitante=visitante.get("name") or "Por definir",
            escudo_local=local.get("crest"),
            escudo_visitante=visitante.get("crest"),
            goles_local=marcador.get("home"),
            goles_visitante=marcador.get("away"),
        )
