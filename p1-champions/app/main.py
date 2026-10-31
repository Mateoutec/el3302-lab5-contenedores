"""Punto de entrada: arma las capas y sincroniza los partidos al iniciar."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import Config, cargar_config
from app.datos.cliente_api_partidos import ClienteApiPartidos
from app.datos.db import base_de_datos_disponible, crear_fabrica_sesiones, crear_motor, crear_tablas
from app.negocio.servicios import ServicioPartidos, ServicioPredicciones
from app.presentacion import api, web

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("champions")


def crear_app(config: Config | None = None, cliente: ClienteApiPartidos | None = None) -> FastAPI:
    config = config or cargar_config()
    motor = crear_motor(config.database_url)
    fabrica = crear_fabrica_sesiones(motor)
    cliente = cliente or ClienteApiPartidos(config.api_partidos_url, config.api_partidos_token)
    servicio_partidos = ServicioPartidos(fabrica, cliente, config.competicion, config.temporada)
    servicio_predicciones = ServicioPredicciones(fabrica)

    @asynccontextmanager
    async def ciclo_de_vida(app: FastAPI):
        crear_tablas(motor)
        if config.sincronizar_al_iniciar:
            # Requisito 2: al iniciar se guardan en la BD todos los partidos de la API.
            servicio_partidos.sincronizar_con_reintentos(config.intentos_sincronizacion)
        log.info("Partidos en la base de datos: %d", servicio_partidos.total())
        yield
        motor.dispose()

    app = FastAPI(
        title="Predicciones Champions League",
        description="Laboratorio 5 EL3302 — aplicación en 3 capas (presentación, negocio, datos).",
        version="1.0.0",
        lifespan=ciclo_de_vida,
    )
    app.state.config = config
    app.state.servicio_partidos = servicio_partidos
    app.state.servicio_predicciones = servicio_predicciones

    app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "presentacion" / "static")), name="static")
    app.include_router(web.router)
    app.include_router(api.router)

    @app.get("/health", tags=["Sistema"])
    def salud():
        ok = base_de_datos_disponible(motor)
        return JSONResponse({"estado": "ok" if ok else "sin_bd", "partidos": servicio_partidos.total() if ok else None},
                            status_code=200 if ok else 503)

    return app


app = crear_app()
