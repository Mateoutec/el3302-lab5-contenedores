"""Configuración leída de variables de entorno (ver .env.example)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    database_url: str
    media_dir: Path
    url_publica: str
    # Guiones: "auto" usa Claude si hay ANTHROPIC_API_KEY y, si no, plantillas locales.
    proveedor_guiones: str
    modelo_claude: str
    # Fotos: "local" (Pillow, sin costo) u "openai" (gpt-image-1, requiere OPENAI_API_KEY).
    proveedor_imagenes: str
    modelo_imagen_openai: str
    # Publicación: "simulado" o "real" (usa las credenciales de Instagram/TikTok).
    modo_publicacion: str
    ig_user_id: str
    ig_access_token: str
    ig_graph_version: str
    ig_graph_host: str
    tiktok_access_token: str
    tiktok_privacidad: str
    max_mb_foto: int


def cargar_config() -> Config:
    return Config(
        database_url=os.getenv("DATABASE_URL", "sqlite:///./marketing.db"),
        media_dir=Path(os.getenv("MEDIA_DIR", "./media")).resolve(),
        url_publica=os.getenv("URL_PUBLICA", "http://localhost:8080").rstrip("/"),
        proveedor_guiones=os.getenv("PROVEEDOR_GUIONES", "auto").lower(),
        modelo_claude=os.getenv("MODELO_CLAUDE", "claude-opus-5-5"),
        proveedor_imagenes=os.getenv("PROVEEDOR_IMAGENES", "local").lower(),
        modelo_imagen_openai=os.getenv("MODELO_IMAGEN_OPENAI", "gpt-image-1"),
        modo_publicacion=os.getenv("MODO_PUBLICACION", "simulado").lower(),
        ig_user_id=os.getenv("IG_USER_ID", ""),
        ig_access_token=os.getenv("IG_ACCESS_TOKEN", ""),
        ig_graph_version=os.getenv("IG_GRAPH_VERSION", "v23.0"),
        # graph.facebook.com (login con Facebook) o graph.instagram.com (login con Instagram)
        ig_graph_host=os.getenv("IG_GRAPH_HOST", "https://graph.facebook.com"),
        tiktok_access_token=os.getenv("TIKTOK_ACCESS_TOKEN", ""),
        tiktok_privacidad=os.getenv("TIKTOK_PRIVACIDAD", "SELF_ONLY"),
        max_mb_foto=int(os.getenv("MAX_MB_FOTO", "10")),
    )
