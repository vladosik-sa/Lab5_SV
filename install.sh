#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/vladosik-sa/Lab5_SV.git"
TARGET_DIR="Lab5_SV"

echo "[INFO] Lab5 installer started"

if command -v apt-get >/dev/null 2>&1; then
    echo "[INFO] Installing system prerequisites (git, python3, venv, pip)..."
    sudo apt-get update -y
    sudo apt-get install -y git python3 python3-venv python3-pip ca-certificates
else
    echo "[ERROR] This installer currently supports Debian/Kali/Ubuntu (apt-get)."
    echo "Please install manually: git, python3, python3-venv, python3-pip"
    exit 3
fi

WORKDIR=""

if [[ -f "./lab5.py" && -f "./requirements.txt" ]]; then
    WORKDIR="."
    echo "[INFO] Detected lab5.py in current directory -> using current folder"
else
    if [[ -d "$TARGET_DIR/.git" ]]; then
        echo "[INFO] Repo folder '$TARGET_DIR' already exists -> pulling latest changes"
        git -C "$TARGET_DIR" pull
    else
        echo "[INFO] Cloning repo into ./$TARGET_DIR ..."
        rm -rf "$TARGET_DIR"
        git clone "$REPO_URL" "$TARGET_DIR"
    fi
    WORKDIR="$TARGET_DIR"
fi

cd "$WORKDIR"

if [[ ! -f "requirements.txt" ]]; then
    echo "[ERROR] requirements.txt not found in: $(pwd)"
    exit 4
fi

if [[ ! -f "lab5.py" ]]; then
    echo "[ERROR] lab5.py not found in: $(pwd)"
    exit 4
fi

echo "[INFO] Creating virtual environment: .venv"
python3 -m venv .venv

source .venv/bin/activate

echo "[INFO] Upgrading pip..."
python -m pip install --upgrade pip

echo "[INFO] Installing Python dependencies from requirements.txt..."
pip install -r requirements.txt

chmod +x lab5.py || true
chmod +x install.sh || true

echo
echo "[OK] Installation complete."
echo "Next steps:"
echo " cd $(pwd)"
echo " source .venv/bin/activate"
echo " python3 lab5.py --help"
