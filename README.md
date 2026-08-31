# EMS Overlays

Herramientas para las retransmisiones de iRacing de **EMS (European Master Series)**: overlay web de tiempos para el stream, app de escritorio para dirigir cámaras, y utilidades de datos de carrera.

## Estructura del repositorio

```
.
├── overlay/            # Suite principal: overlay web + Director de cámaras
├── data/               # Datos de ejemplo / históricos de carrera
└── templates/          # Plantilla HTML suelta de una versión temprana del timing tower
```

### `overlay/` — Overlay web + Director

Suite para retransmisiones de iRacing: overlay web de tiempos para el stream + app de escritorio para dirigir cámaras.

```
overlay/
├── controlcamaras.py       # App de escritorio "Director" (customtkinter): clasificación en vivo,
│                            # mapa de pista, tracking de sectores/pits, control de cámaras
├── overlayWeb.py            # Lanzador: arranca overlay/main.py y overlay/renderoverlay.py
├── director_layout.json     # Estado de ventana del Director (se genera/actualiza solo)
├── build.cmd                # Compila los 4 ejecutables con PyInstaller
├── pyi_specs/                # Specs de PyInstaller
└── overlay/                 # Paquete del overlay web
    ├── main.py               # Entry point: servidor Flask + hilos de telemetría iRacing
    ├── renderoverlay.py       # Ventana PyQt5 transparente que embebe el overlay web
    ├── iracing/               # Cliente iRacing, procesado de datos, cámaras, historial, grabación
    ├── web/                   # Servidor Flask, rutas, plantillas y estáticos
    │   ├── templates/
    │   └── static/
    │       └── dorsales/      # Imágenes de dorsales por número de coche
    ├── models/
    └── utils/
```

**Requisitos:** Python 3.x, iRacing corriendo (o modo `--playback`), y las dependencias `irsdk`, `customtkinter`, `flask`, `PyQt5`, `PyQtWebEngine`.

**Uso — todo en uno:**
```
python overlayWeb.py
```
Arranca el servidor Flask en `http://localhost:5000`, la ventana transparente (PyQt5) que lo embebe (activable/desactivable desde `/config`), y el Director (`controlcamaras.py`) para el control de cámaras.

Si solo quieres el Director de forma aislada:
```
python controlcamaras.py
```

**URLs del overlay web (`localhost:5000`):**

| URL | Qué es |
|---|---|
| `/` | Torre de tiempos (overlay principal para el stream) |
| `/config` | Panel de configuración (columnas, formato de nombres, etc.) |
| `/controls` | Panel de controles generales del overlay |
| `/camera` | Controles de cámara (focus leader, por posición/piloto, battles) |
| `/team_assignment` | Asignación de equipos/pilotos |
| `/raceinfo` | Tarjeta de info de carrera |
| `/raceresults` | Tarjeta de resultados |
| `/grid` | Parrilla de salida |
| `/results` | Resultados de carrera |

**Personalización:**
- *Logos de sponsors*: se definen en `overlay/web/templates/timing.html` (bloque `.sponsors-section`); tamaño/espaciado en `timing.css`.
- *Dorsales (números de coche)*: `overlay/web/static/dorsales/{numeroDeCoche}.png`. Se referencian automáticamente por número de coche; también se pueden subir desde `/config`.

**Compilar a `.exe`:** `build.cmd` genera 4 ejecutables independientes con PyInstaller (lanzador, servidor Flask, ventana overlay y Director) que se reparten juntos como una carpeta `dist/`. Los binarios compilados no se incluyen en este repo — solo el código fuente.

### `data/`

JSON de ejemplo/histórico usados por las apps de timing: `preq.json` (datos de demo de pre-qualy) y `race_history.json` (histórico de sesiones procesado por `overlay/overlay/iracing/history.py`).

### `templates/`

Plantilla HTML suelta (`index.html`) de una iteración temprana del timing tower, previa a la versión servida actualmente por Flask en `overlay/overlay/web/templates/`. Se conserva como referencia histórica del desarrollo.

## Colaboración y autoría

`overlay/` arrancó como un proyecto compartido con un compañero (repositorio original en `github.com/mcshi14/iracing_scoreboard`), que desde entonces ha dejado el proyecto. Desde ese punto, el desarrollo, mantenimiento y las nuevas funcionalidades (Director de cámaras, historial de carreras, sistema de licencia/build, empaquetado a `.exe`, etc.) los ha llevado en solitario [Alberto](mailto:albertocs93@gmail.com).

## Notas

Este repositorio recoge el código fuente con fines de portfolio. Se excluyen deliberadamente los ejecutables/binarios compilados (PyInstaller) y un prototipo interno de sincronización de pre-qualy que no está listo para compartir.
