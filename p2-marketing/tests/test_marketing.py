"""Pruebas de la app de marketing (sin claves: plantillas, Pillow, FFmpeg y publicación simulada)."""
from __future__ import annotations

import io
import json
import shutil
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from app.config import cargar_config
from app.dominio.entidades import Brief, Campana, EstadoCampana, RedSocial
from app.main import crear_app
from app.proveedores.guiones import (
    ErrorProveedor,
    GeneradorGuionesClaude,
    GeneradorGuionesPlantilla,
    _esquema_estricto,
    _RespuestaIA,
)
from app.proveedores.imagenes import GeneradorImagenesLocal
from app.proveedores.redes import PublicadorInstagram, PublicadorTikTok
from app.proveedores.video import GeneradorVideo

HAY_FFMPEG = shutil.which("ffmpeg") is not None


def foto_de_prueba(ancho=900, alto=1200) -> Image.Image:
    imagen = Image.new("RGB", (ancho, alto), (236, 228, 214))
    dibujo = ImageDraw.Draw(imagen)
    dibujo.rounded_rectangle((250, 300, 650, 1000), 40, fill=(120, 72, 40))
    dibujo.rectangle((250, 520, 650, 700), fill=(214, 90, 60))
    return imagen


def bytes_jpeg(imagen: Image.Image) -> bytes:
    buffer = io.BytesIO()
    imagen.save(buffer, format="JPEG")
    return buffer.getvalue()


BRIEF = Brief(empresa="Café Altura", producto="café de especialidad 250 g", publico="oficinistas",
              tono="Cercano", red_social=RedSocial.INSTAGRAM)


def test_plantillas_proponen_tres_guiones_de_tres_escenas():
    propuesta = GeneradorGuionesPlantilla().proponer(BRIEF, foto_de_prueba())
    assert len(propuesta.guiones) == 3
    assert all(len(g.escenas) == 3 for g in propuesta.guiones)
    assert len({g.titulo for g in propuesta.guiones}) == 3
    assert "Foto vertical" in propuesta.descripcion_foto
    assert all(h.startswith("#") for g in propuesta.guiones for h in g.hashtags)


def _respuesta_claude(datos: dict, stop_reason="end_turn"):
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=json.dumps(datos))],
    )


class ClienteFalso:
    def __init__(self, respuesta):
        self.respuesta = respuesta
        self.llamadas = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._crear))

    def _crear(self, **kwargs):
        self.llamadas.append(kwargs)
        return self.respuesta


def _guion_ia(n):
    escena = {"texto_en_pantalla": f"Texto {n}", "descripcion_visual": "plano cerrado", "narracion": "voz"}
    return {"titulo": f"Guion {n}", "enfoque": "x", "gancho": "y", "escenas": [escena] * 3,
            "llamado_accion": "Compra", "caption": "Caption", "hashtags": ["cafe", "#peru"]}


def test_claude_parsea_salida_estructurada():
    cliente = ClienteFalso(_respuesta_claude({"descripcion_foto": "Una bolsa de café",
                                              "guiones": [_guion_ia(i) for i in range(1, 4)]}))
    propuesta = GeneradorGuionesClaude("claude-opus-5-5", cliente=cliente).proponer(BRIEF, foto_de_prueba())
    assert propuesta.proveedor == "claude:claude-opus-5-5"
    assert [g.titulo for g in propuesta.guiones] == ["Guion 1", "Guion 2", "Guion 3"]
    assert propuesta.guiones[0].hashtags == ["#cafe", "#peru"]
    llamada = cliente.llamadas[0]
    assert llamada["model"] == "claude-opus-5-5" and llamada["fallbacks"] == "default"
    assert llamada["output_config"]["format"]["type"] == "json_schema"
    assert llamada["messages"][0]["content"][0]["type"] == "image"


def test_claude_rechazo_y_respuesta_incompleta():
    rechazo = ClienteFalso(_respuesta_claude({}, stop_reason="refusal"))
    with pytest.raises(ErrorProveedor, match="no pudo"):
        GeneradorGuionesClaude(cliente=rechazo).proponer(BRIEF, foto_de_prueba())
    pocos = ClienteFalso(_respuesta_claude({"descripcion_foto": "x", "guiones": [_guion_ia(1)]}))
    with pytest.raises(ErrorProveedor, match="menos de 3"):
        GeneradorGuionesClaude(cliente=pocos).proponer(BRIEF, foto_de_prueba())


def test_esquema_estricto_cierra_todos_los_objetos():
    esquema = _esquema_estricto(_RespuestaIA)
    guion = esquema["properties"]["guiones"]["items"]
    escena = guion["properties"]["escenas"]["items"]
    for nodo in (esquema, guion, escena):
        assert nodo["additionalProperties"] is False
        assert set(nodo["required"]) == set(nodo["properties"])
    assert "$defs" not in json.dumps(esquema) and "$ref" not in json.dumps(esquema)


def test_imagenes_locales():
    guion = GeneradorGuionesPlantilla().proponer(BRIEF, foto_de_prueba()).guiones[0]
    piezas = GeneradorImagenesLocal().generar(foto_de_prueba(), BRIEF, guion, ["#784828", "#d65a3c", "#ece4d6"])
    assert [p.size for p in piezas] == [(1080, 1350)] * 3


@pytest.mark.skipif(not HAY_FFMPEG, reason="FFmpeg no instalado")
def test_video(tmp_path):
    guion = GeneradorGuionesPlantilla().proponer(BRIEF, foto_de_prueba()).guiones[0]
    piezas = GeneradorImagenesLocal().generar(foto_de_prueba(), BRIEF, guion, ["#784828"])
    video = GeneradorVideo().generar(piezas, BRIEF, guion, (120, 72, 40), tmp_path)
    assert video.exists() and video.stat().st_size > 50_000
    assert not list(tmp_path.glob("_cuadro_*"))
    assert (tmp_path / "video_portada.jpg").exists()


def _campana_publicable(tmp_path):
    fotos = []
    for i in range(3):
        ruta = tmp_path / f"foto_{i}.jpg"
        foto_de_prueba().save(ruta)
        fotos.append(ruta)
    video = tmp_path / "video.mp4"
    video.write_bytes(b"\x00" * 1000)
    guion = GeneradorGuionesPlantilla().proponer(BRIEF, foto_de_prueba()).guiones[0]
    campana = Campana(brief=BRIEF, foto="x.jpg", estado=EstadoCampana.CONTENIDO_LISTO, id=7)
    return campana, guion, fotos, video


def test_instagram_publica_carrusel_y_reel(tmp_path):
    llamadas = []

    def responder(request: httpx.Request) -> httpx.Response:
        llamadas.append((request.method, request.url.path))
        if request.method == "GET" and "fields=status_code" in str(request.url):
            return httpx.Response(200, json={"status_code": "FINISHED"})
        if request.method == "GET":
            return httpx.Response(200, json={"permalink": "https://www.instagram.com/p/abc/"})
        return httpx.Response(200, json={"id": f"id{len(llamadas)}"})

    campana, guion, fotos, video = _campana_publicable(tmp_path)
    publicador = PublicadorInstagram("1784", "token", "v23.0", transporte=httpx.MockTransport(responder), espera_s=0)
    publicacion = publicador.publicar(campana, guion, fotos, video, lambda p: f"https://demo/media/{p.name}")
    assert publicacion.modo == "REAL" and publicacion.url == "https://www.instagram.com/p/abc/"
    posts = [ruta for metodo, ruta in llamadas if metodo == "POST"]
    assert posts.count("/v23.0/1784/media") == 5 and posts.count("/v23.0/1784/media_publish") == 2


def test_tiktok_sube_video(tmp_path):
    def responder(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/video/init/"):
            cuerpo = json.loads(request.content)
            assert cuerpo["source_info"]["video_size"] == 1000
            return httpx.Response(200, json={"data": {"publish_id": "p_1", "upload_url": "https://subida.tiktok/x"},
                                             "error": {"code": "ok"}})
        if request.method == "PUT":
            assert request.headers["Content-Range"] == "bytes 0-999/1000"
            return httpx.Response(201)
        return httpx.Response(200, json={"data": {"status": "PUBLISH_COMPLETE"}, "error": {"code": "ok"}})

    campana, guion, fotos, video = _campana_publicable(tmp_path)
    publicador = PublicadorTikTok("token", transporte=httpx.MockTransport(responder), espera_s=0)
    publicacion = publicador.publicar(campana, guion, fotos, video, lambda p: "")
    assert publicacion.id_externo == "p_1" and "PUBLISH_COMPLETE" in publicacion.detalle


def test_credenciales_faltantes():
    with pytest.raises(ErrorProveedor, match="IG_USER_ID"):
        PublicadorInstagram("", "", "v23.0")
    with pytest.raises(ErrorProveedor, match="TIKTOK_ACCESS_TOKEN"):
        PublicadorTikTok("")


@pytest.fixture
def cliente_http(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'm.db'}")
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path / "media"))
    monkeypatch.setenv("PROVEEDOR_GUIONES", "plantilla")
    monkeypatch.setenv("MODO_PUBLICACION", "simulado")
    with TestClient(crear_app(cargar_config())) as http:
        yield http


@pytest.mark.skipif(not HAY_FFMPEG, reason="FFmpeg no instalado")
def test_flujo_completo(cliente_http):
    http = cliente_http
    r = http.post("/campanas", data={"empresa": "Café Altura", "producto": "café 250 g", "publico": "oficinistas",
                                     "tono": "Cercano", "red_social": "INSTAGRAM"},
                  files={"foto": ("cafe.jpg", bytes_jpeg(foto_de_prueba()), "image/jpeg")}, follow_redirects=False)
    assert r.status_code == 303
    url = r.headers["location"]
    campana = http.get("/api/campanas/1").json()
    assert campana["estado"] == "GUIONES_LISTOS" and len(campana["guiones"]) == 3
    assert "Guiones propuestos" in http.get(url).text

    guion_id = campana["guiones"][1]["id"]
    http.post(f"/campanas/1/guiones/{guion_id}", follow_redirects=False)
    campana = http.get("/api/campanas/1").json()
    assert campana["estado"] == "CONTENIDO_LISTO", campana["error"]
    assert sorted(r["tipo"] for r in campana["recursos"]) == ["FOTO", "FOTO", "FOTO", "VIDEO"]
    for recurso in campana["recursos"]:
        assert http.get(f"/media/{recurso['ruta']}").status_code == 200

    http.post("/campanas/1/publicar", follow_redirects=False)
    campana = http.get("/api/campanas/1").json()
    assert campana["estado"] == "PUBLICADA"
    assert campana["publicaciones"][0]["modo"] == "SIMULADO"
    assert "Vista previa de la publicación" in http.get("/campanas/1/publicacion").text
    assert http.get("/api/campanas").json()[0]["publicaciones"] == 1


@pytest.mark.parametrize(
    "datos,archivo,mensaje",
    [
        ({"empresa": "A", "producto": "café"}, True, "empresa"),
        ({"empresa": "Café", "producto": "café", "tono": "Raro"}, True, "tono"),
        ({"empresa": "Café", "producto": "café"}, False, "imagen"),
    ],
)
def test_validaciones(cliente_http, datos, archivo, mensaje):
    base = {"publico": "", "tono": "Cercano", "red_social": "INSTAGRAM"}
    contenido = bytes_jpeg(foto_de_prueba()) if archivo else b"esto no es una imagen"
    r = cliente_http.post("/campanas", data={**base, **datos},
                          files={"foto": ("f.jpg", contenido, "image/jpeg")}, follow_redirects=False)
    assert r.status_code == 303 and "error=" in r.headers["location"]
    assert mensaje in httpx.URL(r.headers["location"]).params["error"]
