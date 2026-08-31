document.addEventListener('DOMContentLoaded', function () {
    const gridBody = document.getElementById('grid-body');
    const trackNameEl = document.getElementById('track-name');
    let liveDataReceived = false;
    let lastRenderTime = 0;
    const RENDER_INTERVAL = 60000; // Update grid every 60 seconds
    const FETCH_INTERVAL = 60000; // Poll every 60 seconds

    // Mock data for preview when no iRacing connection
    const MOCK_DATA = {
        trackName: "Spa-Francorchamps",
        trackConfig: "Grand Prix",
        drivers: [
            { carNumber: "44", userName: "M. VERSTAPPEN", position: 1 },
            { carNumber: "11", userName: "L. HAMILTON", position: 2 },
            { carNumber: "16", userName: "C. LECLERC", position: 3 },
            { carNumber: "4",  userName: "L. NORRIS", position: 4 },
            { carNumber: "81", userName: "O. PIASTRI", position: 5 },
            { carNumber: "55", userName: "C. SAINZ", position: 6 },
            { carNumber: "63", userName: "G. RUSSELL", position: 7 },
            { carNumber: "14", userName: "F. ALONSO", position: 8 },
            { carNumber: "18", userName: "L. STROLL", position: 9 },
            { carNumber: "10", userName: "P. GASLY", position: 10 },
            { carNumber: "31", userName: "E. OCON", position: 11 },
            { carNumber: "3",  userName: "D. RICCIARDO", position: 12 },
            { carNumber: "22", userName: "Y. TSUNODA", position: 13 },
            { carNumber: "77", userName: "V. BOTTAS", position: 14 },
            { carNumber: "24", userName: "Z. GUANYU", position: 15 },
            { carNumber: "27", userName: "N. HULKENBERG", position: 16 },
            { carNumber: "20", userName: "K. MAGNUSSEN", position: 17 },
            { carNumber: "23", userName: "A. ALBON", position: 18 },
            { carNumber: "2",  userName: "L. SARGEANT", position: 19 },
            { carNumber: "21", userName: "N. DE VRIES", position: 20 }
        ]
    };

    async function fetchGridData() {
        try {
            const resp = await fetch('/api/session-results?for_grid=true');
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const data = await resp.json();
            if (data.error || !data.drivers || data.drivers.length === 0) throw new Error(data.error || 'No drivers');
            liveDataReceived = true;
            renderGrid(data);
        } catch (e) {
            console.warn('Grid fetch failed:', e.message);
            if (!liveDataReceived) {
                renderGrid(MOCK_DATA);
            }
        }
    }

    // Initial fetch, then poll
    fetchGridData();
    setInterval(fetchGridData, FETCH_INTERVAL);

    function renderGrid(data) {
        const now = Date.now();
        // Throttle re-renders (skip if rendered recently, except first render)
        if (lastRenderTime > 0 && (now - lastRenderTime) < RENDER_INTERVAL) return;
        lastRenderTime = now;

        // Update track name
        if (data.trackName) {
            let trackLabel = data.trackName;
            if (data.trackConfig) trackLabel += ' - ' + data.trackConfig;
            trackNameEl.textContent = trackLabel;
        }

        // Sort drivers by position (qualifying order = grid order)
        const drivers = [...data.drivers].filter(d => d.carNumber);
        drivers.sort((a, b) => {
            const posA = (a.position && a.position > 0) ? a.position : 999;
            const posB = (b.position && b.position > 0) ? b.position : 999;
            return posA - posB;
        });

        gridBody.innerHTML = '';

        // Start/finish line
        const startLine = document.createElement('div');
        startLine.className = 'grid-start-line';
        const startLabel = document.createElement('span');
        startLabel.className = 'grid-start-label';
        startLabel.textContent = 'START';
        startLine.appendChild(startLabel);
        gridBody.appendChild(startLine);

        // Staggered grid: odd positions LEFT, even positions RIGHT
        for (let i = 0; i < drivers.length; i++) {
            const gridPos = i + 1;
            const isLeft = gridPos % 2 === 1; // P1, P3, P5... on left
            const slot = createSlot(drivers[i], gridPos, isLeft);
            // Staggered animation delay: each slot appears 150ms after the previous
            slot.style.setProperty('--delay', (0.5 + i * 0.15) + 's');
            gridBody.appendChild(slot);
        }
    }

    function createSlot(driver, gridPos, isLeft) {
        const slot = document.createElement('div');
        slot.className = 'grid-slot ' + (isLeft ? 'grid-left' : 'grid-right');
        if (gridPos === 1) slot.classList.add('grid-pole');

        // Position
        const posEl = document.createElement('div');
        posEl.className = 'grid-pos';
        posEl.textContent = gridPos;
        slot.appendChild(posEl);

        // Dorsal image
        const img = document.createElement('img');
        img.className = 'grid-dorsal';
        img.src = `/static/dorsales/${driver.carNumber}.png`;
        img.onerror = function () { this.src = '/static/dorsales/default.png'; };
        slot.appendChild(img);

        // Driver info (car number + name)
        const info = document.createElement('div');
        info.className = 'grid-driver-info';

        const numEl = document.createElement('div');
        numEl.className = 'grid-car-number';
        numEl.textContent = '#' + driver.carNumber;
        info.appendChild(numEl);

        const nameEl = document.createElement('div');
        nameEl.className = 'grid-driver-name';
        nameEl.textContent = driver.userName || driver.fullName || 'Unknown';
        info.appendChild(nameEl);

        slot.appendChild(info);

        // Pole badge
        if (gridPos === 1) {
            const badge = document.createElement('span');
            badge.className = 'grid-pole-badge';
            badge.textContent = 'POLE';
            slot.appendChild(badge);
        }

        return slot;
    }
});
