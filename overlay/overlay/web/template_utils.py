import os
import logging

logger = logging.getLogger("iracing-timing")

def ensure_template_directory(template_dir):
    """Ensure the templates directory exists."""
    if not os.path.exists(template_dir):
        os.makedirs(template_dir)
        logger.info(f"Created templates directory: {template_dir}")

def create_html_template(template_path):
    """Create the HTML template for the web interface."""

    # Only create the template if it doesn't exist
    if not os.path.exists(template_path):
        with open(template_path, 'w', encoding="utf-8") as f:
            f.write('''
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>iRacing Timing Tower</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.2.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body {
            background-color: #121212;
            color: #f0f0f0;
            font-family: 'Roboto', sans-serif;
            padding: 20px;
        }
        .timing-tower {
            background-color: rgba(30, 30, 30, 0.9);
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.5);
            margin-bottom: 20px;
        }
        .timing-header {
            background-color: #333;
            padding: 10px;
            font-weight: bold;
            border-bottom: 2px solid #555;
        }
        .timing-row {
            padding: 8px 10px;
            border-bottom: 1px solid #444;
            transition: background-color 0.3s;
        }
        .timing-row:hover {
            background-color: #3a3a3a;
        }
        .position-1 {
            background-color: rgba(255, 215, 0, 0.2);
        }
        .position-2 {
            background-color: rgba(192, 192, 192, 0.2);
        }
        .position-3 {
            background-color: rgba(205, 127, 50, 0.2);
        }
        .session-info {
            background-color: rgba(30, 30, 30, 0.9);
            border-radius: 10px;
            padding: 15px;
            margin-bottom: 20px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.5);
        }
        .session-timer {
            font-size: 1.5rem;
            font-weight: bold;
            color: #ff4d4d;
        }
        .column-selector {
            background-color: rgba(30, 30, 30, 0.9);
            border-radius: 10px;
            padding: 15px;
            margin-bottom: 20px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.5);
        }
        .form-check-input:checked {
            background-color: #1e88e5;
            border-color: #1e88e5;
        }
        .debug-info {
            background-color: rgba(30, 30, 30, 0.9);
            border-radius: 10px;
            padding: 15px;
            margin-top: 20px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.5);
            font-family: monospace;
            max-height: 300px;
            overflow-y: auto;
        }
        .connection-status {
            display: inline-block;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            margin-right: 8px;
        }
        .connected {
            background-color: #4CAF50;
        }
        .disconnected {
            background-color: #F44336;
        }
    </style>
</head>
<body>
    <div class="container-fluid">
        <div class="row">
            <div class="col-md-8">
                <h1>iRacing Timing Tower</h1>
                <div class="session-info">
                    <div class="row">
                        <div class="col-md-6">
                            <h4 id="session-name">Esperando datos...</h4>
                            <p id="track-name"></p>
                            <p>
                                <span class="connection-status disconnected" id="connection-indicator"></span>
                                <span id="connection-status">Desconectado</span>
                            </p>
                        </div>
                        <div class="col-md-6 text-end">
                            <div class="session-timer" id="session-time">--:--</div>
                            <p id="session-laps"></p>
                        </div>
                    </div>
                </div>
                
                <div class="timing-tower">
                    <div class="timing-header">
                        <div class="row" id="timing-header-row">
                            <!-- Los encabezados de las columnas se generarán con JavaScript -->
                        </div>
                    </div>
                    <div id="timing-rows">
                        <!-- Las filas de datos se generarán con JavaScript -->
                    </div>
                </div>
            </div>
            
            <div class="col-md-4">
                <div class="column-selector">
                    <h4>Configurar Columnas</h4>
                    <p>Selecciona las columnas que quieres mostrar:</p>
                    <div id="column-checkboxes">
                        <!-- Las casillas de verificación se generarán con JavaScript -->
                    </div>
                    <button class="btn btn-primary mt-3" id="apply-columns">Aplicar Cambios</button>
                </div>
                
                <div class="debug-info">
                    <h4>Información de Depuración</h4>
                    <pre id="debug-json">Esperando datos...</pre>
                </div>
            </div>
        </div>
    </div>

    <script>
        // Definiciones de columnas y traducciones
        const columnDefinitions = {
            position: { name: "Pos", width: 1 },
            carNumber: { name: "Nº", width: 1 },
            userName: { name: "Piloto", width: 3 },
            teamName: { name: "Equipo", width: 3 },
            carName: { name: "Coche", width: 2 },
            bestLapTime: { name: "Mejor Vuelta", width: 2 },
            lastLapTime: { name: "Última Vuelta", width: 2 },
            lapsComplete: { name: "Vueltas", width: 1 },
            interval: { name: "Intervalo", width: 2 },
            gap: { name: "Gap", width: 2 },
            pitstops: { name: "Pitstops", width: 1 },
            iRating: { name: "iRating", width: 1 }
        };

        // Variables de estado
        let activeColumns = [];
        let lastUpdate = 0;
        let sessionData = null;
        let updateInterval;

        // Inicializar la página
        document.addEventListener('DOMContentLoaded', function() {
            // Generar casillas de verificación para las columnas
            generateColumnCheckboxes();
            
            // Iniciar la actualización de datos
            updateInterval = setInterval(fetchTimingData, 1000);
            
            // Configurar el botón de aplicar cambios
            document.getElementById('apply-columns').addEventListener('click', applyColumnChanges);
        });

        // Generar casillas de verificación para las columnas
        function generateColumnCheckboxes() {
            const container = document.getElementById('column-checkboxes');
            const availableColumns = {{ columns|tojson }};
            activeColumns = {{ active_columns|tojson }};
            
            availableColumns.forEach(column => {
                const div = document.createElement('div');
                div.className = 'form-check';
                
                const input = document.createElement('input');
                input.className = 'form-check-input';
                input.type = 'checkbox';
                input.id = `column-${column}`;
                input.value = column;
                input.checked = activeColumns.includes(column);
                
                const label = document.createElement('label');
                label.className = 'form-check-label';
                label.htmlFor = `column-${column}`;
                label.textContent = columnDefinitions[column]?.name || column;
                
                div.appendChild(input);
                div.appendChild(label);
                container.appendChild(div);
            });
        }

        // Aplicar cambios de columnas
        function applyColumnChanges() {
            const checkboxes = document.querySelectorAll('#column-checkboxes input[type="checkbox"]:checked');
            const newColumns = Array.from(checkboxes).map(cb => cb.value);
            
            if (newColumns.length === 0) {
                alert("Debes seleccionar al menos una columna.");
                return;
            }
            
            // Enviar selección al servidor
            fetch('/api/update-columns', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ columns: newColumns }),
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    activeColumns = data.activeColumns;
                    if (sessionData) {
                        updateTimingTable(sessionData);
                    }
                }
            });
        }

        // Obtener datos de timing del servidor
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
                    
                    sessionData = data;
                    
                    // Actualizar solo si hay nuevos datos (timestamp diferente)
                    if (data.timestamp !== lastUpdate) {
                        lastUpdate = data.timestamp;
                        updateTimingTable(data);
                        updateSessionInfo(data);
                        document.getElementById('connection-status').textContent = 'Conectado';
                        document.getElementById('connection-indicator').className = 'connection-status connected';
                    }
                    
                    // Actualizar información de depuración
                    document.getElementById('debug-json').textContent = JSON.stringify(data, null, 2);
                })
                .catch(error => console.error('Error:', error));
        }

        // Actualizar la tabla de timing
        function updateTimingTable(data) {
            // Generar encabezados
            const headerRow = document.getElementById('timing-header-row');
            headerRow.innerHTML = '';
            
            activeColumns.forEach(column => {
                const colDef = columnDefinitions[column] || { name: column, width: 2 };
                const div = document.createElement('div');
                div.className = `col-${colDef.width}`;
                div.textContent = colDef.name;
                headerRow.appendChild(div);
            });
            
            // Generar filas
            const rowsContainer = document.getElementById('timing-rows');
            rowsContainer.innerHTML = '';
            
            data.drivers.forEach(driver => {
                const row = document.createElement('div');
                row.className = `timing-row position-${driver.position}`;
                
                const rowContent = document.createElement('div');
                rowContent.className = 'row';
                
                activeColumns.forEach(column => {
                    const colDef = columnDefinitions[column] || { name: column, width: 2 };
                    const div = document.createElement('div');
                    div.className = `col-${colDef.width}`;
                    div.textContent = driver[column] !== undefined ? driver[column] : '-';
                    rowContent.appendChild(div);
                });
                
                row.appendChild(rowContent);
                rowsContainer.appendChild(row);
            });
        }

        // Actualizar información de la sesión
        function updateSessionInfo(data) {
            document.getElementById('session-name').textContent = data.sessionName || 'Sesión Desconocida';
            document.getElementById('track-name').textContent = `${data.trackName}${data.trackConfig ? ' - ' + data.trackConfig : ''}`;
            
            // Formatear tiempo restante de sesión
            const timeRemaining = data.sessionTimeRemaining;
            if (timeRemaining !== undefined) {
                const minutes = Math.floor(timeRemaining / 60);
                const seconds = Math.floor(timeRemaining % 60);
                document.getElementById('session-time').textContent = `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
            } else {
                document.getElementById('session-time').textContent = '--:--';
            }
            
            // Mostrar información de vueltas si está disponible
            const lapsInfo = [];
            if (data.sessionLapsTotal > 0) {
                lapsInfo.push(`Vueltas totales: ${data.sessionLapsTotal}`);
            }
            if (data.sessionLapsRemaining > 0) {
                lapsInfo.push(`Vueltas restantes: ${data.sessionLapsRemaining}`);
            }
            document.getElementById('session-laps').textContent = lapsInfo.join(' - ');
        }
    </script>
</body>
</html>
                ''')
        logger.info(f"Created HTML template: {template_path}")
