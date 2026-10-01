#!/bin/zsh
# Prepara Studio Local en este Mac: entorno de Python, FFmpeg y la app. Se puede repetir sin riesgo.
set -euo pipefail
cd -- "${0:A:h}/editor"
if ! xcode-select -p >/dev/null 2>&1; then
  echo 'Faltan las herramientas de línea de comandos de Apple. Ejecuta «xcode-select --install», acepta la instalación y vuelve a lanzar este script.'
  exit 1
fi
[[ -x .venv/bin/python3 ]] || /usr/bin/python3 -m venv .venv
.venv/bin/python3 -m pip install --quiet --upgrade pip
.venv/bin/python3 -m pip install --quiet -r requirements.txt
mkdir -p runtime projects
ln -sf "$(.venv/bin/python3 -c 'import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())')" runtime/ffmpeg
runtime/ffmpeg -hide_banner -version | head -1
./build.command
echo 'Studio Local está listo. Ábrelo con: ./editor/studio.command'
