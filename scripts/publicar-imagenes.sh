#!/usr/bin/env bash
# Construye y publica las 3 imágenes desde tu PC (alternativa a GitHub Actions).
#
#   Docker Hub:  docker login                       && bash scripts/publicar-imagenes.sh tu-usuario
#   GHCR:        docker login ghcr.io -u tu-usuario && bash scripts/publicar-imagenes.sh ghcr.io/tu-usuario
#
# Opcional: segundo argumento con la etiqueta (por defecto "latest").
set -euo pipefail

PREFIJO="${1:?Uso: bash scripts/publicar-imagenes.sh <prefijo: usuario-dockerhub | ghcr.io/usuario> [tag]}"
TAG="${2:-latest}"
RAIZ="$(cd "$(dirname "$0")/.." && pwd)"

publicar() {
  local nombre="$1" contexto="$2"
  local imagen="${PREFIJO}/${nombre}:${TAG}"
  echo "==> ${imagen}"
  docker build --platform linux/amd64 -t "${imagen}" "${RAIZ}/${contexto}"
  docker push "${imagen}"
}

publicar p1-champions p1-champions
publicar p1-mock-api  p1-champions/mock_api
publicar p2-marketing p2-marketing

echo
echo "Listo. En el servidor usa IMAGE_PREFIX=${PREFIJO} y TAG=${TAG}."
