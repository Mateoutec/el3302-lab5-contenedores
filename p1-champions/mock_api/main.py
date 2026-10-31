"""API simulada de partidos de la Champions League.

Imita el contrato v4 de football-data.org (GET /v4/competitions/CL/matches)
para que la app funcione sin token. Genera la fase liga (36 equipos, 8
jornadas, 144 partidos) con un calendario anclado a la fecha de arranque:
las 3 primeras jornadas ya se jugaron y las 5 siguientes están programadas,
de modo que siempre hay partidos para predecir. Los marcadores son
pseudoaleatorios pero deterministas (misma semilla, mismos goles).
Los datos son SIMULADOS: no corresponden a resultados reales.
"""
from __future__ import annotations

import os
import random
from datetime import date, datetime, time, timedelta, timezone

from fastapi import FastAPI, HTTPException

EQUIPOS = [
    ("Real Madrid CF", "RMA"), ("FC Barcelona", "BAR"), ("Club Atlético de Madrid", "ATM"),
    ("Athletic Club", "ATH"), ("Villarreal CF", "VIL"), ("Manchester City FC", "MCI"),
    ("Arsenal FC", "ARS"), ("Liverpool FC", "LIV"), ("Chelsea FC", "CHE"),
    ("Tottenham Hotspur FC", "TOT"), ("Newcastle United FC", "NEW"), ("FC Bayern München", "FCB"),
    ("Borussia Dortmund", "BVB"), ("Bayer 04 Leverkusen", "B04"), ("Eintracht Frankfurt", "SGE"),
    ("FC Internazionale Milano", "INT"), ("SSC Napoli", "NAP"), ("Juventus FC", "JUV"),
    ("Atalanta BC", "ATA"), ("Paris Saint-Germain FC", "PSG"), ("Olympique de Marseille", "OM"),
    ("AS Monaco FC", "ASM"), ("SL Benfica", "BEN"), ("Sporting CP", "SCP"),
    ("FC Porto", "POR"), ("PSV", "PSV"), ("AFC Ajax", "AJA"), ("Feyenoord", "FEY"),
    ("Club Brugge KV", "BRU"), ("Royale Union Saint-Gilloise", "USG"), ("Galatasaray SK", "GAL"),
    ("Olympiakos", "OLY"), ("SK Slavia Praha", "SLA"), ("FC København", "FCK"),
    ("FK Bodø/Glimt", "BOD"), ("Celtic FC", "CEL"),
]
JORNADAS = 8
JORNADAS_JUGADAS = 3
DIAS_ENTRE_JORNADAS = 14
DURACION_PARTIDO = timedelta(hours=2)
SEMILLA = int(os.getenv("MOCK_SEMILLA", "2026"))


def _ancla() -> date:
    """Día de la jornada 4 (la primera por jugarse). Fijable con MOCK_FECHA_ANCLA=AAAA-MM-DD."""
    valor = os.getenv("MOCK_FECHA_ANCLA")
    if valor:
        return date.fromisoformat(valor)
    return datetime.now(timezone.utc).date() + timedelta(days=3)


ANCLA = _ancla()


def _emparejamientos() -> list[list[tuple[int, int]]]:
    """Método del círculo: 8 rondas sin repetir rival, alternando localía."""
    n = len(EQUIPOS)
    orden = list(range(n))
    rondas = []
    for r in range(JORNADAS):
        ronda = []
        for k in range(n // 2):
            a, b = orden[k], orden[n - 1 - k]
            ronda.append((a, b) if (r + k) % 2 == 0 else (b, a))
        rondas.append(ronda)
        orden = [orden[0], orden[-1]] + orden[1:-1]
    return rondas


def _goles(rng: random.Random) -> int:
    return rng.choices([0, 1, 2, 3, 4, 5], weights=[24, 33, 24, 12, 5, 2])[0]


def _equipo(indice: int) -> dict:
    nombre, tla = EQUIPOS[indice]
    return {"id": 1000 + indice, "name": nombre, "shortName": nombre, "tla": tla, "crest": None}


def generar_partidos(ahora: datetime | None = None) -> list[dict]:
    ahora = ahora or datetime.now(timezone.utc)
    partidos = []
    for j, ronda in enumerate(_emparejamientos(), start=1):
        dia_inicio = ANCLA + timedelta(days=(j - (JORNADAS_JUGADAS + 1)) * DIAS_ENTRE_JORNADAS)
        for k, (local, visitante) in enumerate(ronda):
            dia = dia_inicio + timedelta(days=0 if k < 9 else 1)
            hora = time(17, 45) if k % 9 < 2 else time(20, 0)
            inicio = datetime.combine(dia, hora, tzinfo=timezone.utc)
            id_partido = 500000 + j * 100 + k
            if ahora >= inicio + DURACION_PARTIDO:
                estado = "FINISHED"
            elif ahora >= inicio:
                estado = "IN_PLAY"
            else:
                estado = "TIMED"
            rng = random.Random(SEMILLA * 1_000_003 + id_partido)
            goles_l, goles_v = _goles(rng), _goles(rng)
            terminado = estado == "FINISHED"
            ganador = None
            if terminado:
                ganador = "HOME_TEAM" if goles_l > goles_v else "AWAY_TEAM" if goles_v > goles_l else "DRAW"
            partidos.append({
                "id": id_partido,
                "utcDate": inicio.isoformat().replace("+00:00", "Z"),
                "status": estado,
                "matchday": j,
                "stage": "LEAGUE_STAGE",
                "group": None,
                "lastUpdated": ahora.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                "homeTeam": _equipo(local),
                "awayTeam": _equipo(visitante),
                "score": {
                    "winner": ganador,
                    "duration": "REGULAR",
                    "fullTime": {"home": goles_l if terminado else None, "away": goles_v if terminado else None},
                },
            })
    return partidos


COMPETICION = {"id": 2001, "name": "UEFA Champions League", "code": "CL", "type": "CUP", "emblem": None}

app = FastAPI(title="API simulada de partidos (contrato football-data.org v4)", version="1.0.0")


@app.get("/health")
def salud():
    return {"estado": "ok", "ancla_jornada_4": ANCLA.isoformat()}


@app.get("/v4/competitions/{codigo}")
def competicion(codigo: str):
    if codigo.upper() != "CL":
        raise HTTPException(404, "Solo se simula la competición CL")
    return COMPETICION


@app.get("/v4/competitions/{codigo}/matches")
def partidos(codigo: str, matchday: int | None = None, status: str | None = None, season: str | None = None):
    if codigo.upper() != "CL":
        raise HTTPException(404, "Solo se simula la competición CL")
    lista = generar_partidos()
    if matchday is not None:
        lista = [p for p in lista if p["matchday"] == matchday]
    if status:
        estados = set(status.upper().split(","))
        lista = [p for p in lista if p["status"] in estados]
    return {
        "filters": {"season": season or "simulada"},
        "resultSet": {"count": len(lista), "played": sum(p["status"] == "FINISHED" for p in lista)},
        "competition": COMPETICION,
        "simulado": True,
        "matches": lista,
    }
