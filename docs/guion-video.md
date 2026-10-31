# Guion del video (5 minutos como máximo)

Grabar la pantalla con OBS, la Xbox Game Bar (Win + G) o QuickTime. Conviene tener abiertas de antemano las pestañas del navegador y una terminal.

| Tiempo | Qué mostrar | Qué decir (resumen) |
|---|---|---|
| 0:00 – 0:20 | README del repositorio en GitHub | «Laboratorio 5 de contenedores: dos aplicaciones dockerizadas y desplegadas en AWS.» |
| 0:20 – 1:00 | Diagrama de 3 capas (`docs/img/arquitectura-p1.png`) y las carpetas `presentacion/`, `negocio/`, `datos/` | Qué hace cada capa y que la API simulada imita el contrato de football-data.org. |
| 1:00 – 1:30 | `Dockerfile` y `docker-compose.yml` de P1 | Imagen slim, usuario sin privilegios, healthcheck, variables de entorno, volumen `pgdata`, `depends_on: service_healthy`. |
| 1:30 – 2:30 | P1 en la nube (`http://<ip>:8000`) | Listar partidos → filtrar la jornada → abrir un partido → registrar una predicción → ver «Predicciones». Abrir `/docs`. |
| 2:30 – 2:50 | Terminal: `docker compose ps` en la EC2 y consola de EC2 | Los 5 contenedores *healthy* en el servidor. |
| 2:50 – 4:20 | P2 en la nube (`http://<ip>:8080`) | Subir la foto → aparecen los 3 guiones → elegir uno → 3 fotos + video → Publicar → vista previa. |
| 4:20 – 4:45 | GitHub Actions y Packages | Pruebas y publicación automática de las imágenes en GHCR. |
| 4:45 – 5:00 | Cierre | Persistencia con volúmenes y cómo se despliega con un solo script. |

Consejo: crea la campaña de P2 una vez antes de grabar, para comprobar que todo responde rápido.
