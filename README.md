# Miner de nombre de funciones

Herramienta para identificar las palabras más utilizadas en nombres de funciones y métodos en código Python y Java, a partir de repositorios públicos de GitHub.

## Componentes

El sistema tiene dos componentes independientes:

- **Miner** — se conecta a GitHub, descarga código fuente y extrae palabras desde nombres de funciones y métodos. Escribe los resultados en un archivo CSV.
- **Visualizer** — lee el CSV y muestra el ranking de palabras más frecuentes por lenguaje, actualizándose en tiempo real.

```
word-miner/
├── run.py              # comando único para levantar todo
├── miner/
│   └── miner.py        # lógica completa del miner
├── visualizer/
│   └── visualizer.py   # dashboard Streamlit
├── data/
│   └── words.csv       # archivo compartido entre componentes
├── requirements.txt
└── README.md
```

---

## Requisitos

- Python 3.12+
- Token de GitHub (gratuito, sin permisos especiales)

Sin token el sistema funciona, pero con un límite de 60 requests por hora, lo que hace el mining muy lento.

---

## Instalación

```bash
pip install -r requirements.txt
```

---

## Ejecución

### Un solo comando

**Bash:**
```
export GITHUB_TOKEN=token
python run.py
```

**PowerShell:**
```
$env:GITHUB_TOKEN="token"; python run.py
```

El visualizer se abre automáticamente en `http://localhost:8501`. El miner empieza a escribir datos en `data/words.csv` de inmediato.

Para detener: `Ctrl+C`.

---


## Logs del miner

Durante la ejecución se muestra el progreso repo por repo:

```
10:32:01  INFO     Miner iniciando
10:32:01  INFO     Token de GitHub cargado correctamente
10:32:01  INFO     Archivo de salida: data/words.csv
10:32:03  INFO     [python] huggingface/transformers (130,000 ★)
10:32:04  INFO       30 archivos encontrados
10:32:08  INFO       → 214 palabras escritas desde huggingface/transformers
10:32:10  INFO     [java] spring-projects/spring-framework (54,000 ★)
```

---

## Variables de entorno

### Miner

| Variable | Default | Descripción |
|---|---|---|
| `GITHUB_TOKEN` | _(vacío)_ | Token de autenticación de GitHub |
| `OUTPUT_CSV` | `./data/words.csv` | Ruta del CSV de salida |
| `LOG_LEVEL` | `INFO` | Nivel de logging (`DEBUG`, `INFO`, `WARNING`) |

### Visualizer

| Variable | Default | Descripción |
|---|---|---|
| `INPUT_CSV` | `./data/words.csv` | Ruta del CSV a leer |
| `REFRESH_SECONDS` | `5` | Intervalo de actualización del dashboard en segundos |
| `TOP_N` | `10` | Cantidad de palabras en el ranking |

---

## Formato del CSV

El CSV es el único canal de comunicación entre el Miner y el Visualizer. Cada fila representa una palabra extraída de un archivo fuente:

```
word,language,repo,stars
make,python,pallets/flask,64821
response,python,pallets/flask,64821
retain,java,spring-projects/spring-framework,54000
```

| Columna | Descripción |
|---|---|
| `word` | Palabra extraída del nombre de la función o método |
| `language` | `python` o `java` |
| `repo` | Nombre completo del repositorio (`owner/repo`) |
| `stars` | Número de stars del repositorio al momento de la extracción |

---

## Decisiones de diseño

### CSV como canal de comunicación

Se eligió un archivo CSV compartido en lugar de un message broker (Redis, RabbitMQ) para simplificar la arquitectura y eliminar dependencias de infraestructura. El CSV es append-only: el Miner solo agrega filas al final y el Visualizer solo lee. Esto evita conflictos de escritura y permite que ambos componentes operen de forma completamente independiente.

### Una palabra por fila

Cada palabra ocupa una fila propia en lugar de agrupar todas las palabras de un archivo en una sola fila. Esto permite al Visualizer calcular el ranking con un simple `value_counts()` de pandas, sin necesidad de parsear listas ni estructuras anidadas.

### Miner en un solo archivo

Toda la lógica del Miner vive en un único archivo `miner.py`, dividido en secciones claramente marcadas. Se optó por esta estructura porque cada función es corta y cohesiva, y tener múltiples módulos añadía complejidad de imports sin beneficio real para un proyecto de este tamaño.

### AST para Python, regex para Java

- **Python**: se usa el módulo `ast` de la librería estándar para recorrer el árbol de sintaxis y encontrar nodos `FunctionDef` y `AsyncFunctionDef`. Es robusto, no requiere dependencias externas y descarta automáticamente comentarios, strings y código muerto.
- **Java**: se usa regex porque las alternativas más robustas (`javalang`) están abandonadas y no soportan Java 14+, mientras que `tree-sitter` requiere compilación de extensiones nativas. El regex cubre correctamente el 95%+ de los casos reales limpiando primero comentarios y strings literales antes de buscar firmas de métodos.

### Repositorios por popularidad

El Miner procesa repositorios en orden descendente de stars porque los repositorios más populares tienden a tener código más idiomático, mejor mantenido y más representativo de las convenciones del lenguaje.

### Alternancia Python/Java

El Miner alterna entre repositorios Python y Java en cada iteración en lugar de procesar todos los de un lenguaje primero. Esto asegura que el CSV tenga datos de ambos lenguajes desde el principio, lo que permite al Visualizer mostrar rankings útiles incluso después de pocos minutos de ejecución.

### Métodos excluidos

Se excluyen del ranking los métodos que aparecen en prácticamente todo repositorio y no aportan información sobre el dominio:

- **Python**: métodos dunder (`__init__`, `__str__`, `__repr__`, `__len__`, etc.) — identificados porque el nombre empieza y termina con `__`.
- **Java**: métodos de infraestructura estándar definidos en la constante `JAVA_EXCLUDED`: `main`, `toString`, `hashCode`, `equals`, `clone`, `finalize`.

---

## Supuestos

- Se asume que los repositorios más populares de GitHub son representativos del uso real del lenguaje.
- Se asume que los nombres de funciones siguen las convenciones estándar del lenguaje (`snake_case` en Python, `camelCase` en Java). Nombres que mezclan convenciones de forma no estándar pueden no separarse correctamente.
- El sistema no deduplica palabras entre repositorios — si la misma función aparece en 100 repos, cuenta 100 veces. Esto es intencional: la frecuencia refleja cuánto se usa ese concepto en el ecosistema, no solo cuántos proyectos lo tienen.
- El CSV puede crecer indefinidamente. Para ejecuciones largas se recomienda monitorear el tamaño del archivo.
