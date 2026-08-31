document.addEventListener('DOMContentLoaded', function () {
    const podiumEl = document.getElementById('results-podium');
    const listEl = document.getElementById('results-list');
    const trackNameEl = document.getElementById('track-name');
    let liveDataReceived = false;
    const FETCH_INTERVAL = 30000; // Poll every 30 seconds

    // Mock data for preview
    const MOCK_DATA = {
        trackName: "Spa-Francorchamps",
        trackConfig: "Grand Prix",
        drivers: [
            { carNumber: "44", userName: "M. VERSTAPPEN", startPosition: 3, position: 1, gap: "WINNER", bestLapTime: "2:01.432", lapsComplete: 44, isFastestLap: false, positionsGained: 2 },
            { carNumber: "11", userName: "L. HAMILTON", startPosition: 1, position: 2, gap: "+3.241", bestLapTime: "2:01.876", lapsComplete: 44, isFastestLap: false, positionsGained: -1 },
            { carNumber: "16", userName: "C. LECLERC", startPosition: 2, position: 3, gap: "+7.502", bestLapTime: "2:01.104", lapsComplete: 44, isFastestLap: true, positionsGained: -1 },
            { carNumber: "4",  userName: "L. NORRIS", startPosition: 5, position: 4, gap: "+12.887", bestLapTime: "2:02.115", lapsComplete: 44, isFastestLap: false, positionsGained: 1 },
            { carNumber: "81", userName: "O. PIASTRI", startPosition: 4, position: 5, gap: "+18.334", bestLapTime: "2:02.450", lapsComplete: 44, isFastestLap: false, positionsGained: -1 },
            { carNumber: "55", userName: "C. SAINZ", startPosition: 7, position: 6, gap: "+22.108", bestLapTime: "2:02.773", lapsComplete: 44, isFastestLap: false, positionsGained: 1 },
            { carNumber: "63", userName: "G. RUSSELL", startPosition: 6, position: 7, gap: "+28.991", bestLapTime: "2:02.890", lapsComplete: 44, isFastestLap: false, positionsGained: -1 },
            { carNumber: "14", userName: "F. ALONSO", startPosition: 8, position: 8, gap: "+34.552", bestLapTime: "2:03.102", lapsComplete: 44, isFastestLap: false, positionsGained: 0 },
            { carNumber: "18", userName: "L. STROLL", startPosition: 10, position: 9, gap: "+41.220", bestLapTime: "2:03.344", lapsComplete: 44, isFastestLap: false, positionsGained: 1 },
            { carNumber: "10", userName: "P. GASLY", startPosition: 9, position: 10, gap: "+45.678", bestLapTime: "2:03.501", lapsComplete: 44, isFastestLap: false, positionsGained: -1 },
            { carNumber: "31", userName: "E. OCON", startPosition: 12, position: 11, gap: "+52.113", bestLapTime: "2:03.670", lapsComplete: 44, isFastestLap: false, positionsGained: 1 },
            { carNumber: "3",  userName: "D. RICCIARDO", startPosition: 11, position: 12, gap: "+55.892", bestLapTime: "2:03.812", lapsComplete: 44, isFastestLap: false, positionsGained: -1 },
            { carNumber: "22", userName: "Y. TSUNODA", startPosition: 14, position: 13, gap: "+1:01.334", bestLapTime: "2:04.001", lapsComplete: 44, isFastestLap: false, positionsGained: 1 },
            { carNumber: "77", userName: "V. BOTTAS", startPosition: 13, position: 14, gap: "+1:05.778", bestLapTime: "2:04.150", lapsComplete: 44, isFastestLap: false, positionsGained: -1 },
            { carNumber: "24", userName: "Z. GUANYU", startPosition: 16, position: 15, gap: "+1 Lap", bestLapTime: "2:04.556", lapsComplete: 43, isFastestLap: false, positionsGained: 1 },
            { carNumber: "27", userName: "N. HULKENBERG", startPosition: 15, position: 16, gap: "+1 Lap", bestLapTime: "2:04.701", lapsComplete: 43, isFastestLap: false, positionsGained: -1 },
            { carNumber: "20", userName: "K. MAGNUSSEN", startPosition: 18, position: 17, gap: "+1 Lap", bestLapTime: "2:04.889", lapsComplete: 43, isFastestLap: false, positionsGained: 1 },
            { carNumber: "23", userName: "A. ALBON", startPosition: 17, position: 18, gap: "+1 Lap", bestLapTime: "2:05.012", lapsComplete: 43, isFastestLap: false, positionsGained: -1 },
            { carNumber: "2",  userName: "L. SARGEANT", startPosition: 19, position: 19, gap: "+2 Laps", bestLapTime: "2:05.445", lapsComplete: 42, isFastestLap: false, positionsGained: 0 },
            { carNumber: "21", userName: "N. DE VRIES", startPosition: 20, position: 20, gap: "DNF", bestLapTime: "2:05.890", lapsComplete: 31, isFastestLap: false, positionsGained: 0 }
        ]
    };

    async function fetchResultsData() {
        try {
            const resp = await fetch('/api/session-results?session=race');
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const data = await resp.json();
            if (data.error || !data.drivers || data.drivers.length === 0) throw new Error(data.error || 'No drivers');
            liveDataReceived = true;
            renderResults(data);
        } catch (e) {
            console.warn('Results fetch failed:', e.message);
            if (!liveDataReceived) {
                renderResults(MOCK_DATA);
            }
        }
    }

    // Initial fetch, then poll
    fetchResultsData();
    setInterval(fetchResultsData, FETCH_INTERVAL);

    function renderResults(data) {
        // Track name
        if (data.trackName) {
            let label = data.trackName;
            if (data.trackConfig) label += ' - ' + data.trackConfig;
            trackNameEl.textContent = label;
        }

        // Sort by position
        const drivers = [...data.drivers].filter(d => d.carNumber);
        drivers.sort((a, b) => {
            const pa = a.position || 999;
            const pb = b.position || 999;
            return pa - pb;
        });

        // Clear
        podiumEl.innerHTML = '';
        listEl.innerHTML = '';

        // PODIUM (top 3)
        const top3 = drivers.slice(0, 3);
        for (let i = 0; i < top3.length; i++) {
            const pos = i + 1;
            podiumEl.appendChild(createPodiumBlock(top3[i], pos));
        }

        // RESULTS LIST (P4+)
        if (drivers.length > 3) {
            const divider = document.createElement('div');
            divider.className = 'results-list-divider';
            listEl.appendChild(divider);

            const rest = drivers.slice(3);
            for (let i = 0; i < rest.length; i++) {
                const pos = i + 4;
                const row = createResultRow(rest[i], pos);
                // Staggered animation: starts after podium finishes (~1.2s)
                row.style.setProperty('--delay', (1.2 + i * 0.1) + 's');
                listEl.appendChild(row);
            }
        }
    }

    function createPodiumBlock(driver, pos) {
        const block = document.createElement('div');
        block.className = 'podium-block podium-' + pos;

        // Position
        const posEl = document.createElement('div');
        posEl.className = 'podium-pos';
        posEl.textContent = pos;
        block.appendChild(posEl);

        // Dorsal
        const img = document.createElement('img');
        img.className = 'podium-dorsal';
        img.src = `/static/dorsales/${driver.carNumber}.png`;
        img.onerror = function () { this.src = '/static/dorsales/default.png'; };
        block.appendChild(img);

        // Car number
        const numEl = document.createElement('div');
        numEl.className = 'podium-number';
        numEl.textContent = '#' + driver.carNumber;
        block.appendChild(numEl);

        // Driver name
        const nameEl = document.createElement('div');
        nameEl.className = 'podium-name';
        nameEl.textContent = driver.userName || driver.fullName || 'Unknown';
        block.appendChild(nameEl);

        // Gap / time
        const gapEl = document.createElement('div');
        gapEl.className = 'podium-gap';
        if (pos === 1) {
            gapEl.textContent = driver.gap === 'WINNER' ? 'WINNER' : (driver.gap || 'P1');
        } else {
            gapEl.textContent = driver.gap || '-';
        }
        block.appendChild(gapEl);

        // Base step
        const base = document.createElement('div');
        base.className = 'podium-base';
        block.appendChild(base);

        return block;
    }

    function createResultRow(driver, pos) {
        const row = document.createElement('div');
        row.className = 'result-row';

        // Position
        const posEl = document.createElement('div');
        posEl.className = 'row-pos';
        posEl.textContent = pos;
        row.appendChild(posEl);

        // Dorsal
        const img = document.createElement('img');
        img.className = 'row-dorsal';
        img.src = `/static/dorsales/${driver.carNumber}.png`;
        img.onerror = function () { this.src = '/static/dorsales/default.png'; };
        row.appendChild(img);

        // Car number
        const numEl = document.createElement('div');
        numEl.className = 'row-number';
        numEl.textContent = '#' + driver.carNumber;
        row.appendChild(numEl);

        // Name
        const nameEl = document.createElement('div');
        nameEl.className = 'row-name';
        nameEl.textContent = driver.userName || driver.fullName || 'Unknown';
        row.appendChild(nameEl);

        // Gap
        const gapEl = document.createElement('div');
        gapEl.className = 'row-gap';
        gapEl.textContent = driver.gap || '-';
        row.appendChild(gapEl);

        // Positions gained
        const gainedEl = document.createElement('div');
        gainedEl.className = 'row-gained';
        const diff = driver.positionsGained || 0;
        if (diff > 0) {
            gainedEl.textContent = '+' + diff;
            gainedEl.classList.add('gained-up');
        } else if (diff < 0) {
            gainedEl.textContent = '' + diff;
            gainedEl.classList.add('gained-down');
        } else {
            gainedEl.textContent = '=';
            gainedEl.classList.add('gained-same');
        }
        row.appendChild(gainedEl);

        // Best lap
        const lapEl = document.createElement('div');
        lapEl.className = 'row-bestlap';
        lapEl.textContent = driver.bestLapTime || '-';
        if (driver.isFastestLap) {
            lapEl.classList.add('is-fastest');
        }
        row.appendChild(lapEl);

        return row;
    }
});
