
import ast
import base64
import csv
import logging
import os
import re
import signal
import time
import threading
from pathlib import Path

import requests

#Logger

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# Extractor

MIN_LEN = 2  # descarta solo letras sueltas


def split_name(name: str) -> list[str]:

    if not name:
        return []
    name = name.strip("_")
    words = []
    for part in name.split("_"):
        if part:
            words.extend(re.findall(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|[0-9]+", part))
    return [w.lower() for w in words if len(w) >= MIN_LEN]


def extract_python(source: str) -> list[str]:

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    words = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("__") and node.name.endswith("__"):
                continue
            words.extend(split_name(node.name))
    return words


JAVA_EXCLUDED = {"main", "toString", "hashCode", "equals", "clone", "finalize"}

_JAVA_STRIP = [
    re.compile(r"/\*.*?\*/", re.DOTALL),  # comentarios de bloque /* ... */
    re.compile(r"//[^\n]*"),              # comentarios de línea //
    re.compile(r'"(?:\\.|[^"\\])*"'),     # strings literales "..."
]
_JAVA_METHOD = re.compile(
    r"(?:(?:public|protected|private|static|final|abstract|synchronized|native|default)\s+)*"
    r"[\w$][\w$.<>\[\],\s?]*?\s+"
    r"(?!(?:if|for|while|switch|catch|return|throw|new|else|try|do|assert|case)\b)"
    r"\b([a-z][a-zA-Z0-9_$]*)\s*\(",
    re.MULTILINE,
)


def extract_java(source: str) -> list[str]:

    for pattern in _JAVA_STRIP:
        source = pattern.sub(" ", source)
    seen, words = set(), []
    for name in _JAVA_METHOD.findall(source):
        if name not in seen and name not in JAVA_EXCLUDED:
            seen.add(name)
            words.extend(split_name(name))
    return words


# Github

BASE_URL       = "https://api.github.com"
MAX_FILES_REPO = 30 


def _github_get(session: requests.Session, url: str, params: dict = None):
    for attempt in range(3):
        try:
            resp = session.get(url, params=params, timeout=15)
        except requests.RequestException as e:
            log.warning(f"Error de red (intento {attempt+1}/3): {e}")
            time.sleep(5 * (attempt + 1))
            continue

        if resp.status_code == 403 and "rate limit" in resp.text.lower():
            reset_ts = int(resp.headers.get("X-RateLimit-Reset", time.time() + 60))
            wait = max(reset_ts - int(time.time()), 1) + 5
            log.warning(f"Rate limit alcanzado. Esperando {wait}s...")
            time.sleep(wait)
            continue

        if resp.status_code == 404:
            return None

        if resp.status_code != 200:
            log.warning(f"HTTP {resp.status_code} en {url}")
            time.sleep(2)
            continue

        remaining = int(resp.headers.get("X-RateLimit-Remaining", 999))
        if remaining < 100:
            log.warning(f"Rate limit bajo: {remaining} requests restantes")

        return resp

    return None


def iter_repos(session: requests.Session, language: str):

    page = 1
    while True:
        resp = _github_get(session, f"{BASE_URL}/search/repositories", {
            "q": f"language:{language}",
            "sort": "stars",
            "order": "desc",
            "per_page": 30,
            "page": page,
        })
        if not resp:
            log.error("No se pudo obtener repos, reintentando en 10s...")
            time.sleep(10)
            continue

        items = resp.json().get("items", [])
        if not items:
            log.info(f"Sin más repos en página {page}, reiniciando desde página 1")
            page = 1
            time.sleep(10)
            continue

        for repo in items:
            yield repo["full_name"], repo["stargazers_count"]

        page += 1
        time.sleep(1)  # pausa entre páginas para no saturar la API


def list_files(session: requests.Session, full_name: str, ext: str) -> list[str]:
    resp = _github_get(
        session,
        f"{BASE_URL}/repos/{full_name}/git/trees/HEAD",
        {"recursive": "1"},
    )
    if not resp:
        return []
    tree = resp.json().get("tree", [])
    return [
        item["path"] for item in tree
        if item.get("type") == "blob" and item["path"].endswith(ext)
    ][:MAX_FILES_REPO]


def get_file(session: requests.Session, full_name: str, path: str) -> str | None:
    """Descarga y retorna el contenido de un archivo como string."""
    resp = _github_get(session, f"{BASE_URL}/repos/{full_name}/contents/{path}")
    if not resp:
        return None
    if "application/json" in resp.headers.get("Content-Type", ""):
        data = resp.json()
        if data.get("encoding") == "base64":
            try:
                return base64.b64decode(data["content"]).decode("utf-8", errors="ignore")
            except Exception:
                return None
    return resp.text


# Creacion csv

_csv_lock = threading.Lock()  


def init_csv(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.stat().st_size == 0:
        with open(path, "w", newline="") as f:
            csv.writer(f).writerow(["word", "language", "repo", "stars"])
        log.info(f"CSV creado en {path}")


def write_words(path: Path, words: list[str], language: str, repo: str, stars: int):
    if not words:
        return
    with _csv_lock:
        with open(path, "a", newline="") as f:
            writer = csv.writer(f)
            for word in words:
                writer.writerow([word, language, repo, stars])
            f.flush()


#Main

# Definición de lenguajes, extensiones y extractores
LANGUAGES = [
    ("python", ".py",   extract_python),
    ("java",   ".java", extract_java),
]

_running = True


def _handle_stop(sig, frame):
    global _running
    log.info("Señal de parada recibida, terminando el repo actual...")
    _running = False


signal.signal(signal.SIGTERM, _handle_stop)
signal.signal(signal.SIGINT,  _handle_stop)


def main():
    token    = os.getenv("GITHUB_TOKEN")
    csv_path = Path(os.getenv("OUTPUT_CSV", "./data/words.csv"))

    log.info("Miner iniciando")

    if not token:
        log.warning("GITHUB_TOKEN no configurado — límite de 60 req/hora sin token")

    # Sesión HTTP compartida para todas las requests
    session = requests.Session()
    session.headers.update({
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    if token:
        session.headers["Authorization"] = f"Bearer {token}"
        log.info("Token de GitHub cargado correctamente")

    init_csv(csv_path)
    log.info(f"Archivo de salida: {csv_path}")
    log.info("Presiona Ctrl+C para detener el miner\n")

    # Un iterador por lenguaje alternan repo a repo
    iterators  = {lang: iter_repos(session, lang) for lang, _,   _   in LANGUAGES}
    extractors = {lang: ext                        for lang, _,   ext in LANGUAGES}
    extensions = {lang: ext                        for lang, ext, _   in LANGUAGES}

    total_repos = 0
    total_words = 0
    idx = 0

    while _running:
        lang = LANGUAGES[idx % len(LANGUAGES)][0]
        idx += 1

        full_name, stars = next(iterators[lang])
        log.info(f"[{lang}] {full_name} ({stars:,} ★)")

        files = list_files(session, full_name, extensions[lang])
        if not files:
            log.debug(f"  Sin archivos {extensions[lang]}, saltando")
            continue

        log.info(f"  {len(files)} archivos encontrados")

        repo_words = 0
        for filepath in files:
            if not _running:
                break
            source = get_file(session, full_name, filepath)
            if not source:
                continue
            words = extractors[lang](source)
            if words:
                write_words(csv_path, words, lang, full_name, stars)
                repo_words  += len(words)
                total_words += len(words)

        log.info(f"  → {repo_words} palabras escritas desde {full_name}")
        total_repos += 1

        if total_repos % 10 == 0:
            log.info(f"Progreso: {total_repos} repos procesados | {total_words:,} palabras en total")

        if _running:
            time.sleep(2)

    log.info(f"Miner detenido. {total_repos} repos procesados | {total_words:,} palabras escritas.")


if __name__ == "__main__":
    main()
