import os
import sys
import subprocess
import signal
import time
from pathlib import Path

#Configuracion inicial

CSV_PATH = os.getenv("OUTPUT_CSV", "./data/words.csv")

# Crea la carpeta data/ si no existe
Path(CSV_PATH).parent.mkdir(parents=True, exist_ok=True)

# Validaciones

if not os.getenv("GITHUB_TOKEN"):
    print("GITHUB TOKEN no configurado, el miner correrá con límite de 60 req/hora")
    print("                    $env:GITHUB_TOKEN='tu_token'  (PowerShell)")
    print()

try:
    import streamlit
except ImportError:
    print("ERROR: streamlit no está instalado.")
    sys.exit(1)

try:
    import requests
except ImportError:
    print("ERROR: requests no está instalado.")
    sys.exit(1)

# Arranque 

env = os.environ.copy()
env["OUTPUT_CSV"] = CSV_PATH
env["INPUT_CSV"]  = CSV_PATH

print("Word Miner iniciando")
print(f"CSV referencia: {CSV_PATH}")
print("Visualizer disponible en: http://localhost:8501")
print("Presiona Ctrl+C para detener el proceso\n")

miner_proc = subprocess.Popen(
    [sys.executable, "miner/miner.py"],
    env=env,
)

#  pausa para que el miner cree el csv antes de que arranque el visualizer
time.sleep(2)

visualizer_proc = subprocess.Popen(
    [
        sys.executable, "-m", "streamlit", "run", "visualizer/visualizer.py",
        "--server.address=localhost",
        "--server.port=8501",
        "--server.headless=true",
    ],
    env=env,
)

# Manejo de señales para detener ambos procesos

def stop(sig, frame):
    print("\nDeteniendo miner y visualizer...")
    miner_proc.terminate()
    visualizer_proc.terminate()
    miner_proc.wait()
    visualizer_proc.wait()
    print("Todo detenido.")
    sys.exit(0)

signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT,  stop)

while True:
    if miner_proc.poll() is not None:
        print(f"El miner se detuvo (código {miner_proc.returncode}). Reiniciando...")
        miner_proc = subprocess.Popen(
            [sys.executable, "miner/miner.py"],
            env=env,
        )

    if visualizer_proc.poll() is not None:
        print(f"El visualizer se detuvo (código {visualizer_proc.returncode}). Reiniciando...")
        visualizer_proc = subprocess.Popen(
            [
                sys.executable, "-m", "streamlit", "run", "visualizer/visualizer.py",
                "--server.address=localhost",
                "--server.port=8501",
                "--server.headless=true",
            ],
            env=env,
        )

    time.sleep(5)
