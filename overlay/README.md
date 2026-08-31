# iRacing Overlay & Director

Suite para retransmisiones de iRacing: overlay web de tiempos para el stream + app de escritorio para dirigir cámaras.

## Estructura

```
overlay/
├── controlcamaras.py       # App de escritorio "Director" (customtkinter): clasificación en vivo,
│                            # mapa de pista, tracking de sectores/pits, control de cámaras
├── overlayWeb.py            # Lanzador: arranca overlay/main.py y overlay/renderoverlay.py
├── director_layout.json     # Estado de ventana del Director (se genera/actualiza solo)
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

## Requisitos

- Python 3.x
- iRacing corriendo (o modo `--playback`)
- Dependencias: `irsdk`, `customtkinter`, `flask`, `PyQt5`, `PyQtWebEngine`

## Uso

**Todo en uno:**
```
python overlayWeb.py
```
Arranca el servidor Flask en `http://localhost:5000`, la ventana transparente (PyQt5) que lo embebe (activable/desactivable desde `/config`), y el Director (`controlcamaras.py`) para el control de cámaras.

Si solo quieres el Director de forma aislada, también puedes arrancarlo suelto:
```
python controlcamaras.py
```

## URLs del overlay web (`localhost:5000`)

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

## Personalización

### Logos debajo de la torre de tiempos (sponsors)

Se definen en [`overlay/web/templates/timing.html`](overlay/web/templates/timing.html) dentro del bloque `.sponsors-section`:

```html
<div class="sponsors-section">
    <div class="sponsor-item">
        <img src="/static/EUROPEANMASTERSERIES3D.png" alt="Sponsor 1">
    </div>
</div>
```

Para añadir/cambiar uno:
1. Copia el `.png` a `overlay/web/static/`
2. Añade o edita un `<div class="sponsor-item"><img src="/static/tuarchivo.png"></div>` dentro de `.sponsors-section`

El tamaño/espaciado se controla en `timing.css` (`.sponsors-section` / `.sponsor-item`).

### Dorsales (números de coche)

Van en [`overlay/web/static/dorsales/`](overlay/web/static/dorsales/), nombrados como `{numeroDeCoche}.png` (ej. `10.png`, `44.png`). Se referencian automáticamente en `timing.js`, `race_results.js` y `starting_grid.js`:

```js
img.src = `/static/dorsales/${driver.carNumber}.png`;
img.onerror = function () { this.src = '/static/dorsales/default.png'; };
```

Para un piloto nuevo: solo copia el PNG con el número de su coche a esa carpeta, no hace falta tocar código. También puedes subirlos desde `/config` (incluye galería y borrado).

## Compilar a .exe

`build.cmd` genera 4 ejecutables independientes con PyInstaller (no requieren Python instalado en la máquina que los ejecute):

```
build.cmd
```

Resultado en `dist/`:

| Carpeta | Viene de | Qué es |
|---|---|---|
| `EMS_Overlay/` | `overlayWeb.py` | Lanzador — **este es el que se ejecuta** |
| `overlay_server/` | `overlay/main.py` | Servidor Flask + telemetría |
| `overlay_window/` | `overlay/renderoverlay.py` | Ventana PyQt5 transparente |
| `director/` | `controlcamaras.py` | App de control de cámaras |

Reparte la carpeta `dist/` **completa** (las 4 subcarpetas juntas) — cada `.exe` busca a sus hermanos en carpetas contiguas. Ejecutar `dist\EMS_Overlay\EMS_Overlay.exe` arranca todo el conjunto igual que `python overlayWeb.py` en desarrollo.

No hay ofuscación del código (bytecode empaquetado, técnicamente extraíble). Cada copia lleva una marca de licencia (`license_info.py`) visible en el título del Director y en el pie de `/config`, más un ID de build embebido en el binario para poder identificar una copia concreta si se distribuye sin autorización.
