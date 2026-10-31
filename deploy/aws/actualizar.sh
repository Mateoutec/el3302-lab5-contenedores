#!/usr/bin/env bash
# Vuelve a descargar las imágenes publicadas y reinicia los contenedores.
source "$(dirname "$0")/comun.sh"
ID=$(id_instancia); [ "$ID" != "None" ] || { echo "No hay instancia $NOMBRE"; exit 1; }
IP=$(ip_publica "$ID")
scp "${ssh_opciones[@]}" "$DIR_DEPLOY/docker-compose.nube.yml" "ec2-user@$IP:/opt/el3302/docker-compose.yml"
ssh "${ssh_opciones[@]}" "ec2-user@$IP" \
  "cd /opt/el3302 && sudo docker compose pull -q && sudo docker compose up -d && sudo docker image prune -f && sudo docker compose ps"
