"""Páginas HTML (Jinja2) de la capa de presentación."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.datos.cliente_api_partidos import ErrorApiPartidos
from app.dominio.entidades import EstadoPartido
from app.negocio.servicios import (
    ErrorNegocio,
    PartidoNoEncontrado,
    ServicioPartidos,
    ServicioPredicciones,
)
from app.presentacion.dependencias import servicio_partidos, servicio_predicciones

plantillas = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
router = APIRouter(include_in_schema=False)

ETAPAS = {
    "LEAGUE_STAGE": "Fase liga",
    "PLAYOFFS": "Play-off",
    "LAST_16": "Octavos",
    "QUARTER_FINALS": "Cuartos",
    "SEMI_FINALS": "Semifinal",
    "FINAL": "Final",
}
ESTADOS = {
    "PROGRAMADO": "Programado",
    "EN_JUEGO": "En juego",
    "FINALIZADO": "Finalizado",
    "SUSPENDIDO": "Suspendido",
}


def _fecha_local(request: Request, fecha, formato: str = "%d/%m/%Y %H:%M") -> str:
    zona = ZoneInfo(request.app.state.config.zona_horaria)
    return fecha.astimezone(zona).strftime(formato)


def _render(request: Request, plantilla: str, **contexto):
    contexto.update(
        request=request,
        ok=request.query_params.get("ok"),
        error=request.query_params.get("error"),
        etapas=ETAPAS,
        estados=ESTADOS,
        fecha_local=lambda fecha, formato="%d/%m/%Y %H:%M": _fecha_local(request, fecha, formato),
        zona=request.app.state.config.zona_horaria,
        fuente=request.app.state.config.api_partidos_url,
    )
    return plantillas.TemplateResponse(request, plantilla, contexto)


@router.get("/", response_class=HTMLResponse)
def inicio(request: Request, estado: str = "", jornada: str = "",
           servicio: ServicioPartidos = Depends(servicio_partidos)):
    estado_filtro = EstadoPartido(estado) if estado in EstadoPartido.__members__ else None
    jornada_filtro = int(jornada) if jornada.isdigit() else None
    partidos = servicio.listar(estado_filtro, jornada_filtro)
    return _render(
        request, "partidos.html",
        partidos=partidos,
        total=servicio.total(),
        jornadas=servicio.jornadas(),
        conteo_predicciones=servicio.predicciones_por_partido(),
        estado_sel=estado, jornada_sel=jornada,
    )


@router.get("/partidos/{partido_id}", response_class=HTMLResponse)
def detalle_partido(request: Request, partido_id: int,
                    partidos: ServicioPartidos = Depends(servicio_partidos),
                    predicciones: ServicioPredicciones = Depends(servicio_predicciones)):
    try:
        partido = partidos.obtener(partido_id)
    except PartidoNoEncontrado:
        return RedirectResponse("/?error=" + quote("El partido no existe."), status_code=303)
    return _render(request, "partido.html", partido=partido, predicciones=predicciones.listar(partido_id))


@router.post("/partidos/{partido_id}/predicciones")
def registrar_prediccion(partido_id: int,
                         autor: str = Form(""),
                         resultado: str = Form(""),
                         goles_local: str = Form(""),
                         goles_visitante: str = Form(""),
                         servicio: ServicioPredicciones = Depends(servicio_predicciones)):
    destino = f"/partidos/{partido_id}"
    if not (goles_local.strip().isdigit() and goles_visitante.strip().isdigit()):
        return RedirectResponse(destino + "?error=" + quote("Ingresa el marcador estimado (números enteros)."), status_code=303)
    try:
        servicio.registrar(partido_id, autor, resultado, int(goles_local), int(goles_visitante))
    except ErrorNegocio as error:
        return RedirectResponse(destino + "?error=" + quote(str(error)), status_code=303)
    return RedirectResponse(destino + "?ok=" + quote("Predicción registrada."), status_code=303)


@router.get("/predicciones", response_class=HTMLResponse)
def listar_predicciones(request: Request, servicio: ServicioPredicciones = Depends(servicio_predicciones)):
    predicciones = servicio.listar()
    ranking: dict[str, int] = {}
    for p in predicciones:
        if p.puntos is not None:
            ranking[p.autor] = ranking.get(p.autor, 0) + p.puntos
    return _render(
        request, "predicciones.html",
        predicciones=predicciones,
        ranking=sorted(ranking.items(), key=lambda par: (-par[1], par[0])),
    )


@router.post("/sincronizar")
def sincronizar(servicio: ServicioPartidos = Depends(servicio_partidos)):
    try:
        resumen = servicio.sincronizar()
    except ErrorApiPartidos as error:
        return RedirectResponse("/?error=" + quote(f"No se pudo sincronizar: {error}"), status_code=303)
    mensaje = f"Sincronizado: {resumen.recibidos} partidos ({resumen.nuevos} nuevos, {resumen.actualizados} actualizados)."
    return RedirectResponse("/?ok=" + quote(mensaje), status_code=303)
