// Variables de estado
let activeColumns = [];
let previousActiveColumns = []; // Para detectar cambios en las columnas
let lastUpdate = 0;
let lastKnownSectorStrings = {};
let sessionData = null; // Will store the whole data object from WebSocket now
let updateInterval;
let rotationInterval; // Intervalo para la rotación de pilotos adicionales
let previousPositions = {}; // Para rastrear cambios de posición
let lastConfigModified = 0; // Última modificación del archivo de configuración
let driverElements = {}; // Mapa para mantener referencias a los elementos DOM de cada piloto
let lastLapTimes = {}; // Para rastrear cambios en los tiempos de última vuelta
let currentSessionBestSectors = {}; // Track session best sectors for delta recalculation
let animationTimeout; // Para controlar el timeout de la animación
let focusedDriverEnabled = false; // Declare focusedDriverEnabled
let focusedDriverBattleMode = true; // Show P1/P2 duel/train card when close to a rival (race only)

// Configuración para la visualización de pilotos
const MAX_FIXED_DRIVERS = 20; // Número máximo de pilotos fijos a mostrar
const ROTATING_DRIVERS = 5; // Número de pilotos adicionales que rotan
let rotationIndex = 0; // Índice actual para la rotación

// Focused Driver Display variables
let focusedDriverDisplayIndex = 0; // Index for cycling dynamic data
const FOCUSED_DRIVER_DYNAMIC_FIELDS = ['lastLapTime', 'bestLapTime', 'gap', 'interval', 'positionsGained'];
// Inicializar la página
document.addEventListener('DOMContentLoaded', function() {
    // WebSocket connection
    const ws = new WebSocket(`ws://${window.location.host}/ws/timing-data`);

    ws.onopen = () => {
        console.log('WebSocket connected');
        // Iniciar la rotación de pilotos adicionales cada 5 segundos
        rotationInterval = setInterval(rotateAdditionalDrivers, 5000);
    };

    ws.onmessage = (event) => {
        let data = JSON.parse(event.data);

        // data.drivers is the array of drivers — no merging needed

        if (data.error) {
            console.log("Backend error:", data.error);
            document.getElementById('connection-status').textContent = 'Desconectado';
            document.getElementById('connection-indicator').className = 'connection-status disconnected';
            updateFocusedDriverInfo(null, null); // Clear focused driver info on error
            return;
        }

        if (!data || !data.drivers) {
            console.log("Received invalid data structure via WebSocket:", data);
            document.getElementById('connection-status').textContent = 'Datos Inválidos';
            document.getElementById('connection-indicator').className = 'connection-status disconnected';
            updateFocusedDriverInfo(null, null); // Clear focused driver info
            return;
        }

        // Check for configuration updates from WebSocket
        if (data.config) {
            console.log("Received config via WebSocket:", data.config); // Add this log
            let configChanged = false;
            if (data.config.activeColumns && JSON.stringify(data.config.activeColumns) !== JSON.stringify(activeColumns)) {
                previousActiveColumns = [...activeColumns];
                activeColumns = data.config.activeColumns;
                configChanged = true;
                console.log("Active columns updated via WebSocket:", activeColumns);
            }
            // Check for focusedDriverEnabled changes
            if (typeof data.config.focusedDriverEnabled !== 'undefined' && data.config.focusedDriverEnabled !== focusedDriverEnabled) {
                focusedDriverEnabled = data.config.focusedDriverEnabled; // Update local state
                // Trigger update for focused driver info, which will react to the new enabled state
                updateFocusedDriverInfo(data.focusedDriver, data);
                console.log("Focused driver enabled state updated via WebSocket:", focusedDriverEnabled);
            }
            // Check for focusedDriverBattleMode changes
            if (typeof data.config.focusedDriverBattleMode !== 'undefined' && data.config.focusedDriverBattleMode !== focusedDriverBattleMode) {
                focusedDriverBattleMode = data.config.focusedDriverBattleMode;
                updateFocusedDriverInfo(data.focusedDriver, data);
                console.log("Focused driver battle mode updated via WebSocket:", focusedDriverBattleMode);
            }

            if (configChanged) { // Re-render if columns changed, regardless of sessionData state
                updateTimingTableWithAnimation(data, null);
            }
        }

        // Actualizar solo si hay nuevos datos (timestamp diferente)
        // This block handles general session data updates, including drivers and other info
        if (data.timestamp !== lastUpdate) {
            const oldData = sessionData;
            sessionData = data;
            lastUpdate = data.timestamp;

            // Capture server time for live lap timer interpolation
            if (data.sessionTime !== undefined) {
                _fdServerSessionTime = data.sessionTime;
                _fdClientReceiveMs = Date.now();
            }

            // Check if session best sectors changed — recalculate all visible popups
            if (data.sessionBestSectors) {
                const newBests = data.sessionBestSectors;
                const changed = JSON.stringify(newBests) !== JSON.stringify(currentSessionBestSectors);
                currentSessionBestSectors = { ...newBests };
                if (changed) {
                    recalculateVisiblePopups();
                }
            }

            updateTimingTable(data, oldData);
            updateSessionInfo(data);
            updateLiveIndicator(data.sessionFlags || 0);
            updateFocusedDriverInfo(data.focusedDriver, data); // Pass the whole data object for config access

            document.getElementById('connection-status').textContent = 'Conectado';
            document.getElementById('connection-indicator').className = 'connection-status connected';
        }
    };

    ws.onclose = () => {
        console.log('WebSocket disconnected');
        document.getElementById('connection-status').textContent = 'Desconectado';
        document.getElementById('connection-indicator').className = 'connection-status disconnected';
        updateFocusedDriverInfo(null, null); // Clear focused driver info on disconnect
        clearInterval(rotationInterval); // Stop rotation when disconnected
    };
});

// Función para rotar los pilotos adicionales
function rotateAdditionalDrivers() {
    if (!sessionData || !sessionData.drivers || sessionData.drivers.length <= MAX_FIXED_DRIVERS) {
        return; // No hay suficientes pilotos para rotar
    }

    const totalRotatingDrivers = Math.max(0, sessionData.drivers.length - MAX_FIXED_DRIVERS);
    const rotationGroups = Math.ceil(totalRotatingDrivers / ROTATING_DRIVERS);
    rotationIndex = (rotationIndex + 1) % rotationGroups;

    if (sessionData) {
        updateTimingTable(sessionData, null);
    }
}

// Eliminar la función checkColumnsUpdate ya que las actualizaciones se harán por WebSocket
/*
function checkColumnsUpdate() {
    fetch('/api/active-columns')
        .then(response => response.json())
        .then(data => {
            if (data.success && JSON.stringify(data.activeColumns) !== JSON.stringify(activeColumns)) {
                previousActiveColumns = [...activeColumns];
                activeColumns = data.activeColumns;

                if (sessionData) {
                    updateTimingTableWithAnimation(sessionData, null);
                }
            }
        })
        .catch(error => console.error('Error al verificar columnas:', error));
}
*/

// Actualizar la tabla de timing con animación para cambios de columnas
function updateTimingTableWithAnimation(data, oldData) {
    // Primero actualizar la cabecera con animación
    updateColumnsHeaderWithAnimation();

    // Luego actualizar la tabla
    updateTimingTable(data, oldData);
}

// Función para actualizar la cabecera de columnas con animación
function updateColumnsHeaderWithAnimation() {
    const headerContainer = document.getElementById('columns-header');
    const oldColumns = [...previousActiveColumns];
    const newColumns = [...activeColumns];

    // Identificar columnas añadidas y eliminadas
    const addedColumns = newColumns.filter(col => !oldColumns.includes(col));
    const removedColumns = oldColumns.filter(col => !newColumns.includes(col));

    // Actualizar la cabecera normalmente (ya se hace en updateTimingTable)
    // No es necesario llamar a updateColumnsHeader aquí, ya que está inlined en updateTimingTable.

    // Aplicar animaciones a las columnas añadidas
    if (addedColumns.length > 0) {
        addedColumns.forEach(column => {
            const elements = document.querySelectorAll(`.header-column.${column}, .timing-column.${column}`);
            elements.forEach(el => {
                el.classList.add('column-enter');
                setTimeout(() => {
                    el.classList.remove('column-enter');
                }, 500);
            });
        });
    }
}

// Obtener datos de timing del servidor - No longer needed, using WebSocket
/*
function fetchTimingData() {
    fetch('/api/timing-data')
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                console.log(data.error);
                document.getElementById('connection-status').textContent = 'Desconectado';
                document.getElementById('connection-indicator').className = 'connection-status disconnected';
                return;
            }

            // Actualizar solo si hay nuevos datos (timestamp diferente)
            if (data.timestamp !== lastUpdate) {
                // Guardar los datos actuales para comparar posiciones
                const oldData = sessionData;
                sessionData = data;
                lastUpdate = data.timestamp;

                // Actualizar la tabla con las columnas activas actuales
                updateTimingTable(data, oldData);
                updateSessionInfo(data);

                document.getElementById('connection-status').textContent = 'Conectado';
                document.getElementById('connection-indicator').className = 'connection-status connected';
            }
        })
        .catch(error => console.error('Error:', error));
}
*/

// Definiciones de columnas y traducciones
const columnDefinitions = {
    position: {
        name: "Pos",
        width: 0.8
    },
    brands: {
        name: " ",
        width: 0.6
    },
    teamLogo: {
        name: "Team",
        width: 0.8
    },
    carNumber: {
        name: "Nº",
        width: 0.9
    },
    userName: {
        name: "Piloto",
        width: 2.5
    },
    teamName: {
        name: "Equipo",
        width: 3
    },
    carName: {
        name: "Coche",
        width: 2
    },
    bestLapTime: {
        name: "Mejor Vuelta",
        width: 2
    },
    lastLapTime: {
        name: "Última Vuelta",
        width: 2
    },
    lapsComplete: {
        name: "Vueltas",
        width: 1
    },
    interval: {
        name: "Intervalo",
        width: 2
    },
    gap: {
        name: "Gap",
        width: 2
    },
    pitstops: {
        name: "Pitstops",
        width: 1
    },
    lastPitTime: {
        name: "Pit Lane",
        width: 1.5
    },
    lastPitBoxTime: {
        name: "Pit Box",
        width: 1.5
    },
    lastPitLap: {
        name: "Vuelta Pit",
        width: 1.2
    },
    iRating: {
        name: "iRating",
        width: 1
    },
    tireCompound: {
        name: "Neumático",
        width: 1
    },
    onPitRoad: {
        name: "Pits",
        width: 0.8
    },
    positionsGained: {
        name: "±",
        width: 0.8
    },
    sectors: {
        name: "Sectores",
        width: 1 // Ajusta según necesites
    },
    performanceScore: {
        name: "Perf",
        width: 1.4
    },
};

// Función para calcular la distancia de desplazamiento basada en la posición
function calculatePositionOffset(oldPosition, newPosition) {
    // Cada fila tiene 30px de altura, calculamos el desplazamiento en píxeles
    const rowHeight = 30;
    return (oldPosition - newPosition) * rowHeight;
}

// Función para determinar si un cambio de posición es un adelantamiento significativo
function isSignificantOvertake(oldPosition, newPosition) {
    // Consideramos adelantamiento significativo si se ganan 2 o más posiciones
    return (oldPosition - newPosition) >= 50;
}

// Actualizar la tabla de timing
function updateTimingTable(data, oldData) {
    // ** START of inlined updateColumnsHeader **
    const headerContainer = document.getElementById('columns-header');
    headerContainer.innerHTML = '';
    headerContainer.style.width = 'fit-content';
    headerContainer.style.minWidth = '100%';

    activeColumns.forEach(column => {
        const colDef = columnDefinitions[column] || {
            name: column,
            width: 2
        };

        const headerColumn = document.createElement('div');
        headerColumn.className = `header-column ${column}`;
        headerColumn.style.width = `${colDef.width * 50}px`;
        headerColumn.style.minWidth = `${colDef.width * 50}px`;
        headerColumn.textContent = colDef.name;

        headerContainer.appendChild(headerColumn);
    });
    // ** END of inlined updateColumnsHeader **


    // Preparar el contenedor para las filas
    const rowsContainer = document.getElementById('timing-rows');

    // Asegurarse de que el contenedor tenga la clase timing-container
    rowsContainer.classList.add('timing-container');

    // Crear un nuevo mapa para los elementos actuales
    const newDriverElements = {};

    // Crear un mapa de posiciones anteriores si tenemos datos antiguos
    if (oldData && oldData.drivers) {
        previousPositions = {};
        oldData.drivers.forEach(driver => {
            // Usar carIdx o UserID como identificador único
            const driverId = driver.carIdx || driver.UserID;
            if (driverId) {
                previousPositions[driverId] = driver.position;
            }
        });
    }

    // Primero, crear o actualizar todos los elementos de piloto
    data.drivers.forEach(driver => {
        // Identificador único del piloto
        const driverId = driver.carIdx || driver.UserID;
        if (!driverId) return;

        let driverBlock;
        let isNewElement = false;

        // Comprobar si ya existe un elemento para este piloto
        if (driverElements[driverId]) {
            // Usar el elemento existente
            driverBlock = driverElements[driverId];
            // Limpiar clases de animación anteriores
            driverBlock.classList.remove('moving-up', 'moving-down', 'overtake', 'position-up-gradient', 'position-down-gradient', 'row-highlight', 'not-on-track');
            // Actualizar la clase de posición
            driverBlock.className = `timing-row driver-block position-${driver.position}`;
        } else {
            // Crear un nuevo elemento
            driverBlock = document.createElement('div');
            driverBlock.className = `timing-row driver-block position-${driver.position}`;
            driverBlock.setAttribute('data-driver-id', driverId);
            driverBlock.style.transition = 'transform 0.8s ease-out, background-color 0.3s ease'; // Añadir transición aquí
            isNewElement = true;
        }

        // Check if the driver is not on track (abandoned)
        const isAbandoned = driver.finished || (driver.lapProgress === undefined) || (driver.currentLap === undefined);
        if (isAbandoned) {
            driverBlock.classList.add('not-on-track');
        } else {
            driverBlock.classList.remove('not-on-track');
        }

        // Highlight the focused driver's row
        const focusedCarIdx = sessionData && sessionData.focusedDriver ? sessionData.focusedDriver.carIdx : null;
        if (focusedCarIdx && driver.carIdx === focusedCarIdx) {
            driverBlock.classList.add('fd-row-focused');
        } else {
            driverBlock.classList.remove('fd-row-focused');
        }

        // Comprobar si ha cambiado de posición
        if (!isNewElement && previousPositions[driverId] && previousPositions[driverId] !== driver.position) {
            const oldPosition = previousPositions[driverId];
            const newPosition = driver.position;

            if (newPosition < oldPosition && !driverBlock.classList.contains('moving-up') && !driverBlock.classList.contains('overtake')) {
                // Ha mejorado posición (subido)
                const positionsGained = oldPosition - newPosition;

                if (isSignificantOvertake(oldPosition, newPosition)) {
                    // ¡Es un adelantamiento significativo!
                    driverBlock.classList.add('overtake');
                    driverBlock.classList.remove('moving-down');

                    // Calcular el desplazamiento y aplicar la transformación inicial
                    const offset = calculatePositionOffset(oldPosition, newPosition);
                    driverBlock.style.transform = `translateY(${offset}px)`;

                    // Forzar reflow para que la animación funcione
                    void driverBlock.offsetHeight;

                    // Aplicar la transformación final (volver a la posición normal)
                    driverBlock.style.transform = 'translateY(0)';

                    // Ajustar el timeout para que coincida con la duración de la animación de adelantamiento (800ms)
                    clearTimeout(animationTimeout);
                    animationTimeout = setTimeout(() => {
                        driverBlock.classList.remove('overtake');
                        driverBlock.style.transform = ''; // Limpiar la transformación después de la animación
                    }, 800);
                } else {
                    // Es una mejora de posición normal (no un adelantamiento significativo)
                    driverBlock.classList.add('moving-up');
                    driverBlock.classList.remove('moving-down');

                    // Calcular el desplazamiento y aplicar la transformación inicial
                    const offset = calculatePositionOffset(oldPosition, newPosition);
                    driverBlock.style.transform = `translateY(${offset}px)`;

                    // Forzar reflow para que la animación funcione
                    void driverBlock.offsetHeight;

                    // Aplicar la transformación final (volver a la posición normal)
                    driverBlock.style.transform = 'translateY(0)';

                    // Ajustar el timeout para que coincida con la duración de la animación CSS (500ms)
                    clearTimeout(animationTimeout);
                    animationTimeout = setTimeout(() => {
                        driverBlock.classList.remove('moving-up', 'moving-down');
                        driverBlock.style.transform = ''; // Limpiar la transformación después de la animación
                    }, 500); // Coincidir con la duración de la animación CSS
                }

            } else if (newPosition > oldPosition && !driverBlock.classList.contains('moving-down')) {
                // Ha empeorado posición (bajado)
                driverBlock.classList.add('moving-down');
                driverBlock.classList.remove('moving-up', 'overtake');

                // Calcular el desplazamiento y aplicar la transformación inicial
                const offset = calculatePositionOffset(oldPosition, newPosition);
                driverBlock.style.transform = `translateY(${offset}px)`;

                // Forzar reflow para que la animación funcione
                void driverBlock.offsetHeight;

                // Aplicar la transformación final (volver a la posición normal)
                driverBlock.style.transform = 'translateY(0)';

                // Ajustar el timeout para que coincida con la duración de la animación CSS (500ms)
                clearTimeout(animationTimeout);
                animationTimeout = setTimeout(() => {
                    driverBlock.classList.remove('moving-up', 'moving-down', 'overtake');
                    driverBlock.style.transform = ''; // Limpiar la transformación después de la animación
                }, 500); // Coincidir con la duración de la animación CSS
            }
        }

        // ---------------------------------------------------------
        // 1. LÓGICA DEL SLIDER (MODIFICADA E INTEGRADA)
        // ---------------------------------------------------------
        const sessionType = data.sessionType ? data.sessionType.toUpperCase() : '';
        // Descomenta la siguiente línea si quieres restringirlo solo a Clasificación/Práctica
        const isTimeBased = sessionType.includes('QUALIFY') || sessionType.includes('PRACTICE');
        // const isTimeBased = true; // Forzamos true para que salga siempre por ahora

        if (isTimeBased) {
            const currentLastSector = driver.lastSector;

            // Si el sector es válido y es DIFERENTE al último que vimos
            if (currentLastSector &&
                currentLastSector !== '-' &&
                currentLastSector !== 'N/A' &&
                lastKnownSectorStrings[driverId] !== currentLastSector) {

                // Actualizamos la memoria
                lastKnownSectorStrings[driverId] = currentLastSector;
                // Lanzamos la animación con delta to session best
                showSectorSlider(driverBlock, driver, currentLastSector);
            }
        }
        // ---------------------------------------------------------

        // Limpiar el contenido existente (excepto indicadores, etiquetas Y EL POP-OVER)
        Array.from(driverBlock.children).forEach(child => {
            if (!child.classList.contains('position-change-indicator') &&
                !child.classList.contains('position-change-label') &&
                !child.classList.contains('sector-popover')) { // <--- PROTECCIÓN CRUCIAL AÑADIDA
                driverBlock.removeChild(child);
            }
        });

        // Crear elementos para cada columna activa
        activeColumns.forEach(column => {
            const colDef = columnDefinitions[column] || {
                name: column,
                width: 2
            };

            const columnDiv = document.createElement('div');
            columnDiv.className = `timing-column ${column}`;
            columnDiv.setAttribute('data-driver-id', driverId);

            // Aplicar estilo según el ancho de la columna
            columnDiv.style.width = `${colDef.width * 50}px`;
            columnDiv.style.minWidth = `${colDef.width * 50}px`;
            columnDiv.style.textAlign = column === 'position' || column === 'carNumber' ? 'center' : 'left';

            // Formatear el valor según el tipo de columna
            let value = driver[column];
            
            // Añadir indicador de cambio de posición en la columna de posición
            if (column === 'position' && previousPositions[driverId] && previousPositions[driverId] !== driver.position) {
                const oldPosition = previousPositions[driverId];
                const newPosition = driver.position;

                // Crear el elemento para mostrar el cambio de posición
                const positionChange = document.createElement('span');

                if (newPosition < oldPosition) {
                    // Mejoró posición
                    const positionsGained = oldPosition - newPosition;

                    if (isSignificantOvertake(oldPosition, newPosition)) {
                        // ¡Es un adelantamiento significativo!
                        positionChange.className = 'position-change-overtake';
                        positionChange.textContent = `+${positionsGained} 🏁`;
                    } else {
                        // Es una mejora de posición normal
                        positionChange.className = 'position-change position-change-up';
                        positionChange.textContent = `+${positionsGained}`;
                    }
                } else {
                    // Empeoró posición
                    const positionsLost = newPosition - oldPosition;
                    positionChange.className = 'position-change position-change-down';
                    positionChange.textContent = `-${positionsLost}`;
                }

                // Añadir el texto del valor de posición
                columnDiv.textContent = value || '';

                // Añadir el indicador de cambio
                columnDiv.appendChild(positionChange);

                // Eliminar el indicador después de la animación
                setTimeout(() => {
                    if (columnDiv.contains(positionChange)) {
                        columnDiv.removeChild(positionChange);
                    }
                }, isSignificantOvertake(oldPosition, newPosition) ? 1500 : 5000);
            } else if (column === 'bestLapTime' || column === 'lastLapTime') {
                if (value && value !== "N/A" && value !== "999:59.999") {
                    // Formatear tiempo de vuelta para asegurar formato MM:SS.mmm
                    if (typeof value === 'string' && value.includes('s')) {
                        // Convertir de "65s" a "1:05.000"
                        const seconds = parseFloat(value);
                        if (!isNaN(seconds)) {
                            const minutes = Math.floor(seconds / 60);
                            const remainingSeconds = (seconds % 60).toFixed(3);
                            value = `${minutes}:${remainingSeconds.padStart(6, '0')}`;
                        }
                    }

                    // Verificar si es la última vuelta y ha cambiado
                    if (column === 'lastLapTime' && oldData) {
                        const oldLapTime = lastLapTimes[driverId];

                        if (oldLapTime && oldLapTime !== value) {
                            // Añadir clase para animación
                            columnDiv.classList.add('last-lap-updated');

                            // Programar la eliminación de la clase después de unos segundos
                            setTimeout(() => {
                                const elements = document.querySelectorAll(`.timing-column.lastLapTime[data-driver-id="${driverId}"]`);
                                elements.forEach(el => {
                                    el.classList.remove('last-lap-updated');
                                });
                            }, 5000); // 5 segundos
                        }
                    }

                    columnDiv.textContent = value;
                } else {
                    columnDiv.textContent = '-';
                }
            } else if (column === 'interval' || column === 'gap') {
                columnDiv.classList.remove('out-lap-text');
                if (driver.onOutLap && data.sessionType &&
                    (data.sessionType.toLowerCase().includes('qualify') || data.sessionType.toLowerCase().includes('practice'))) {
                    columnDiv.textContent = 'OUT';
                    columnDiv.classList.add('out-lap-text');
                } else if (driver.position === 1) {
                    // En clasificación o práctica, mostrar el mejor tiempo para el líder
                    if (data.sessionType && (data.sessionType.toLowerCase().includes('qualify') || data.sessionType.toLowerCase().includes('practice'))) {
                        columnDiv.textContent = driver.bestLapTime || '-';
                    } else {
                        columnDiv.textContent = 'Leader';
                    }
                } else {
                    columnDiv.textContent = value || '-';
                }
            } else if (column === 'brands') {
                // Clear previous content
                columnDiv.innerHTML = '';

                // Handle brand image display
                if (driver.brandImageUrl && driver.brandImageUrl.trim() !== '') {
                    const img = document.createElement('img');
                    img.src = driver.brandImageUrl;
                    img.style.maxHeight = '24px';
                    img.style.maxWidth = '100%';
                    img.style.objectFit = 'contain';
                    columnDiv.appendChild(img);
                }
            } else if (column === 'teamLogo') {
                columnDiv.innerHTML = '';
                if (driver.teamLogoUrl && driver.teamLogoUrl.trim() !== '') {
                    const img = document.createElement('img');
                    img.src = driver.teamLogoUrl;
                    img.alt = driver.teamName || 'Team Logo';
                    img.style.maxHeight = '24px';
                    img.style.maxWidth = '100%';
                    img.style.objectFit = 'contain';
                    columnDiv.appendChild(img);
                }
            } else if (column === 'carNumber') {
                // Clear previous content
                columnDiv.innerHTML = '';

                // Create image element for the race number
                const img = document.createElement('img');
                img.src = `/static/dorsales/${value}.png`; // Assumes images are in /static/dorsales/ and named {carNumber}.png
                img.alt = `Dorsal ${value}`;
                img.style.maxHeight = '24px'; // Adjust size as needed
                img.style.maxWidth = '100%';
                img.style.objectFit = 'contain';
                img.style.verticalAlign = 'middle'; // Align image vertically

                // Fallback to text if image fails to load
                img.onerror = () => {
                    columnDiv.textContent = value || ''; // Show number if image not found
                };

                columnDiv.appendChild(img);
            } else if (column === 'userName') {
                columnDiv.textContent = value || '';
                // Add checkered flag emoji if driver has finished
                if (driver.finished) {
                    const flagSpan = document.createElement('span');
                    flagSpan.className = 'finished-flag';
                    flagSpan.textContent = ' 🏁'; // Add a space before the emoji
                    columnDiv.appendChild(flagSpan);
                }
            } else if (column === 'tireCompound') {
                columnDiv.innerHTML = ''; // Clear previous content
                const tireSpan = document.createElement('span');
                tireSpan.className = 'tire-indicator';
                if (value === 'Dry') {
                    tireSpan.textContent = 'D';
                    tireSpan.classList.add('tire-dry');
                    tireSpan.title = 'Dry Tires';
                } else if (value === 'Wet') {
                    tireSpan.textContent = 'W';
                    tireSpan.classList.add('tire-wet');
                    tireSpan.title = 'Wet Tires';
                } else {
                    tireSpan.textContent = 'U';
                    tireSpan.classList.add('tire-unknown');
                    tireSpan.title = 'Unknown Tires';
                }
                columnDiv.appendChild(tireSpan);
                } else if (column === 'onPitRoad') {
                    columnDiv.innerHTML = ''; // Clear previous content
                    const pitSpan = document.createElement('span');
                    pitSpan.className = 'pit-indicator';
                    if (value === true) {
                        // Check if this is an abandoned car by looking at other data
                        const isAbandoned = driver.finished || (driver.lapProgress === undefined) || (driver.currentLap === undefined);
                        if (isAbandoned) {
                            driverBlock.classList.add('not-on-track');
                            pitSpan.textContent = 'OUT';
                            pitSpan.classList.add('abandoned');
                            pitSpan.title = 'Not on Track';
                        } else if (value === true) {
                            pitSpan.textContent = 'PIT';
                            pitSpan.classList.add('in-pits');
                            pitSpan.title = 'In Pits';
                        } else {
                            pitSpan.textContent = '';
                            pitSpan.classList.add('not-in-pits');
                            pitSpan.title = 'On Track';
                        }
                    } else {
                        pitSpan.textContent = '';
                        pitSpan.classList.add('not-in-pits');
                        pitSpan.title = 'On Track';
                    }
                    columnDiv.appendChild(pitSpan);
            } else if (column === 'lastPitTime') {
                // Display last pit stop duration
                if (value !== null && value !== undefined && value > 0) {
                    columnDiv.textContent = `${value.toFixed(1)}s`;
                    columnDiv.style.textAlign = 'right';
                } else {
                    columnDiv.textContent = '-';
                    columnDiv.style.textAlign = 'right';
                }
            } else if (column === 'lastPitBoxTime') {
                // Display last pit box (stationary) duration
                if (value !== null && value !== undefined && value > 0) {
                    columnDiv.textContent = `${value.toFixed(1)}s`;
                    columnDiv.style.textAlign = 'right';
                } else {
                    columnDiv.textContent = '-';
                    columnDiv.style.textAlign = 'right';
                }
            } else if (column === 'positionsGained') {
                columnDiv.textContent = '';
                columnDiv.style.textAlign = 'center';
                columnDiv.classList.remove('gained-up', 'gained-down', 'gained-same');
                if (value !== null && value !== undefined && value !== 0) {
                    if (value > 0) {
                        columnDiv.textContent = '+' + value;
                        columnDiv.classList.add('gained-up');
                    } else {
                        columnDiv.textContent = '' + value;
                        columnDiv.classList.add('gained-down');
                    }
                } else if (value === 0) {
                    columnDiv.textContent = '=';
                    columnDiv.classList.add('gained-same');
                } else {
                    columnDiv.textContent = '-';
                }
            } else if (column === 'lastPitLap') {
                // Display lap number when last pit stop occurred
                if (value !== null && value !== undefined && value > 0) {
                    columnDiv.textContent = `L${value}`;
                    columnDiv.style.textAlign = 'center';
                } else {
                    columnDiv.textContent = '-';
                    columnDiv.style.textAlign = 'center';
                }
            } else if (column === 'sectors') {
                columnDiv.innerHTML = ''; 
                columnDiv.className = `timing-column ${column} sectors-container`;
                
                // Si value es null o undefined, usamos [0,0,0]
                const sectorsData = Array.isArray(value) ? value : [0, 0, 0];
                // Dibujamos las 3 cajitas
                for (let i = 0; i < 3; i++) {
                    const box = document.createElement('div');
                    box.className = 'sector-box';
                    
                    const status = sectorsData[i] || 0;
                    
                    if (status === 1) {
                        box.classList.add('sec-gray');  // No mejora
                    } else if (status === 2) {
                        box.classList.add('sec-green'); // Récord personal
                    } else if (status === 3) {
                        box.classList.add('sec-purple'); // Récord absoluto
                    } else {
                        box.classList.add('sec-none');  // Pendiente
                    }
                    
                    columnDiv.appendChild(box);
                }
            } else if (column === 'performanceScore') {
                columnDiv.innerHTML = '';
                columnDiv.style.textAlign = 'center';
                const score = parseFloat(value);
                if (!isNaN(score) && score >= 0) {
                    const badge = document.createElement('span');
                    badge.className = 'perf-score';
                    badge.textContent = score.toFixed(1);
                    if (score >= 70) badge.classList.add('perf-high');
                    else if (score >= 45) badge.classList.add('perf-mid');
                    else badge.classList.add('perf-low');
                    columnDiv.appendChild(badge);
                } else {
                    columnDiv.textContent = '-';
                }
            } else {
                columnDiv.textContent = value || '';
            }

            // Aplicar color al texto del intervalo basado en el valor
            if (column === 'interval') {
                const intervalValue = parseFloat(value);
                if (!isNaN(intervalValue)) {
                    if (intervalValue < 0.7) {
                        columnDiv.style.color = 'rgb(255, 204, 0)';
                    } else if (intervalValue < 1.5) {
                        columnDiv.style.color = 'rgb(144, 238, 144)';
                    } else {
                        columnDiv.style.color = ''; // Restablecer al color por defecto
                    }
                }
            }

            driverBlock.appendChild(columnDiv);
        });

        // Guardar la referencia al elemento
        newDriverElements[driverId] = driverBlock;
    });

    // Ordenar los pilotos por posición
    const sortedDrivers = [...data.drivers].sort((a, b) => a.position - b.position);

    // Crear un DocumentFragment para construir la tabla
    const fragment = document.createDocumentFragment();

    // Determinar qué pilotos mostrar (fijos + rotativos)
    let driversToShow = [];

    // Siempre mostrar los primeros MAX_FIXED_DRIVERS pilotos
    const fixedDrivers = sortedDrivers.slice(0, Math.min(MAX_FIXED_DRIVERS, sortedDrivers.length));
    driversToShow = [...fixedDrivers];

    // Si hay más pilotos que los fijos, añadir los rotativos
    if (sortedDrivers.length > MAX_FIXED_DRIVERS) {
        // Calcular el rango de pilotos rotativos
        const remainingDrivers = sortedDrivers.slice(MAX_FIXED_DRIVERS);

        // Calcular el índice de inicio basado en el grupo de rotación actual
        const rotationStart = rotationIndex * ROTATING_DRIVERS;
        const rotationEnd = Math.min(rotationStart + ROTATING_DRIVERS, remainingDrivers.length);

        // Añadir los pilotos rotativos
        const rotatingDrivers = remainingDrivers.slice(rotationStart, rotationEnd);
        driversToShow = [...driversToShow, ...rotatingDrivers];

        // Añadir filas vacías si no hay suficientes pilotos rotativos
        const emptyRowsNeeded = ROTATING_DRIVERS - rotatingDrivers.length;
        for (let i = 0; i < emptyRowsNeeded; i++) {
            const emptyRow = document.createElement('div');
            // Alternar entre odd y even basado en la posición (MAX_FIXED_DRIVERS + rotatingDrivers.length + i)
            const position = MAX_FIXED_DRIVERS + rotatingDrivers.length + i + 1;
            const rowType = position % 2 === 0 ? 'even' : 'odd';
            emptyRow.className = `timing-row empty-row ${rowType}`;
            emptyRow.style.height = '30px'; // Misma altura que las filas normales
            emptyRow.style.opacity = '1'; // Hacer visible el fondo
            emptyRow.style.color = 'transparent'; // Ocultar el texto
            driversToShow.push({ isPlaceholder: true, element: emptyRow });
        }
    }

    // Añadir los elementos en el orden correcto
    let addedFixedDrivers = 0;
    let addedRotatingDrivers = 0;

    driversToShow.forEach(driver => {
        if (driver.isPlaceholder) {
            fragment.appendChild(driver.element);
            return;
        }

        const driverId = driver.carIdx || driver.UserID;
        if (!driverId || !newDriverElements[driverId]) return;

        // Determinar si este piloto es fijo o rotativo
        if (addedFixedDrivers < fixedDrivers.length) {
            // Piloto fijo
            fragment.appendChild(newDriverElements[driverId]);
            addedFixedDrivers++;

            // Si este es el último piloto fijo y hay pilotos rotativos, añadir el separador
            if (addedFixedDrivers === fixedDrivers.length && sortedDrivers.length > MAX_FIXED_DRIVERS) {
                const separator = document.createElement('div');
                separator.className = 'rotating-drivers-separator';

                const label = document.createElement('div');
                label.className = 'rotating-drivers-label';
                label.textContent = 'ROTANDO';

                separator.appendChild(label);
                fragment.appendChild(separator);
            }
        } else {
            // Piloto rotativo
            fragment.appendChild(newDriverElements[driverId]);
            addedRotatingDrivers++;
        }
    });

    // Limpiar el contenedor y añadir el fragmento
    rowsContainer.innerHTML = '';
    rowsContainer.appendChild(fragment);

    // Actualizar el mapa de elementos
    driverElements = newDriverElements;

    // Ajustar el ancho del timing tower basado en las columnas activas
    let totalWidth = activeColumns.reduce((acc, column) => {
        const colDef = columnDefinitions[column] || {
            width: 2
        };
        return acc + (colDef.width * 50);
    }, 40); // 40px extra para padding y bordes

    document.querySelector('.timing-tower').style.width = `${totalWidth}px`;

    // Actualizar los tiempos de última vuelta para la próxima comparación
    data.drivers.forEach(driver => {
        const driverId = driver.carIdx || driver.UserID;
        if (driverId && driver.lastLapTime) {
            lastLapTimes[driverId] = driver.lastLapTime;
        }
    });
}

// Función para actualizar la cabecera de columnas - REMOVED - INLINED INTO updateTimingTable
/*
function updateColumnsHeader() {
    const headerContainer = document.getElementById('columns-header');
    headerContainer.innerHTML = '';
    headerContainer.style.width = 'fit-content';
    headerContainer.style.minWidth = '100%';

    activeColumns.forEach(column => {
        const colDef = columnDefinitions[column] || {
            name: column,
            width: 2
        };

        const headerColumn = document.createElement('div');
        headerColumn.className = `header-column ${column}`;
        headerColumn.style.width = `${colDef.width * 50}px`;
        headerColumn.style.minWidth = `${colDef.width * 50}px`;
        headerColumn.textContent = colDef.name;

        headerContainer.appendChild(headerColumn);
    });
}
*/

// --- Focused Driver Card ---
let _fdLastCarIdx = null;       // track driver changes for transition
let _fdTimerInterval = null;    // setInterval handle for live lap timer
let _fdLapStartTime = null;     // server sessionTime when current lap started
let _fdServerSessionTime = 0;   // last known server sessionTime
let _fdClientReceiveMs = 0;     // Date.now() when last WS message arrived
let _fdPrevSectorCount = 0;     // detect lap completion (sector count resets)
let _fdPrevBestLap = null;      // driver's best lap before this lap — detect new best
let _fdFlashTimeout = null;     // timeout for lap-end flash removal
let _fdBattleActive = false;    // hysteresis: currently in battle mode
let _fdLastGapAhead = null;     // previous gap ahead for trend arrow
let _fdLastGapBehind = null;    // previous gap behind for trend arrow
let _fdStatIndex = 0;           // current stat rotation index
let _fdStatList  = [];          // all stats from last race render
let _fdStatRotateInterval = null; // setInterval handle for stat rotation
let _fdLastSectorSnapshot = null; // last focusedDriverDetails snapshot with sector data
let _fdFreezeUntilMs = 0;         // Date.now() timestamp when sector freeze expires
const _FD_FREEZE_MS = 3500;       // how long to hold sector display after lap end

function _fdFormatTime(seconds) {
    if (seconds === null || seconds === undefined || isNaN(seconds)) return '--:--.---';
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${s.toFixed(3).padStart(6, '0')}`;
}

function _fdFormatSectorTime(seconds) {
    if (seconds === null || seconds === undefined) return '--';
    return seconds.toFixed(3);
}

function _fdStartLiveTimer() {
    if (_fdTimerInterval) return; // already running
    _fdTimerInterval = setInterval(() => {
        const el = document.getElementById('fd-lap-timer');
        if (!el || _fdLapStartTime === null) return;
        // Compute how much real time has passed since the last WS message
        const clientElapsedSec = (Date.now() - _fdClientReceiveMs) / 1000;
        const elapsed = (_fdServerSessionTime - _fdLapStartTime) + clientElapsedSec;
        el.textContent = _fdFormatTime(Math.max(0, elapsed));
    }, 50);
}

function _fdStopLiveTimer() {
    if (_fdTimerInterval) {
        clearInterval(_fdTimerInterval);
        _fdTimerInterval = null;
    }
}

function _fdFlashLapEnd(lapTimeStr, deltaSeconds) {
    const infoDiv = document.getElementById('focused-driver-info');
    if (!infoDiv) return;
    const sign = deltaSeconds <= 0 ? '' : '+';
    const deltaStr = `${sign}${deltaSeconds.toFixed(3)}`;
    const deltaClass = deltaSeconds <= 0 ? 'fd-flash-purple' : 'fd-flash-red';

    const flash = document.createElement('div');
    flash.className = `fd-lap-flash ${deltaClass}`;
    flash.innerHTML = `<span class="fd-flash-time">${lapTimeStr}</span><span class="fd-flash-delta">${deltaStr}</span>`;
    infoDiv.appendChild(flash);

    if (_fdFlashTimeout) clearTimeout(_fdFlashTimeout);
    _fdFlashTimeout = setTimeout(() => {
        flash.classList.add('fd-flash-fade');
        setTimeout(() => flash.remove(), 600);
    }, 3000);
}

const SECTOR_STATUS_CLASS = ['s-none', 's-gray', 's-green', 's-purple'];

function _fdQualySectorsHTML(focusedDetails, bestSectors) {
    const status = focusedDetails.sectorStatus || [0, 0, 0];
    const times  = focusedDetails.sectorTimes  || [];
    // sectorDeltas from backend: delta computed BEFORE session best was updated, so purple shows real improvement
    const preDeltas = focusedDetails.sectorDeltas || [];
    const pills = status.map((s, i) => {
        const cls = SECTOR_STATUS_CLASS[s] || 's-none';
        const t = times[i] !== undefined ? _fdFormatSectorTime(times[i]) : '';

        let deltaHTML = '';
        if (times[i] !== undefined) {
            // Prefer backend-computed delta (accurate for purple sectors)
            let delta = (preDeltas[i] !== undefined && preDeltas[i] !== null) ? preDeltas[i] : null;
            // Fallback: compute from current session best (will be 0 for purple, but at least shows for green/gray)
            if (delta === null && bestSectors) {
                const best = bestSectors[i] ?? bestSectors[String(i)];
                if (best !== undefined && best !== null) delta = times[i] - best;
            }
            if (delta !== null) {
                const sign = delta >= 0 ? '+' : '';
                const deltaStr = `${sign}${delta.toFixed(3)}`;
                const deltaClass = s === 3 ? 'delta-purple' : (delta > 0 ? 'delta-slow' : 'delta-fast');
                deltaHTML = `<span class="fd-sp-delta ${deltaClass}">${deltaStr}</span>`;
            }
        }

        return `<div class="fd-sector-pill ${cls}"><span class="fd-sp-label">S${i + 1}</span><span class="fd-sp-time">${t}</span>${deltaHTML}</div>`;
    });
    return `<div class="fd-sector-pills">${pills.join('')}</div>`;
}

function _fdHide(infoDiv) {
    infoDiv.classList.remove('fd-visible');
    infoDiv.classList.add('fd-hidden');
}

function _fdShow(infoDiv) {
    infoDiv.classList.remove('fd-hidden');
    infoDiv.classList.add('fd-visible');
}

function _fdContextStats(d) {
    // Context-aware: pick the most relevant stat for this moment
    const stats = [];

    // Just pitted / on out lap
    if (d.onOutLap) {
        if (d.lastPitDuration) stats.push({ label: 'PIT', value: `${parseFloat(d.lastPitDuration).toFixed(1)}s` });
        if (d.tireCompound) stats.push({ label: 'TYRE', value: d.tireCompound });
        return stats;
    }

    // Gap to leader
    const gap = d.gap || d.gapToLeader;
    if (gap && gap !== '-' && gap !== 'Leader') stats.push({ label: 'GAP', value: gap });

    // Interval to car ahead
    if (d.interval && d.interval !== '-') stats.push({ label: 'INT', value: d.interval });

    // Best lap
    if (d.bestLapTime && d.bestLapTime !== '-') stats.push({ label: 'BEST', value: d.bestLapTime });

    // Positions gained
    if (typeof d.positionsGained === 'number' && d.positionsGained !== 0) {
        const val = d.positionsGained > 0 ? `+${d.positionsGained}` : `${d.positionsGained}`;
        stats.push({ label: 'POS', value: val });
    }

    return stats.slice(0, 3);
}

function _fdBattleResult(focusedDriver, drivers) {
    const pos = focusedDriver.position;
    if (!pos || !drivers) return null;

    // Parse gap string — treats lapped cars (contains 'L') as Infinity
    function parseGap(gapStr) {
        if (!gapStr || gapStr === '-' || gapStr === 'Leader') return Infinity;
        if (gapStr.includes('L')) return Infinity;
        return parseFloat(gapStr.replace('+', '')) || Infinity;
    }

    const ENTER = 1.5;
    const EXIT  = 2.2;
    const threshold = _fdBattleActive ? EXIT : ENTER;

    const ahead  = drivers.find(d => d.position === pos - 1);
    const behind = drivers.find(d => d.position === pos + 1);

    const gapAhead  = ahead  ? parseGap(focusedDriver.interval) : Infinity;
    const gapBehind = behind ? parseGap(behind.interval)        : Infinity;

    const inBattleAhead  = gapAhead  <= threshold;
    const inBattleBehind = gapBehind <= threshold;

    if (!inBattleAhead && !inBattleBehind) return null;

    // Count additional chained cars in the train (always use EXIT threshold)
    function countChainAhead(fromCar) {
        let count = 0, cur = fromCar;
        while (true) {
            const next = drivers.find(d => d.position === cur.position - 1);
            if (!next || parseGap(cur.interval) > EXIT) break;
            count++; cur = next;
        }
        return count;
    }
    function countChainBehind(fromPos) {
        let count = 0, p = fromPos;
        while (true) {
            const next = drivers.find(d => d.position === p + 1);
            if (!next || parseGap(next.interval) > EXIT) break;
            count++; p++;
        }
        return count;
    }

    return {
        ahead:        inBattleAhead  ? ahead  : null,
        behind:       inBattleBehind ? behind : null,
        gapAhead,
        gapBehind,
        trainAhead:  inBattleAhead  ? countChainAhead(ahead)      : 0,
        trainBehind: inBattleBehind ? countChainBehind(pos + 1)   : 0,
    };
}

function _fdDriverCardHTML(d, isFocused) {
    const dorsal = d.carNumber || '';
    const dorsalSrc = `/static/dorsales/${dorsal}.png`;
    const pos = d.position || '-';
    const name = d.userName || '-';
    return `
        <div class="fd-card ${isFocused ? 'fd-card-focused' : 'fd-card-opponent'}">
            <img class="fd-dorsal" src="${dorsalSrc}" onerror="this.style.display='none'">
            <div class="fd-card-info">
                <span class="fd-pos">P${pos}</span>
                <span class="fd-name">${name.toUpperCase()}</span>
            </div>
        </div>`;
}

function updateFocusedDriverInfo(focusedDriverDetails, currentSessionData) {
    const infoDiv = document.getElementById('focused-driver-info');
    if (!infoDiv) return;

    const HIDDEN_NAMES = ['Pace Car', 'Jose Carlos Herrero'];
    const shouldHide = !focusedDriverDetails || !currentSessionData || !currentSessionData.drivers
        || HIDDEN_NAMES.some(n => (focusedDriverDetails.userName || '').includes(n));

    if (shouldHide) {
        _fdHide(infoDiv);
        return;
    }

    const drivers = currentSessionData.drivers;
    const d = drivers.find(x => x.carIdx === focusedDriverDetails.carIdx);
    if (!d) { _fdHide(infoDiv); return; }

    // Transition: detect driver change
    const driverChanged = _fdLastCarIdx !== null && _fdLastCarIdx !== focusedDriverDetails.carIdx;
    if (driverChanged) {
        infoDiv.classList.add('fd-transitioning');
        setTimeout(() => infoDiv.classList.remove('fd-transitioning'), 400);
        _fdBattleActive = false;
        _fdLastGapAhead = null;
        _fdLastGapBehind = null;
        clearInterval(_fdStatRotateInterval); _fdStatRotateInterval = null;
        _fdStatIndex = 0; _fdStatList = [];
    }
    _fdLastCarIdx = focusedDriverDetails.carIdx;

    const sessionType = (currentSessionData.sessionType || '').toUpperCase();
    const isRace = sessionType.includes('RACE') || sessionType.includes('GRID');

    // Check for battle/train mode — race only, and only if enabled in config
    const battle = (isRace && focusedDriverBattleMode) ? _fdBattleResult(d, drivers) : null;

    if (battle) {
        _fdBattleActive = true;
        clearInterval(_fdStatRotateInterval); _fdStatRotateInterval = null;

        // Compute gap trend arrows
        function trendArrow(current, last) {
            if (last === null || current === Infinity) return '';
            if (current < last - 0.015) return '<span class="fd-gap-trend closing">▼</span>';
            if (current > last + 0.015) return '<span class="fd-gap-trend opening">▲</span>';
            return '';
        }
        const arrowAhead  = trendArrow(battle.gapAhead,  _fdLastGapAhead);
        const arrowBehind = trendArrow(battle.gapBehind, _fdLastGapBehind);
        if (battle.ahead)  _fdLastGapAhead  = battle.gapAhead;
        if (battle.behind) _fdLastGapBehind = battle.gapBehind;

        const gapAheadStr  = (d.interval && d.interval !== '-') ? d.interval : '---';
        const gapBehindStr = (battle.behind?.interval && battle.behind.interval !== '-') ? battle.behind.interval : '---';

        if (battle.ahead && battle.behind) {
            // ── 3-car train mode ──
            const moreAhead  = battle.trainAhead  > 0 ? `<div class="fd-train-more">+${battle.trainAhead} ahead</div>`  : '';
            const moreBehind = battle.trainBehind > 0 ? `<div class="fd-train-more">+${battle.trainBehind} behind</div>` : '';
            infoDiv.className = 'fd-train fd-visible';
            infoDiv.innerHTML = `
                <div class="fd-train-slot">${moreAhead}${_fdDriverCardHTML(battle.ahead, false)}</div>
                <div class="fd-duel-gap">${gapAheadStr}${arrowAhead}</div>
                ${_fdDriverCardHTML(d, true)}
                <div class="fd-duel-gap">${gapBehindStr}${arrowBehind}</div>
                <div class="fd-train-slot">${_fdDriverCardHTML(battle.behind, false)}${moreBehind}</div>
            `;
        } else {
            // ── 2-car duel mode ──
            const focusedFirst = !!battle.behind;
            const [leftDriver, rightDriver] = focusedFirst ? [d, battle.behind] : [battle.ahead, d];
            const gapStr  = focusedFirst ? gapBehindStr : gapAheadStr;
            const arrow   = focusedFirst ? arrowBehind  : arrowAhead;
            infoDiv.className = 'fd-duel fd-visible';
            infoDiv.innerHTML = `
                ${_fdDriverCardHTML(leftDriver,  leftDriver.carIdx  === d.carIdx)}
                <div class="fd-duel-gap">${gapStr}${arrow}</div>
                ${_fdDriverCardHTML(rightDriver, rightDriver.carIdx === d.carIdx)}
            `;
        }
    } else {
        _fdBattleActive = false;
        _fdLastGapAhead = null;
        _fdLastGapBehind = null;
        const dorsal = d.carNumber || '';
        const dorsalSrc = `/static/dorsales/${dorsal}.png`;
        const isQualy = !isRace;

        if (isQualy) {
            // --- Qualifying mode ---
            clearInterval(_fdStatRotateInterval); _fdStatRotateInterval = null;
            const newSectorCount = (focusedDriverDetails.sectorTimes || []).length;

            // Keep a rolling snapshot of the last tick that had sector data
            if (newSectorCount > 0) {
                _fdLastSectorSnapshot = { ...focusedDriverDetails };
            }

            // Detect lap completion: sector count resets to 0 after having sectors
            if (_fdPrevSectorCount > 0 && newSectorCount === 0 && d.bestLapTime && d.bestLapTime !== '-') {
                // Freeze the last known sector state for a few seconds
                _fdFreezeUntilMs = Date.now() + _FD_FREEZE_MS;

                // Find session best lap across all drivers
                const sessionBestSec = currentSessionData.drivers.reduce((best, drv) => {
                    if (drv.bestLapSeconds && drv.bestLapSeconds > 0) return Math.min(best, drv.bestLapSeconds);
                    return best;
                }, Infinity);
                const thisBestSec = d.bestLapSeconds;
                if (thisBestSec && sessionBestSec < Infinity) {
                    const delta = thisBestSec - sessionBestSec;
                    _fdFlashLapEnd(d.bestLapTime, delta);
                }
            }
            _fdPrevSectorCount = newSectorCount;

            // Use frozen snapshot if within freeze window, otherwise live data
            const isFrozen = Date.now() < _fdFreezeUntilMs;
            const sectorsSource = (isFrozen && _fdLastSectorSnapshot) ? _fdLastSectorSnapshot : focusedDriverDetails;

            const inPits   = !!d.onPitRoad;
            const onOutLap = !!d.onOutLap;
            const timerStopped = inPits || onOutLap;

            // Update lapStartTime for live timer (only on a normal timed lap)
            if (!timerStopped) {
                _fdLapStartTime = focusedDriverDetails.lapStartTime || null;
            } else {
                _fdStopLiveTimer();
                _fdLapStartTime = null;
            }

            const timerLabel = inPits ? 'PIT' : onOutLap ? 'OUT LAP' : '--:--.---';

            infoDiv.className = 'fd-qualy fd-visible';
            infoDiv.innerHTML = `
                <img class="fd-dorsal" src="${dorsalSrc}" onerror="this.style.display='none'">
                <div class="fd-main">
                    <span class="fd-pos">P${d.position || '-'}</span>
                    <span class="fd-name">${(d.userName || '').toUpperCase()}</span>
                    <span class="fd-best-lap">${d.bestLapTime || '--:--.---'}</span>
                </div>
                <div class="fd-qualy-right">
                    <span class="fd-lap-timer" id="fd-lap-timer">${timerLabel}</span>
                    <div class="fd-qualy-divider"></div>
                    ${_fdQualySectorsHTML(sectorsSource, currentSessionData.sessionBestSectors)}
                </div>
            `;
            if (!timerStopped) {
                // Immediately paint the correct elapsed time so there's no --:--.--- flash
                const _timerEl = document.getElementById('fd-lap-timer');
                if (_timerEl && _fdLapStartTime !== null) {
                    const _clientElapsed = (Date.now() - _fdClientReceiveMs) / 1000;
                    _timerEl.textContent = _fdFormatTime(Math.max(0, (_fdServerSessionTime - _fdLapStartTime) + _clientElapsed));
                }
                _fdStartLiveTimer();
            }
        } else {
            // --- Race mode ---
            _fdStopLiveTimer();
            _fdLapStartTime = null;
            _fdPrevSectorCount = 0;

            // Update stat list — if list changed length, reset index
            const newStats = _fdContextStats(d);
            if (newStats.length !== _fdStatList.length) {
                _fdStatIndex = 0;
                clearInterval(_fdStatRotateInterval); _fdStatRotateInterval = null;
            }
            _fdStatList = newStats;
            if (_fdStatIndex >= _fdStatList.length) _fdStatIndex = 0;

            function _statSlotHTML(idx) {
                const s = _fdStatList[idx];
                if (!s) return '';
                return `<div class="fd-stat fd-stat-fade">
                    <span class="fd-stat-label">${s.label}</span>
                    <span class="fd-stat-value">${s.value}</span>
                </div>`;
            }

            infoDiv.className = 'fd-single fd-visible';
            infoDiv.innerHTML = `
                <img class="fd-dorsal" src="${dorsalSrc}" onerror="this.style.display='none'">
                <div class="fd-main">
                    <span class="fd-pos">P${d.position || '-'}</span>
                    <span class="fd-name">${(d.userName || '').toUpperCase()}</span>
                </div>
                <div class="fd-stats" id="fd-stat-slot">${_statSlotHTML(_fdStatIndex)}</div>
            `;

            // Start rotation interval if more than one stat and not already running
            if (_fdStatList.length > 1 && !_fdStatRotateInterval) {
                _fdStatRotateInterval = setInterval(() => {
                    _fdStatIndex = (_fdStatIndex + 1) % _fdStatList.length;
                    const slot = document.getElementById('fd-stat-slot');
                    if (slot) slot.innerHTML = _statSlotHTML(_fdStatIndex);
                }, 5000);
            }
        }
    }

    _fdShow(infoDiv);
}

// ── Live indicator flag state ──────────────────────────────────────────────
const _FLAG_YELLOW         = 0x0008;
const _FLAG_CAUTION        = 0x4000;
const _FLAG_CAUTION_WAVING = 0x8000;

function updateLiveIndicator(flags) {
    const indicator = document.querySelector('.live-indicator');
    const textEl    = indicator ? indicator.querySelector('span:last-child') : null;
    if (!indicator || !textEl) return;

    const isSC     = !!(flags & (_FLAG_CAUTION | _FLAG_CAUTION_WAVING));
    const isYellow = !isSC && !!(flags & _FLAG_YELLOW);

    indicator.classList.remove('flag-yellow', 'flag-sc');

    if (isSC) {
        indicator.classList.add('flag-sc');
        textEl.textContent = 'SAFETY CAR';
    } else if (isYellow) {
        indicator.classList.add('flag-yellow');
        textEl.textContent = 'AMARILLA';
    } else {
        textEl.textContent = 'DIRECTO';
    }
}

// Actualizar información de la sesión
function updateSessionInfo(data) {
    document.getElementById('session-name').textContent = data.sessionName || 'CLASIFICACIÓN 1ª DIVISIÓN';
    // document.getElementById('track-name').textContent = `${data.trackName}${data.trackConfig ? ' - ' + data.trackConfig : ''}`;

    // Mostrar vueltas o tiempo según el tipo de sesión
    const sessionTimeElement = document.getElementById('session-time');
    const sessionTypeUpper = data.sessionType ? data.sessionType.toUpperCase() : 'UNKNOWN';
    const timeRemaining = data.sessionTimeRemaining;
    const lapsTotal = data.sessionLapsTotal; // Can be 0 or -1 for unlimited/timed
    const lapsRemaining = data.sessionLapsRemaining;

    console.log("Session Type:", sessionTypeUpper);
    console.log("Time Remaining:", timeRemaining);
    console.log("Laps Total:", lapsTotal);
    console.log("Laps Remaining:", lapsRemaining);

    // 1. Handle Practice (ONLY show time)
    if (sessionTypeUpper.includes("PRACTICE")) {
        if (timeRemaining !== undefined && timeRemaining !== null && timeRemaining >= 0) {
            const hours = Math.floor(timeRemaining / 3600);
            const minutes = Math.floor((timeRemaining % 3600) / 60);
            const seconds = Math.floor(timeRemaining % 60);
            if (hours > 0) {
                sessionTimeElement.textContent = `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
            } else {
                sessionTimeElement.textContent = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
            }
        } else {
            sessionTimeElement.textContent = '--:--'; // Fallback if time is not available
        }
    }
    // 2. Handle Qualifying (Also show time)
    else if (sessionTypeUpper.includes("QUALIFY")) {
        if (timeRemaining !== undefined && timeRemaining !== null && timeRemaining >= 0) {
            const hours = Math.floor(timeRemaining / 3600);
            const minutes = Math.floor((timeRemaining % 3600) / 60);
            const seconds = Math.floor(timeRemaining % 60);
            if (hours > 0) {
                sessionTimeElement.textContent = `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
            } else {
                sessionTimeElement.textContent = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
            }
        } else {
            sessionTimeElement.textContent = '--:--'; // Fallback if time is not available
        }
    }
    // 3. Handle Lap-based Race (lapsTotal is a positive number)
    else if (lapsTotal > 0) {
        let currentLap = 0;
        // Try to get the leader's lap if available
        if (data.drivers && data.drivers.length > 0) {
            const leader = data.drivers.find(d => d.position === 1);
            if (leader && leader.lapsComplete !== undefined) {
                currentLap = leader.lapsComplete + 1; // Show current lap leader is on
            } else if (lapsRemaining !== undefined && lapsRemaining !== null) {
                currentLap = lapsTotal - lapsRemaining; // Calculate based on remaining if leader info missing
            }
            // Ensure currentLap doesn't exceed total laps or go below 1
            currentLap = Math.min(Math.max(1, currentLap), lapsTotal);
        } else if (lapsRemaining !== undefined && lapsRemaining !== null) {
            // Fallback if no driver data but laps remaining exists
            currentLap = lapsTotal - lapsRemaining;
            currentLap = Math.min(Math.max(1, currentLap), lapsTotal);
        } else {
            currentLap = '?'; // Fallback if no info
        }
        sessionTimeElement.textContent = `${currentLap}/${lapsTotal}`;
    }
    // 4. Handle Time-based Race or Unknown (lapsTotal is 0, -1 or undefined) - Show time as fallback
    else {
        if (timeRemaining !== undefined && timeRemaining !== null && timeRemaining >= 0) {
            const hours = Math.floor(timeRemaining / 3600);
            const minutes = Math.floor((timeRemaining % 3600) / 60);
            const seconds = Math.floor(timeRemaining % 60);
            if (hours > 0) {
                sessionTimeElement.textContent = `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
            } else {
                sessionTimeElement.textContent = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
            }
        } else {
            sessionTimeElement.textContent = '--:--'; // Default fallback if no time and not lap race
        }
    }
}
function formatSectorDelta(rawTime, sectorIndex, precomputedDelta) {
    const sectorName = 'S' + (sectorIndex + 1);

    // Use pre-computed delta from backend if provided (accurate for session best setters)
    if (precomputedDelta !== undefined && precomputedDelta !== null) {
        const sign = precomputedDelta >= 0 ? '+' : '';
        return `${sectorName} ${sign}${precomputedDelta.toFixed(2)}`;
    }

    // Fallback: compute client-side (for recalculation of visible popups)
    const sessionBest = currentSessionBestSectors[sectorIndex];
    if (sessionBest !== undefined && sessionBest !== null && rawTime !== null) {
        const delta = rawTime - sessionBest;
        const sign = delta >= 0 ? '+' : '';
        return `${sectorName} ${sign}${delta.toFixed(2)}`;
    }
    // No session best yet — show raw time
    return `${sectorName} ${rawTime.toFixed(2)}`;
}

function showSectorSlider(driverElement, driverData, sectorText) {
    // 1. Si ya hay uno, lo quitamos (limpieza rápida)
    const existingPopup = driverElement.querySelector('.sector-popover');
    if (existingPopup) {
        existingPopup.remove();
    }

    // 2. Crear el elemento (Empieza invisible por CSS)
    const popup = document.createElement('div');
    popup.className = 'sector-popover';

    // 3. Compute delta text if we have raw data
    const rawTime = driverData.lastSectorRawTime;
    const sectorIdx = driverData.lastSectorIndex;
    const precomputedDelta = driverData.lastSectorDelta;

    if (rawTime !== null && rawTime !== undefined && sectorIdx !== null && sectorIdx !== undefined) {
        popup.textContent = formatSectorDelta(rawTime, sectorIdx, precomputedDelta);
        // Store raw data for recalculation
        popup.setAttribute('data-raw-time', rawTime);
        popup.setAttribute('data-sector-index', sectorIdx);
    } else {
        popup.textContent = sectorText;
    }

    // 4. Determinar color
    let colorClass = 'pop-gray';
    if (driverData.sectors && Array.isArray(driverData.sectors)) {
        let sectorIndex = -1;
        if (sectorText.startsWith("S1")) sectorIndex = 0;
        else if (sectorText.startsWith("S2")) sectorIndex = 1;
        else if (sectorText.startsWith("Last") || sectorText.startsWith("S3")) sectorIndex = 2;

        if (sectorIndex >= 0 && driverData.sectors[sectorIndex] !== undefined) {
            const status = driverData.sectors[sectorIndex];
            if (status === 2) colorClass = 'pop-green';
            if (status === 3) colorClass = 'pop-purple';
        }
    }
    popup.classList.add(colorClass);

    // 5. Añadir al DOM
    driverElement.appendChild(popup);

    // 6. ANIMACIÓN DE ENTRADA
    requestAnimationFrame(() => {
        popup.classList.add('visible');
    });

    // 7. ANIMACIÓN DE SALIDA (A los 4 segundos)
    setTimeout(() => {
        if (driverElement.contains(popup)) {
            popup.classList.remove('visible');
            setTimeout(() => {
                if (driverElement.contains(popup)) {
                    popup.remove();
                }
            }, 500);
        }
    }, 4000);
}

function recalculateVisiblePopups() {
    // Find all currently visible sector popovers and recalculate their delta text
    const popups = document.querySelectorAll('.sector-popover');
    for (const popup of popups) {
        const rawTime = parseFloat(popup.getAttribute('data-raw-time'));
        const sectorIdx = parseInt(popup.getAttribute('data-sector-index'));
        if (!isNaN(rawTime) && !isNaN(sectorIdx)) {
            popup.textContent = formatSectorDelta(rawTime, sectorIdx);
        }
    }
}