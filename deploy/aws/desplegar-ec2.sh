#!/usr/bin/env bash
# Crea (o reutiliza) una instancia EC2 con Docker y levanta las dos aplicaciones.
#
# Requisitos: AWS CLI v2 con credenciales válidas (aws configure / aws sso login),
#             ssh/scp, y deploy/nube.env completo (copiar de nube.env.example).
# Uso:        bash deploy/aws/desplegar-ec2.sh
# Variables:  AWS_REGION (us-east-1), TIPO_INSTANCIA (t3.small), NOMBRE (el3302-lab5)
source "$(dirname "$0")/comun.sh"

ENV_NUBE="$DIR_DEPLOY/nube.env"
[ -f "$ENV_NUBE" ] || { echo "Falta $ENV_NUBE (copia nube.env.example y complétalo)"; exit 1; }

echo "==> Cuenta AWS: $(aws sts get-caller-identity --query Arn --output text) | región $AWS_DEFAULT_REGION"

echo "==> Par de llaves SSH"
if ! aws ec2 describe-key-pairs --key-names "$NOMBRE" >/dev/null 2>&1; then
  aws ec2 create-key-pair --key-name "$NOMBRE" --query KeyMaterial --output text > "$LLAVE"
  proteger_llave
elif [ ! -f "$LLAVE" ]; then
  echo "El par de llaves '$NOMBRE' existe en AWS pero no está $LLAVE. Bórralo con eliminar.sh o usa otro NOMBRE."
  exit 1
fi

echo "==> Grupo de seguridad (22 solo desde tu IP; 8000 y 8080 públicos)"
VPC=$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text)
SG=$(aws ec2 describe-security-groups --filters "Name=group-name,Values=$NOMBRE" "Name=vpc-id,Values=$VPC" \
     --query 'SecurityGroups[0].GroupId' --output text)
if [ "$SG" = "None" ]; then
  SG=$(aws ec2 create-security-group --group-name "$NOMBRE" --description "Lab 5 EL3302" --vpc-id "$VPC" \
       --query GroupId --output text)
  MI_IP="$(curl -fsS https://checkip.amazonaws.com | tr -d '[:space:]')/32"
  aws ec2 authorize-security-group-ingress --group-id "$SG" --ip-permissions \
    "IpProtocol=tcp,FromPort=22,ToPort=22,IpRanges=[{CidrIp=$MI_IP,Description=SSH}]" \
    "IpProtocol=tcp,FromPort=8000,ToPort=8000,IpRanges=[{CidrIp=0.0.0.0/0,Description=P1-champions}]" \
    "IpProtocol=tcp,FromPort=8080,ToPort=8080,IpRanges=[{CidrIp=0.0.0.0/0,Description=P2-marketing}]" >/dev/null
fi

echo "==> Instancia EC2 ($TIPO_INSTANCIA, Amazon Linux 2023)"
ID=$(id_instancia)
if [ "$ID" = "None" ]; then
  AMI=$(aws ssm get-parameter --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 \
        --query Parameter.Value --output text)
  ID=$(aws ec2 run-instances --image-id "$AMI" --instance-type "$TIPO_INSTANCIA" --key-name "$NOMBRE" \
       --security-group-ids "$SG" --user-data "file://$(ruta_nativa "$DIR_AWS/user-data.sh")" \
       --block-device-mappings 'DeviceName=/dev/xvda,Ebs={VolumeSize=20,VolumeType=gp3}' \
       --metadata-options HttpTokens=required \
       --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$NOMBRE},{Key=Proyecto,Value=EL3302-Lab5}]" \
       --query 'Instances[0].InstanceId' --output text)
fi
aws ec2 start-instances --instance-ids "$ID" >/dev/null 2>&1 || true
aws ec2 wait instance-running --instance-ids "$ID"
IP=$(ip_publica "$ID")
echo "    $ID -> $IP"

echo "==> Esperando a que Docker quede instalado (user-data)..."
for _ in $(seq 1 60); do
  if ssh "${ssh_opciones[@]}" "ec2-user@$IP" test -f /opt/el3302/.docker-listo 2>/dev/null; then break; fi
  sleep 10
done

echo "==> Subiendo docker-compose.yml y .env"
ENV_TMP="$ESTADO/.env.subir"
grep -v '^[[:space:]]*#' "$ENV_NUBE" | grep -v '^[[:space:]]*$' | grep -v '^URL_PUBLICA=$' > "$ENV_TMP" || true
grep -q '^URL_PUBLICA=' "$ENV_TMP" || echo "URL_PUBLICA=http://$IP:8080" >> "$ENV_TMP"
scp "${ssh_opciones[@]}" "$DIR_DEPLOY/docker-compose.nube.yml" "ec2-user@$IP:/opt/el3302/docker-compose.yml"
scp "${ssh_opciones[@]}" "$ENV_TMP" "ec2-user@$IP:/opt/el3302/.env"
rm -f "$ENV_TMP"

echo "==> docker compose pull && up -d"
ssh "${ssh_opciones[@]}" "ec2-user@$IP" \
  "cd /opt/el3302 && chmod 600 .env && sudo docker compose pull -q && sudo docker compose up -d && sudo docker compose ps"

echo
echo "Listo:"
echo "  P1 Champions:  http://$IP:8000      (API: http://$IP:8000/docs)"
echo "  P2 Marketing:  http://$IP:8080"
echo "  SSH:           ssh -i $LLAVE ec2-user@$IP"
