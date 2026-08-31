// static/results_loader.js

document.addEventListener('DOMContentLoaded', function() {
    
    function fetchRaceResults() {
        fetch('/static/race_mockup.json')
            .then(response => {
                if (!response.ok) {
                    throw new Error(`Error al cargar el archivo JSON: ${response.statusText}`);
                }
                return response.json();
            })
            .then(data => {
                if (!data || !data.results) {
                    console.error("Datos de resultados no válidos en el archivo JSON.");
                    return;
                }

                // Rellenar datos del header
                document.getElementById('results-series').textContent = data.series;
                document.getElementById('results-round').textContent = data.round;

                const tableBody = document.getElementById('results-table-body');
                tableBody.innerHTML = ''; // Limpiar contenido previo

                // Recorrer TODOS los resultados y crear una fila para cada uno
                data.results.forEach(result => {
                    const row = document.createElement('div');
                    row.className = 'result-row';
                    row.setAttribute('data-position', result.position);

                    const timeOrGap = result.position === 1 ? result.time : result.gap;
                    const fastestLapIcon = result.isFastestLapOfAll ? '<i class="fas fa-stopwatch fastest-lap-icon"></i>' : '';

                    // Añadimos el div para el logo del equipo
                    row.innerHTML = `
                        <div class="result-pos">${result.position}</div>
                        <div class="result-logo">
                            <img src="${result.teamLogoUrl}" alt="${result.teamName} Logo">
                        </div>
                        <div class="result-driver">
                            <span class="driver-name">${result.driverName}</span>
                            <span class="team-name">${result.teamName}</span>
                        </div>
                        <div class="result-car">${result.car}</div>
                        <div class="result-time">${timeOrGap}</div>
                        <div class="result-fastest">${result.fastestLap} ${fastestLapIcon}</div>
                    `;
                    
                    tableBody.appendChild(row);
                });
            })
            .catch(error => console.error('Error al procesar los resultados:', error));
    }

    // Iniciar la carga de datos
    fetchRaceResults();
});