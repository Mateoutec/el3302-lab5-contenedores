"""Publicación en redes sociales: simulada, Instagram Graph API o TikTok Content Posting API."""
from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path
from typing import Protocol

import httpx

from app.config import Config
from app.dominio.entidades import Campana, Guion, Publicacion, RedSocial
from app.proveedores.guiones import ErrorProveedor

log = logging.getLogger(__name__)


class Publicador(Protocol):
    def publicar(self, campana: Campana, guion: Guion, fotos: list[Path], video: Path,
                 url_de: callable) -> Publicacion: ...


class PublicadorSimulado:
    """No llama a ninguna red: registra la publicación y muestra una vista previa en la app."""

    def publicar(self, campana, guion, fotos, video, url_de) -> Publicacion:
        return Publicacion(
            red_social=campana.brief.red_social,
            modo="SIMULADO",
            estado="PUBLICADO",
            id_externo=f"sim-{uuid.uuid4().hex[:10]}",
            url=f"/campanas/{campana.id}/publicacion",
            detalle=(f"Publicación simulada en {campana.brief.red_social.value.title()}: "
                     f"carrusel de {len(fotos)} fotos + video vertical."),
        )


class PublicadorInstagram:
    """Instagram Graph API (cuenta profesional). Las fotos y el video deben estar en una URL pública."""

    def __init__(self, user_id: str, token: str, version: str, host: str = "https://graph.facebook.com",
                 transporte=None, espera_s: float = 5.0):
        if not (user_id and token):
            raise ErrorProveedor("Faltan IG_USER_ID e IG_ACCESS_TOKEN para publicar en Instagram.")
        self.base = f"{host.rstrip('/')}/{version}"
        self.user_id, self.token = user_id, token
        self.transporte, self.espera_s = transporte, espera_s

    def _post(self, http: httpx.Client, ruta: str, **datos) -> dict:
        r = http.post(f"{self.base}/{ruta}", data={**datos, "access_token": self.token})
        if r.status_code != 200:
            raise ErrorProveedor(f"Instagram respondió {r.status_code}: {r.text[:300]}")
        return r.json()

    def _get(self, http: httpx.Client, ruta: str, **params) -> dict:
        r = http.get(f"{self.base}/{ruta}", params={**params, "access_token": self.token})
        if r.status_code != 200:
            raise ErrorProveedor(f"Instagram respondió {r.status_code}: {r.text[:300]}")
        return r.json()

    def _esperar_contenedor(self, http: httpx.Client, contenedor: str, intentos: int = 36) -> None:
        for _ in range(intentos):
            estado = self._get(http, contenedor, fields="status_code").get("status_code")
            if estado == "FINISHED":
                return
            if estado in {"ERROR", "EXPIRED"}:
                raise ErrorProveedor(f"Instagram no pudo procesar el video (estado {estado}).")
            time.sleep(self.espera_s)
        raise ErrorProveedor("Instagram tardó demasiado en procesar el video.")

    def publicar(self, campana, guion, fotos, video, url_de) -> Publicacion:
        texto = guion.texto_publicacion()[:2200]
        with httpx.Client(timeout=60, transport=self.transporte) as http:
            hijos = [self._post(http, f"{self.user_id}/media", image_url=url_de(f), is_carousel_item="true")["id"]
                     for f in fotos]
            carrusel = self._post(http, f"{self.user_id}/media", media_type="CAROUSEL",
                                  children=",".join(hijos), caption=texto)["id"]
            id_carrusel = self._post(http, f"{self.user_id}/media_publish", creation_id=carrusel)["id"]
            reel = self._post(http, f"{self.user_id}/media", media_type="REELS", video_url=url_de(video),
                              caption=texto, share_to_feed="true")["id"]
            self._esperar_contenedor(http, reel)
            id_reel = self._post(http, f"{self.user_id}/media_publish", creation_id=reel)["id"]
            enlace = self._get(http, id_carrusel, fields="permalink").get("permalink", "")
        return Publicacion(red_social=RedSocial.INSTAGRAM, modo="REAL", estado="PUBLICADO",
                           id_externo=f"{id_carrusel},{id_reel}", url=enlace,
                           detalle=f"Carrusel {id_carrusel} y Reel {id_reel} publicados.")


class PublicadorTikTok:
    """TikTok Content Posting API (Direct Post, subida del archivo). Las apps sin auditar
    solo pueden publicar en privado (SELF_ONLY)."""

    BASE = "https://open.tiktokapis.com/v2/post/publish"

    def __init__(self, token: str, privacidad: str = "SELF_ONLY", transporte=None, espera_s: float = 5.0):
        if not token:
            raise ErrorProveedor("Falta TIKTOK_ACCESS_TOKEN para publicar en TikTok.")
        self.token, self.privacidad = token, privacidad
        self.transporte, self.espera_s = transporte, espera_s

    def publicar(self, campana, guion, fotos, video, url_de) -> Publicacion:
        datos = Path(video).read_bytes()
        cabeceras = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json; charset=UTF-8"}
        cuerpo = {
            "post_info": {"title": guion.texto_publicacion()[:2200], "privacy_level": self.privacidad,
                          "disable_duet": False, "disable_comment": False, "disable_stitch": False},
            "source_info": {"source": "FILE_UPLOAD", "video_size": len(datos), "chunk_size": len(datos),
                            "total_chunk_count": 1},
        }
        with httpx.Client(timeout=120, transport=self.transporte) as http:
            r = http.post(f"{self.BASE}/video/init/", headers=cabeceras, json=cuerpo)
            respuesta = r.json() if r.content else {}
            if r.status_code != 200 or respuesta.get("error", {}).get("code", "ok") != "ok":
                raise ErrorProveedor(f"TikTok respondió {r.status_code}: {r.text[:300]}")
            publish_id = respuesta["data"]["publish_id"]
            subida = http.put(respuesta["data"]["upload_url"], content=datos, headers={
                "Content-Type": "video/mp4", "Content-Range": f"bytes 0-{len(datos) - 1}/{len(datos)}"})
            if subida.status_code not in (200, 201):
                raise ErrorProveedor(f"TikTok rechazó la subida del video ({subida.status_code}).")
            estado = "PROCESSING_UPLOAD"
            for _ in range(24):
                r = http.post(f"{self.BASE}/status/fetch/", headers=cabeceras, json={"publish_id": publish_id})
                estado = r.json().get("data", {}).get("status", estado)
                if estado in {"PUBLISH_COMPLETE", "FAILED"}:
                    break
                time.sleep(self.espera_s)
        if estado == "FAILED":
            raise ErrorProveedor("TikTok no pudo publicar el video.")
        return Publicacion(red_social=RedSocial.TIKTOK, modo="REAL", estado="PUBLICADO", id_externo=publish_id,
                           detalle=f"Video enviado a TikTok (estado {estado}, privacidad {self.privacidad}).")


def crear_publicador(config: Config, red: RedSocial) -> Publicador:
    if config.modo_publicacion != "real":
        return PublicadorSimulado()
    if red == RedSocial.INSTAGRAM:
        return PublicadorInstagram(config.ig_user_id, config.ig_access_token, config.ig_graph_version,
                                   config.ig_graph_host)
    return PublicadorTikTok(config.tiktok_access_token, config.tiktok_privacidad)
