"""Páginas HTML y API mínima de la app de marketing."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.dominio.entidades import EstadoCampana
from app.negocio.servicio_campanas import TONOS, CampanaNoEncontrada, ErrorNegocio, ServicioCampanas

plantillas = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
router = APIRouter()

PASOS = [
    ("Foto", {EstadoCampana.GENERANDO_GUIONES}),
    ("Guiones", {EstadoCampana.GUIONES_LISTOS}),
    ("Contenido", {EstadoCampana.GENERANDO_CONTENIDO, EstadoCampana.CONTENIDO_LISTO, EstadoCampana.PUBLICANDO}),
    ("Publicación", {EstadoCampana.PUBLICADA}),
]


def _servicio(request: Request) -> ServicioCampanas:
    return request.app.state.servicio


def _render(request: Request, plantilla: str, **contexto):
    config = request.app.state.config
    contexto.update(
        request=request,
        ok=request.query_params.get("ok"),
        error=request.query_params.get("error"),
        modo_publicacion=config.modo_publicacion,
        proveedor_guiones=request.app.state.servicio.guiones.nombre,
        proveedor_imagenes=request.app.state.servicio.imagenes.nombre,
    )
    return plantillas.TemplateResponse(request, plantilla, contexto)


def _redirigir(url: str, ok: str = "", error: str = "") -> RedirectResponse:
    if ok:
        url += ("&" if "?" in url else "?") + "ok=" + quote(ok)
    if error:
        url += ("&" if "?" in url else "?") + "error=" + quote(error)
    return RedirectResponse(url, status_code=303)


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def inicio(request: Request):
    return _render(request, "inicio.html", campanas=_servicio(request).listar()[:12], tonos=TONOS)


@router.post("/campanas", include_in_schema=False)
async def crear_campana(request: Request, tareas: BackgroundTasks,
                        empresa: str = Form(""), producto: str = Form(""), publico: str = Form(""),
                        tono: str = Form("Cercano"), red_social: str = Form("INSTAGRAM"),
                        foto: UploadFile | None = File(None)):
    servicio = _servicio(request)
    contenido = await foto.read() if foto is not None else b""
    try:
        campana = servicio.crear(empresa, producto, publico, tono, red_social, contenido,
                                 foto.content_type if foto is not None else "")
    except ErrorNegocio as error:
        return _redirigir("/", error=str(error))
    tareas.add_task(servicio.generar_guiones, campana.id)
    return _redirigir(f"/campanas/{campana.id}")


@router.get("/campanas/{campana_id}", response_class=HTMLResponse, include_in_schema=False)
def ver_campana(request: Request, campana_id: int):
    try:
        campana = _servicio(request).obtener(campana_id)
    except CampanaNoEncontrada:
        return _redirigir("/", error="La campaña no existe.")
    paso = next((i for i, (_, estados) in enumerate(PASOS) if campana.estado in estados), 0)
    if campana.estado == EstadoCampana.ERROR:
        paso = 2 if campana.guion_elegido_id else 0
    return _render(request, "campana.html", campana=campana, pasos=[n for n, _ in PASOS], paso=paso)


@router.post("/campanas/{campana_id}/guiones/{guion_id}", include_in_schema=False)
def elegir_guion(request: Request, tareas: BackgroundTasks, campana_id: int, guion_id: int):
    servicio = _servicio(request)
    try:
        servicio.elegir_guion(campana_id, guion_id)
    except ErrorNegocio as error:
        return _redirigir(f"/campanas/{campana_id}", error=str(error))
    tareas.add_task(servicio.generar_contenido, campana_id)
    return _redirigir(f"/campanas/{campana_id}")


@router.post("/campanas/{campana_id}/publicar", include_in_schema=False)
def publicar(request: Request, tareas: BackgroundTasks, campana_id: int):
    servicio = _servicio(request)
    try:
        servicio.solicitar_publicacion(campana_id)
    except ErrorNegocio as error:
        return _redirigir(f"/campanas/{campana_id}", error=str(error))
    tareas.add_task(servicio.publicar, campana_id)
    return _redirigir(f"/campanas/{campana_id}")


@router.post("/campanas/{campana_id}/reintentar", include_in_schema=False)
def reintentar(request: Request, tareas: BackgroundTasks, campana_id: int):
    servicio = _servicio(request)
    try:
        paso = servicio.reintentar(campana_id)
    except ErrorNegocio as error:
        return _redirigir(f"/campanas/{campana_id}", error=str(error))
    tareas.add_task(servicio.generar_contenido if paso == "contenido" else servicio.generar_guiones, campana_id)
    return _redirigir(f"/campanas/{campana_id}")


@router.get("/campanas/{campana_id}/publicacion", response_class=HTMLResponse, include_in_schema=False)
def vista_publicacion(request: Request, campana_id: int):
    try:
        campana = _servicio(request).obtener(campana_id)
    except CampanaNoEncontrada:
        return _redirigir("/", error="La campaña no existe.")
    if not campana.publicaciones:
        return _redirigir(f"/campanas/{campana_id}", error="La campaña aún no se publica.")
    return _render(request, "publicacion.html", campana=campana, publicacion=campana.publicaciones[-1])


@router.get("/api/campanas/{campana_id}", tags=["API"])
def api_campana(request: Request, campana_id: int):
    try:
        campana = _servicio(request).obtener(campana_id)
    except CampanaNoEncontrada:
        raise HTTPException(404, "La campaña no existe") from None
    datos = asdict(campana)
    datos["estado"] = campana.estado.value
    return datos


@router.get("/api/campanas", tags=["API"])
def api_campanas(request: Request):
    return [
        {"id": c.id, "empresa": c.brief.empresa, "producto": c.brief.producto, "estado": c.estado.value,
         "red_social": c.brief.red_social.value, "guiones": len(c.guiones), "recursos": len(c.recursos),
         "publicaciones": len(c.publicaciones), "creado_en": c.creado_en}
        for c in _servicio(request).listar()
    ]
