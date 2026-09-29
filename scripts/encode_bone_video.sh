#!/usr/bin/env bash
# Сборка видео «регенерации» кости из кадров scripts/render_bone_video.js → dxaqc/web/static/bone/regen.{mp4,webm}.
# Кадры белые, без прозрачности: карточка на главной белая. mp4 (H.264) — везде; webm (VP9) — меньше, если браузер умеет.
#   scripts/encode_bone_video.sh /tmp/bone_frames
set -euo pipefail
FR=${1:-/tmp/bone_frames}
OUT=$(cd "$(dirname "$0")/.." && pwd)/dxaqc/web/static/bone
nice -n 10 ffmpeg -y -loglevel error -framerate 24 -i "$FR/f%04d.png" -c:v libx264 -preset slow -crf 27 -pix_fmt yuv420p -movflags +faststart -an -threads 2 "$OUT/regen.mp4"
nice -n 10 ffmpeg -y -loglevel error -framerate 24 -i "$FR/f%04d.png" -c:v libvpx-vp9 -crf 38 -b:v 0 -pix_fmt yuv420p -row-mt 1 -an -threads 2 "$OUT/regen.webm"
ls -la "$OUT"/regen.* | awk '{printf "%s  %.2f МБ\n", $9, $5/1048576}'
