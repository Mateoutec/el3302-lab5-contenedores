# Variables y funciones compartidas por los scripts de AWS (se carga con "source").
set -euo pipefail

DIR_AWS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIR_DEPLOY="$(cd "$DIR_AWS/.." && pwd)"
NOMBRE="${NOMBRE:-el3302-lab5}"
TIPO_INSTANCIA="${TIPO_INSTANCIA:-t3.small}"
export AWS_DEFAULT_REGION="${AWS_REGION:-$(aws configure get region 2>/dev/null || true)}"
AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}"
export AWS_PAGER=""
# Git Bash (Windows) convierte argumentos como /aws/service/... o DeviceName=/dev/xvda en rutas de Windows
export MSYS_NO_PATHCONV=1
ESTADO="$DIR_AWS/.estado"
LLAVE="$ESTADO/$NOMBRE.pem"
mkdir -p "$ESTADO"

# En Windows (Git Bash) la CLI de AWS necesita rutas tipo C:/...
ruta_nativa() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else echo "$1"; fi; }

proteger_llave() {
  chmod 600 "$LLAVE" 2>/dev/null || true
  if command -v icacls >/dev/null 2>&1; then
    icacls "$(ruta_nativa "$LLAVE")" /inheritance:r /grant:r "${USERNAME:-$USER}:R" >/dev/null
  fi
}

id_instancia() {
  aws ec2 describe-instances \
    --filters "Name=tag:Name,Values=$NOMBRE" "Name=instance-state-name,Values=pending,running,stopping,stopped" \
    --query 'Reservations[0].Instances[0].InstanceId' --output text
}

ip_publica() {
  aws ec2 describe-instances --instance-ids "$1" \
    --query 'Reservations[0].Instances[0].PublicIpAddress' --output text
}

ssh_opciones=(-i "$LLAVE" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 -o ServerAliveInterval=30)
