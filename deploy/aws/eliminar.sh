#!/usr/bin/env bash
# Borra todo lo creado en AWS (instancia, grupo de seguridad y par de llaves) para no generar costos.
source "$(dirname "$0")/comun.sh"
read -r -p "Se eliminará la instancia '$NOMBRE' y sus datos en $AWS_DEFAULT_REGION. ¿Continuar? (s/N) " ok
[ "$ok" = "s" ] || exit 0
ID=$(id_instancia)
if [ "$ID" != "None" ]; then
  aws ec2 terminate-instances --instance-ids "$ID" >/dev/null
  aws ec2 wait instance-terminated --instance-ids "$ID"
fi
SG=$(aws ec2 describe-security-groups --filters "Name=group-name,Values=$NOMBRE" --query 'SecurityGroups[0].GroupId' --output text)
[ "$SG" = "None" ] || aws ec2 delete-security-group --group-id "$SG"
aws ec2 delete-key-pair --key-name "$NOMBRE" >/dev/null 2>&1 || true
rm -f "$LLAVE"
echo "Recursos eliminados."
