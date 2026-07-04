#!/usr/bin/env bash
# Membangun Drone System menjadi satu executable menggunakan PyInstaller.

echo -e "\e[36mMempersiapkan proses build mdi_drone di Linux...\e[0m"

# Pindah ke folder script
cd "$(dirname "$0")"

# Bersihkan sisa build sebelumnya
rm -rf ./build ./dist ./mdi_drone.spec

# Pastikan venv aktif jika ada .venv
if [ -d "./.venv" ]; then
    echo "Mengaktifkan virtual environment (.venv)..."
    source ./.venv/bin/activate
elif [ -d "../.venv" ]; then
    echo "Mengaktifkan virtual environment (../.venv)..."
    source ../.venv/bin/activate
fi

# Cek Installasi PyInstaller
if ! command -v pyinstaller &> /dev/null; then
    echo -e "\e[33mPyInstaller tidak ditemukan. Menginstal via pip...\e[0m"
    pip install pyinstaller
fi

echo -e "\e[33mSedang mengemas mdi_drone...\e[0m"

pyinstaller --noconfirm \
    --onefile \
    --name "mdi_drone" \
    --clean \
    --hidden-import="uvicorn" \
    --hidden-import="uvicorn.logging" \
    --hidden-import="uvicorn.loops" \
    --hidden-import="uvicorn.loops.auto" \
    --hidden-import="uvicorn.protocols" \
    --hidden-import="uvicorn.protocols.http" \
    --hidden-import="uvicorn.protocols.http.auto" \
    --hidden-import="uvicorn.protocols.websockets" \
    --hidden-import="uvicorn.protocols.websockets.auto" \
    --hidden-import="uvicorn.lifespan" \
    --hidden-import="uvicorn.lifespan.on" \
    --hidden-import="fastapi" \
    --hidden-import="pydantic" \
    --hidden-import="starlette" \
    --hidden-import="anyio" \
    --hidden-import="h11" \
    --hidden-import="serial" \
    --hidden-import="drone_system.tdoa.builtin_filters.passthrough" \
    --hidden-import="drone_system.tdoa.builtin_filters.spectral_gating" \
    --hidden-import="drone_system.tdoa.builtin_filters.wavelet_denoising" \
    --hidden-import="drone_system.tdoa.builtin_filters.wiener_stft" \
    run_drone_system.py

if [ $? -eq 0 ]; then
    echo -e "\e[32mBuild Berhasil! Aplikasi mdi_drone dapat ditemukan di folder 'dist'.\e[0m"
    
    # Buat direktori eksternal
    mkdir -p ./dist/config
    mkdir -p ./dist/custom_filters
    mkdir -p ./dist/drone_recordings
    
    # Salin default config
    if [ -f "./drone_system/config/drone_config_override.json" ]; then
        cp ./drone_system/config/drone_config_override.json ./dist/config/
        echo "Default config disalin ke dist/config/."
    fi
else
    echo -e "\e[31mBuild gagal. Periksa log error di atas.\e[0m"
fi
