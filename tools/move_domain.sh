#!/usr/bin/env bash
# Переезд стенда на новый домен: сертификат Let's Encrypt, nginx, адрес в коде, перезапуск Trac и сервиса.
# Старый домен остаётся и отвечает 301 на тот же путь нового — ссылки в Telegram и документах не ломаются.
#   tools/move_domain.sh ltz2026.ru            # проверка DNS и переезд
# Ничего не меняет, пока A-запись нового домена не указывает на этот сервер.
set -euo pipefail
NEW=${1:?новый домен}
OLD=${OLD_DOMAIN:-ltz2026.juri-konoplev.pro}
REPO=$(cd "$(dirname "$0")/.." && pwd)
IP=$(curl -fsS -4 ifconfig.me)
EMAIL=${CERT_EMAIL:-juri.konoplev@gmail.com}

names=("$NEW")
[ "$(dig +short A "www.$NEW" | tail -1)" = "$IP" ] && names+=("www.$NEW")
got=$(dig +short A "$NEW" @8.8.8.8 | tail -1)
[ "$got" = "$IP" ] || { echo "[domain] $NEW -> '${got:-нет записи}', а сервер $IP: нужна A-запись $NEW -> $IP"; exit 1; }
echo "[domain] DNS ок: ${names[*]} -> $IP"

AV=/etc/nginx/sites-available; EN=/etc/nginx/sites-enabled
# 1) HTTP-блок нового домена для проверки Let's Encrypt
if [ ! -e "/etc/letsencrypt/live/$NEW/fullchain.pem" ]; then
  sudo tee "$AV/$NEW" >/dev/null <<NGX
server {
    listen 80; listen [::]:80;
    server_name ${names[*]};
    location /.well-known/acme-challenge/ { root /var/www/html; }
    location / { return 301 https://$NEW\$request_uri; }
}
NGX
  sudo ln -sf "$AV/$NEW" "$EN/$NEW"
  sudo nginx -t && sudo systemctl reload nginx
  args=(); for n in "${names[@]}"; do args+=(-d "$n"); done
  sudo certbot certonly --webroot -w /var/www/html "${args[@]}" --non-interactive --agree-tos -m "$EMAIL" \
       --deploy-hook "systemctl reload nginx"
fi

# 2) полный конфиг нового домена из старого; старый — только редирект
sudo cp "$AV/$OLD" "/root/nginx-$OLD.bak-$(date +%Y%m%d%H%M)" 2>/dev/null || true
sudo sed -e "s/server_name $OLD;/server_name ${names[*]};/" -e "s#/live/$OLD/#/live/$NEW/#" \
         -e "s#/var/log/nginx/$OLD#/var/log/nginx/$NEW#" -e "s/shared:LTZSSL/shared:LTZSSL2/" \
         -e "s#^\# $OLD#\# $NEW#" -e "s#301 https://\$host\$request_uri#301 https://$NEW\$request_uri#" \
         "$AV/$OLD" | sudo tee "$AV/$NEW" >/dev/null
sudo tee "$AV/$OLD" >/dev/null <<NGX
# $OLD — старый адрес стенда, переехал на $NEW
server {
    listen 80; listen [::]:80;
    server_name $OLD;
    location /.well-known/acme-challenge/ { root /var/www/html; }
    location / { return 301 https://$NEW\$request_uri; }
}
server {
    listen 443 ssl http2; listen [::]:443 ssl http2;
    server_name $OLD;
    ssl_certificate     /etc/letsencrypt/live/$OLD/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$OLD/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    location / { return 301 https://$NEW\$request_uri; }
}
NGX
sudo nginx -t && sudo systemctl reload nginx
echo "[domain] nginx: https://$NEW, $OLD -> 301"

# 3) адрес в коде и конфигурации, перезапуск
cd "$REPO"
grep -rl "$OLD" --exclude-dir=.git --exclude-dir=.venv --exclude-dir=data --exclude-dir=docs --exclude-dir=films \
     --exclude-dir=models --exclude=move_domain.sh . | xargs -r sed -i "s/$OLD/$NEW/g"
(cd infra/trac && docker compose up -d)
infra/app/deploy.sh
curl -fsS -o /dev/null -w "[domain] https://$NEW/ -> %{http_code}\n" "https://$NEW/"
curl -sS -o /dev/null -w "[domain] https://$OLD/tz/ -> %{http_code} %{redirect_url}\n" "https://$OLD/tz/"
