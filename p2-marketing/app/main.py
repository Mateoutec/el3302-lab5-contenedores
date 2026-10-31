"""Punto de entrada de la app de marketing: arma dependencias y monta las rutas."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import Config, cargar_config
from app.datos.almacen import AlmacenArchivos
from app.datos.db import base_de_datos_disponible, crear_fabrica_sesiones, crear_motor, crear_tablas
from app.datos.repositorio import RepositorioCampanas
from app.negocio.servicio_campanas import ServicioCampanas
from app.presentacion import web
from app.proveedores.guiones import crear_generador_guiones
from app.proveedores.imagenes import crear_generador_imagenes
from app.proveedores.redes import crear_publicador
from app.proveedores.video import GeneradorVideo

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("marketing")


def crear_app(config: Config | None = None, **reemplazos) -> FastAPI:
    """`reemplazos` permite inyectar generadores falsos en las pruebas."""
    config = config or cargar_config()
    motor = crear_motor(config.database_url)
    fabrica = crear_fabrica_sesiones(motor)
    almacen = AlmacenArchivos(config.media_dir)
    servicio = ServicioCampanas(
        fabrica, almacen,
        guiones=reemplazos.get("guiones") or crear_generador_guiones(config.proveedor_guiones, config.modelo_claude),
        imagenes=reemplazos.get("imagenes") or crear_generador_imagenes(config.proveedor_imagenes,
                                                                       config.modelo_imagen_openai),
        video=reemplazos.get("video") or GeneradorVideo(),
        publicador_para=reemplazos.get("publicador_para") or (lambda red: crear_publicador(config, red)),
        url_publica=config.url_publica,
        max_mb_foto=config.max_mb_foto,
    )

    @asynccontextmanager
    async def ciclo_de_vida(app: FastAPI):
        crear_tablas(motor)
        with fabrica.begin() as sesion:
            interrumpidas = RepositorioCampanas(sesion).marcar_interrumpidas()
        if interrumpidas:
            log.warning("%d campañas quedaron interrumpidas por un reinicio", interrumpidas)
        log.info("Guiones: %s | Imágenes: %s | Publicación: %s",
                 servicio.guiones.nombre, servicio.imagenes.nombre, config.modo_publicacion)
        yield
        motor.dispose()

    app = FastAPI(title="Marketing con IA para empresas", version="1.0.0",
                  description="Laboratorio 5 EL3302 — Pregunta 2", lifespan=ciclo_de_vida)
    app.state.config = config
    app.state.servicio = servicio
    app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "presentacion" / "static")), name="static")
    app.mount("/media", StaticFiles(directory=str(config.media_dir)), name="media")
    app.include_router(web.router)

    @app.get("/health", tags=["Sistema"])
    def salud():
        ok = base_de_datos_disponible(motor)
        return JSONResponse({"estado": "ok" if ok else "sin_bd"}, status_code=200 if ok else 503)

    return app


app = crear_app()
