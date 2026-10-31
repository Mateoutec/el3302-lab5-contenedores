# Laboratorio 5: Contenedores (EL3302, Introducción a Cognitive Computing)

**Autor:** Mateo Llallire Meza

Este repositorio tiene dos aplicaciones. Cada una va en contenedores Docker con su propia base de datos PostgreSQL y está lista para desplegarse en AWS.

| | Aplicación | Puerto | Contenedores |
|---|---|---|---|
| **Pregunta 1** | Predicciones de la Champions League, con arquitectura de 3 capas | `8000` | `app`, `mock-api`, `db` |
| **Pregunta 2** | Marketing con IA: foto → 3 guiones → 3 fotos + video → red social | `8080` | `app`, `db` |

**Demo desplegada en AWS (EC2, us-east-1):** [P1: http://34.234.97.246:8000](http://34.234.97.246:8000) · [P1 API: /docs](http://34.234.97.246:8000/docs) · [P2: http://34.234.97.246:8080](http://34.234.97.246:8080). Las capturas del despliegue están en [docs/img/evidencias/nube](docs/img/evidencias/nube).

```
.
├── p1-champions/            Pregunta 1
│   ├── app/
│   │   ├── presentacion/    capa de presentación (HTML Jinja2 + API REST)
│   │   ├── negocio/         capa de lógica de negocio (servicios y reglas)
│   │   ├── datos/           capa de acceso a datos (repositorios SQLAlchemy + cliente de la API)
│   │   └── dominio/         entidades compartidas por las capas
│   ├── mock_api/            API simulada de partidos (contrato de football-data.org v4)
│   ├── tests/               pruebas (pytest)
│   ├── Dockerfile
│   ├── docker-compose.yml   app + mock-api + PostgreSQL
│   └── .env.example
├── p2-marketing/            Pregunta 2
│   ├── app/
│   │   ├── presentacion/    páginas y API mínima
│   │   ├── negocio/         flujo de la campaña
│   │   ├── proveedores/     Claude, Pillow / OpenAI, FFmpeg, Instagram / TikTok
│   │   └── datos/           repositorio y almacén de archivos
│   ├── tests/
│   ├── Dockerfile           incluye FFmpeg y fuentes
│   ├── docker-compose.yml   app + PostgreSQL
│   └── .env.example
├── deploy/
│   ├── docker-compose.nube.yml   las 2 apps en un servidor, con las imágenes publicadas
│   ├── nube.env.example
│   └── aws/                      desplegar-ec2.sh · actualizar.sh · eliminar.sh · user-data.sh
├── scripts/publicar-imagenes.sh  build + push a Docker Hub o GHCR desde tu PC
├── .github/workflows/            CI: pruebas + publicación en GHCR en cada push a main
└── docs/                         arquitectura, flujo de datos, despliegue, guion del video, imágenes
```

## Requisitos

- Docker Desktop (Windows/macOS) o Docker Engine con Compose v2 (Linux).
- Opcional, solo para correr las pruebas fuera de Docker: Python 3.12 y FFmpeg.

## Instalación y ejecución

### Pregunta 1: predicciones de la Champions League

```bash
cd p1-champions
cp .env.example .env          # en Windows (PowerShell): copy .env.example .env
docker compose up -d --build
```

- Aplicación web: http://localhost:8000
- Documentación de la API REST (Swagger): http://localhost:8000/docs
- API simulada de partidos: http://localhost:8081/v4/competitions/CL/matches

Al iniciar, la app consume la API de partidos y guarda los 144 partidos de la fase liga en PostgreSQL. Desde la web se puede:

1. Listar los partidos y filtrarlos por estado o jornada.
2. Abrir un partido programado y registrar una predicción (ganador o empate, más el marcador).
3. Ver todas las predicciones en **Predicciones**, con los puntos y el ranking cuando el partido termina.

**Usar la API pública real.** Crea un token gratuito en https://www.football-data.org/client/register y edita `.env`:

```env
API_PARTIDOS_URL=https://api.football-data.org/v4
API_PARTIDOS_TOKEN=tu-token
```

Luego aplica el cambio con `docker compose up -d`. La API simulada usa el mismo contrato, así que no hay que cambiar código.

### Pregunta 2: marketing con IA para empresas

```bash
cd p2-marketing
cp .env.example .env
docker compose up -d --build
```

Abre http://localhost:8080. Sube la foto de un producto y completa la empresa, el producto, el público, el tono y la red social. Luego:

1. El sistema propone **3 guiones**, de 3 escenas cada uno.
2. Eliges uno.
3. El sistema genera **3 fotos** (una por escena, formato 4:5) y **un video vertical** de 1080×1920 (13,5 s, H.264).
4. Con **Publicar**, el contenido sale en Instagram (carrusel + Reel) o en TikTok (video).

La app funciona sin claves de API. Cada proveedor se cambia con variables de entorno en `.env`:

| Paso | Sin claves (por defecto) | Con claves |
|---|---|---|
| Guiones | plantillas locales + análisis de color de la foto | `ANTHROPIC_API_KEY`: Claude analiza la foto (visión) y responde en JSON estructurado |
| 3 fotos | diseño con Pillow sobre la foto subida | `PROVEEDOR_IMAGENES=openai` + `OPENAI_API_KEY`: fotos nuevas con gpt-image-1 |
| Video | FFmpeg (siempre local) | (igual) |
| Publicación | `MODO_PUBLICACION=simulado`: guarda la publicación y muestra la vista previa | `MODO_PUBLICACION=real` + `IG_USER_ID` / `IG_ACCESS_TOKEN` o `TIKTOK_ACCESS_TOKEN` |

Para publicar de verdad en Instagram, la app tiene que estar desplegada con una `URL_PUBLICA` accesible desde internet, porque Meta descarga las fotos y el video desde esa URL. TikTok recibe el archivo directamente. Las apps de TikTok que aún no pasan la auditoría solo pueden publicar en privado (`SELF_ONLY`).

### Detener, ver logs y persistencia

```bash
docker compose logs -f app     # logs de la aplicación
docker compose down            # detiene y borra los contenedores; los volúmenes (datos) se conservan
docker compose up -d           # al volver a levantar, las predicciones y campañas siguen ahí
docker compose down -v         # además borra los volúmenes (empieza de cero)
```

## Pruebas

```bash
cd p1-champions && pip install -r requirements-dev.txt && pytest -q    # 11 pruebas
cd p2-marketing && pip install -r requirements-dev.txt && pytest -q    # 13 pruebas (requiere FFmpeg)
```

GitHub Actions corre ambas suites en cada push antes de publicar las imágenes.

## Publicar las imágenes

- **GitHub Container Registry (automático):** al hacer push a `main`, el workflow `.github/workflows/publicar-imagenes.yml` publica `ghcr.io/<usuario>/p1-champions`, `p1-mock-api` y `p2-marketing`. Después, en GitHub, ve a *Packages* → cada paquete → *Package settings* → *Change visibility* → **Public**, para que el servidor pueda descargarlas sin iniciar sesión.
- **Docker Hub (manual):** `docker login && bash scripts/publicar-imagenes.sh <usuario-dockerhub>`.

## Despliegue en AWS

```bash
cp deploy/nube.env.example deploy/nube.env   # completa IMAGE_PREFIX y las contraseñas
bash deploy/aws/desplegar-ec2.sh                # crea la EC2, instala Docker y levanta las 2 apps
```

Al terminar, el script muestra `http://<ip>:8000` (P1) y `http://<ip>:8080` (P2). El paso a paso, las capturas que hay que tomar y cómo borrar los recursos están en [docs/despliegue-aws.md](docs/despliegue-aws.md).

## Documentación

- [Arquitectura y flujo de datos](docs/arquitectura.md)
- [Despliegue en AWS](docs/despliegue-aws.md)
- [Guion del video (5 min)](docs/guion-video.md)

La foto de ejemplo usada en las capturas es *A small cup of coffee*, de Julius Schorzman (Wikimedia Commons, CC BY-SA 2.0).
