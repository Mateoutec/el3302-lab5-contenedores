"""Video vertical 9:16 (Reel / TikTok) armado con FFmpeg a partir de las 3 fotos."""
from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

from app.dominio.entidades import Brief, Guion
from app.proveedores import graficos as g
from app.proveedores.guiones import ErrorProveedor

log = logging.getLogger(__name__)

ANCHO, ALTO, FPS = 1080, 1920, 30
SEGUNDOS_ESCENA = 4.0
SEGUNDOS_CIERRE = 3.0
TRANSICION = 0.5
PORTADA = "video_portada.jpg"


def cuadro_vertical(pieza: Image.Image) -> Image.Image:
    """Ubica la pieza 4:5 sobre un fondo desenfocado de 1080x1920."""
    lienzo = g.fondo_desenfocado(pieza, ANCHO, ALTO, 0.35)
    ajustada = g.contener(pieza, ANCHO, ALTO)
    lienzo.paste(ajustada, ((ANCHO - ajustada.width) // 2, (ALTO - ajustada.height) // 2))
    return lienzo


def cuadro_cierre(brief: Brief, guion: Guion, acento) -> Image.Image:
    lienzo = Image.new("RGB", (ANCHO, ALTO), acento)
    dibujo = ImageDraw.Draw(lienzo)
    tinta = g.contraste(acento)
    letra, lineas = g.texto_ajustado(brief.empresa.upper(), ANCHO - 160, 2, 120)
    y = g.dibujar_lineas(dibujo, lineas, letra, 0, 640, tinta, centrado_en=ANCHO // 2)
    letra, lineas = g.texto_ajustado(guion.llamado_accion, ANCHO - 200, 4, 60, negrita=False)
    y = g.dibujar_lineas(dibujo, lineas, letra, 0, y + 60, tinta, centrado_en=ANCHO // 2)
    etiquetas = " ".join(guion.hashtags[:4])
    letra, lineas = g.texto_ajustado(etiquetas, ANCHO - 200, 2, 40, negrita=False)
    g.dibujar_lineas(dibujo, lineas, letra, 0, y + 70, tinta, centrado_en=ANCHO // 2)
    return lienzo


class GeneradorVideo:
    nombre = "ffmpeg"

    def __init__(self, ffmpeg: str | None = None):
        self.ffmpeg = ffmpeg or shutil.which("ffmpeg")

    def generar(self, piezas: list[Image.Image], brief: Brief, guion: Guion, acento, carpeta: Path,
                nombre: str = "video.mp4") -> Path:
        if not self.ffmpeg:
            raise ErrorProveedor("FFmpeg no está instalado en el contenedor.")
        cuadros = [cuadro_vertical(p) for p in piezas] + [cuadro_cierre(brief, guion, acento)]
        # Portada del video (atributo poster del reproductor).
        cuadros[0].resize((ANCHO // 2, ALTO // 2)).save(carpeta / PORTADA, quality=85)
        rutas = []
        for i, cuadro in enumerate(cuadros):
            ruta = carpeta / f"_cuadro_{i}.jpg"
            cuadro.save(ruta, quality=92)
            rutas.append(ruta)

        duraciones = [SEGUNDOS_ESCENA] * len(piezas) + [SEGUNDOS_CIERRE]
        entradas: list[str] = []
        filtros: list[str] = []
        for i, (ruta, segundos) in enumerate(zip(rutas, duraciones)):
            entradas += ["-i", str(ruta)]
            cuadros_seg = int(segundos * FPS)
            # Zoom lento (efecto Ken Burns) sobre cada imagen fija.
            filtros.append(
                f"[{i}:v]scale={ANCHO * 2}:{ALTO * 2},"
                f"zoompan=z='min(zoom+0.0007,1.08)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"d={cuadros_seg}:s={ANCHO}x{ALTO}:fps={FPS},setsar=1,format=yuv420p[v{i}]"
            )
        actual, desfase = "v0", 0.0
        for i in range(1, len(rutas)):
            desfase += duraciones[i - 1] - TRANSICION
            salida = f"x{i}"
            filtros.append(f"[{actual}][v{i}]xfade=transition=fade:duration={TRANSICION}:offset={desfase:.2f}[{salida}]")
            actual = salida
        total = sum(duraciones) - TRANSICION * (len(rutas) - 1)
        destino = carpeta / nombre
        comando = [
            self.ffmpeg, "-y", "-loglevel", "error", *entradas,
            "-f", "lavfi", "-t", f"{total:.2f}", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-filter_complex", ";".join(filtros),
            "-map", f"[{actual}]", "-map", f"{len(rutas)}:a",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-r", str(FPS), "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "96k", "-shortest", "-movflags", "+faststart", str(destino),
        ]
        try:
            subprocess.run(comando, check=True, capture_output=True, text=True, timeout=300)
        except subprocess.CalledProcessError as error:
            raise ErrorProveedor(f"FFmpeg falló: {error.stderr.strip()[-400:]}") from None
        except subprocess.TimeoutExpired:
            raise ErrorProveedor("FFmpeg tardó demasiado en generar el video.") from None
        finally:
            for ruta in rutas:
                ruta.unlink(missing_ok=True)
        log.info("Video generado: %s (%.1f s)", destino, total)
        return destino
