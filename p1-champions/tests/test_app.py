"""Pruebas de las tres capas con SQLite y la API simulada servida en memoria."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Config
from app.datos.cliente_api_partidos import ClienteApiPartidos, ErrorApiPartidos
from app.datos.db import crear_fabrica_sesiones, crear_motor, crear_tablas
from app.dominio.entidades import EstadoPartido, Partido, Prediccion, Resultado
from app.main import crear_app
from app.negocio.servicios import (
    PrediccionInvalida,
    ServicioPartidos,
    ServicioPredicciones,
    calcular_puntos,
)
from mock_api import main as mock


def _transporte_mock() -> httpx.MockTransport:
    def responder(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/competitions/CL/matches"):
            return httpx.Response(200, json=mock.partidos("CL"))
        return httpx.Response(404, json={"message": "no encontrado"})

    return httpx.MockTransport(responder)


def _config(tmp_path) -> Config:
    return Config(
        database_url=f"sqlite:///{tmp_path / 'prueba.db'}",
        api_partidos_url="http://mock-api:8081/v4",
        api_partidos_token="",
        competicion="CL",
        temporada="",
        sincronizar_al_iniciar=True,
        intentos_sincronizacion=1,
        zona_horaria="America/Lima",
    )


@pytest.fixture
def servicios(tmp_path):
    motor = crear_motor(f"sqlite:///{tmp_path / 'svc.db'}")
    crear_tablas(motor)
    fabrica = crear_fabrica_sesiones(motor)
    cliente = ClienteApiPartidos("http://mock-api:8081/v4", transporte=_transporte_mock())
    return ServicioPartidos(fabrica, cliente, "CL"), ServicioPredicciones(fabrica)


def test_mock_genera_fase_liga_valida():
    partidos = mock.generar_partidos()
    assert len(partidos) == 144
    rivales: dict[int, set[int]] = {}
    for p in partidos:
        local, visitante = p["homeTeam"]["id"], p["awayTeam"]["id"]
        rivales.setdefault(local, set()).add(visitante)
        rivales.setdefault(visitante, set()).add(local)
    assert len(rivales) == 36
    assert all(len(r) == 8 for r in rivales.values()), "cada equipo juega 8 rivales distintos"
    estados = {p["status"] for p in partidos}
    assert "FINISHED" in estados and "TIMED" in estados


def test_sincronizar_guarda_y_no_duplica(servicios):
    partidos, _ = servicios
    primero = partidos.sincronizar()
    assert (primero.recibidos, primero.nuevos, primero.actualizados) == (144, 144, 0)
    segundo = partidos.sincronizar()
    assert (segundo.nuevos, segundo.actualizados) == (0, 144)
    assert partidos.total() == 144
    assert partidos.jornadas() == list(range(1, 9))
    finalizados = partidos.listar(EstadoPartido.FINALIZADO)
    assert finalizados and all(p.goles_local is not None for p in finalizados)


def test_registrar_y_listar_prediccion(servicios):
    partidos, predicciones = servicios
    partidos.sincronizar()
    programado = partidos.listar(EstadoPartido.PROGRAMADO)[0]
    creada = predicciones.registrar(programado.id, "  Mateo ", "LOCAL", 2, 1)
    assert creada.id and creada.autor == "Mateo"
    todas = predicciones.listar()
    assert len(todas) == 1 and todas[0].partido.id == programado.id and todas[0].puntos is None
    assert partidos.predicciones_por_partido() == {programado.id: 1}


@pytest.mark.parametrize(
    "autor,resultado,gl,gv,mensaje",
    [
        ("", "LOCAL", 1, 0, "nombre"),
        ("Ana", "GANA", 1, 0, "LOCAL, EMPATE o VISITANTE"),
        ("Ana", "EMPATE", 2, 1, "no corresponde"),
        ("Ana", "VISITANTE", -1, 3, "entre 0 y 20"),
    ],
)
def test_validaciones_de_negocio(servicios, autor, resultado, gl, gv, mensaje):
    partidos, predicciones = servicios
    partidos.sincronizar()
    programado = partidos.listar(EstadoPartido.PROGRAMADO)[0]
    with pytest.raises(PrediccionInvalida, match=mensaje):
        predicciones.registrar(programado.id, autor, resultado, gl, gv)


def test_no_se_predice_partido_finalizado(servicios):
    partidos, predicciones = servicios
    partidos.sincronizar()
    finalizado = partidos.listar(EstadoPartido.FINALIZADO)[0]
    with pytest.raises(PrediccionInvalida, match="no han comenzado"):
        predicciones.registrar(finalizado.id, "Ana", "EMPATE", 1, 1)


def test_puntos():
    partido = Partido(id_externo=1, competicion="CL", etapa="LEAGUE_STAGE", jornada=1,
                      fecha_utc=datetime.now(timezone.utc) - timedelta(days=1),
                      estado=EstadoPartido.FINALIZADO, equipo_local="A", equipo_visitante="B",
                      goles_local=2, goles_visitante=1, id=1)

    def pred(gl, gv):
        return Prediccion(partido_id=1, autor="x", resultado=Resultado.desde_marcador(gl, gv),
                          goles_local=gl, goles_visitante=gv, partido=partido)

    assert calcular_puntos(pred(2, 1)) == 3
    assert calcular_puntos(pred(3, 0)) == 1
    assert calcular_puntos(pred(1, 1)) == 0


def test_cliente_reporta_error_http():
    transporte = httpx.MockTransport(lambda request: httpx.Response(403, json={"message": "token"}))
    cliente = ClienteApiPartidos("https://api.football-data.org/v4", "malo", transporte=transporte)
    with pytest.raises(ErrorApiPartidos, match="403"):
        cliente.obtener_partidos("CL")


def test_app_completa_web_y_api(tmp_path):
    cliente_api = ClienteApiPartidos("http://mock-api:8081/v4", transporte=_transporte_mock())
    app = crear_app(_config(tmp_path), cliente_api)
    with TestClient(app) as http:  # el ciclo de vida sincroniza al iniciar
        assert http.get("/health").json() == {"estado": "ok", "partidos": 144}
        assert "Partidos de la Champions League" in http.get("/").text
        programados = http.get("/api/partidos", params={"estado": "PROGRAMADO"}).json()
        partido_id = programados[0]["id"]

        r = http.post(f"/partidos/{partido_id}/predicciones",
                      data={"autor": "Mateo", "resultado": "EMPATE", "goles_local": "1", "goles_visitante": "1"},
                      follow_redirects=False)
        assert r.status_code == 303 and "ok=" in r.headers["location"]

        r = http.post("/api/predicciones", json={"partido_id": partido_id, "autor": "Lucía",
                                                 "resultado": "VISITANTE", "goles_local": 0, "goles_visitante": 2})
        assert r.status_code == 201

        r = http.post("/api/predicciones", json={"partido_id": partido_id, "autor": "Lucía",
                                                 "resultado": "LOCAL", "goles_local": 0, "goles_visitante": 2})
        assert r.status_code == 422

        lista = http.get("/api/predicciones").json()
        assert {p["autor"] for p in lista} == {"Mateo", "Lucía"}
        assert "Lucía" in http.get("/predicciones").text
        assert "Mateo" in http.get(f"/partidos/{partido_id}").text
        assert http.post("/api/sincronizar").json()["recibidos"] == 144
