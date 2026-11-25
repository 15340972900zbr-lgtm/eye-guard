#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

makensis_command=${MAKENSIS:-makensis}
build_dir=work/payload
mkdir -p work/downloads "$build_dir"/{app/eye_guard,assets,runtime} dist

python_zip=work/downloads/cpython.zip
if [[ ! -f "$python_zip" ]]; then
    curl -fL --retry 2 https://www.python.org/ftp/python/3.13.17/python-3.13.17-embed-amd64.zip -o "$python_zip"
fi
printf '%s  %s\n' 9e35319bffedab8b36ad44d8f377cb4f1733bcec257a0b6d04d94f01486ddb38 "$python_zip" | sha256sum -c
unzip -oq "$python_zip" -d "$build_dir/runtime"

model_file="$build_dir/assets/face_landmarker.task"
if [[ ! -f "$model_file" ]]; then
    curl -fL --retry 2 https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task -o "$model_file"
fi
printf '%s  %s\n' 64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff "$model_file" | sha256sum -c

uv pip install --target "$build_dir/runtime/Lib/site-packages" \
    --python-version 3.13 --python-platform x86_64-pc-windows-msvc --only-binary :all: \
    -r requirements-windows.txt
printf '%s\r\n' 'python313.zip' '.' 'Lib\site-packages' '..\app' 'import site' > "$build_dir/runtime/python313._pth"

cp source/start.pyw "$build_dir/app/"
cp source/eye_guard/*.py "$build_dir/app/eye_guard/"
cp source/config.example.toml source/eye.ico requirements-windows.txt "$build_dir/assets/"
cp README.txt THIRD-PARTY.txt "$build_dir/"
find "$build_dir" -type d -name '__pycache__' -prune -exec rm -rf '{}' +
"$makensis_command" -V3 installer.nsi
