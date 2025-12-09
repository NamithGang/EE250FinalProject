// =========================================================================
// NETWORK CONFIGURATION (Entire file was written using Chat GPT)
// =========================================================================
const API_BASE_URL = "http://192.169.0.114:5000"; 
// =========================================================================

document.getElementById('target-ip').innerText = API_BASE_URL;

// --- STATE ---
let chartInstance = null;
const maxDataPoints = 20;
let currentUnit = 'C'; // Default to Celsius
let lastData = null; // Store last received data for UI refreshing

// --- DOM ELEMENTS ---
const ui = {
    temp: document.getElementById('val-temp'),
    unitLbl: document.getElementById('lbl-unit-temp'),
    unitInputLbl: document.getElementById('lbl-unit-input'),
    unitBtn: document.getElementById('btn-unit'),
    
    hum: document.getElementById('val-hum'),
    presenceVal: document.getElementById('val-presence'),
    statusText: document.getElementById('status-text'),
    
    fanBtn: document.getElementById('btn-fan'),
    fanText: document.getElementById('fan-status-text'),

    lightBtn: document.getElementById('btn-light'),
    lightText: document.getElementById('light-status-text'),

    modeToggle: document.getElementById('mode-toggle'),
    thresholdInput: document.getElementById('input-threshold'),
    saveBtn: document.getElementById('btn-save-threshold')
};

// --- HELPER: CONVERSION ---
function toDisplayTemp(celsius) {
    if (currentUnit === 'F') return (celsius * 9/5) + 32;
    return celsius;
}

function toBackendTemp(displayVal) {
    if (currentUnit === 'F') return (displayVal - 32) * 5/9;
    return displayVal;
}

function toggleUnit() {
    // Switch state
    currentUnit = currentUnit === 'C' ? 'F' : 'C';
    
    // Update Button Text
    ui.unitBtn.innerText = `Switch to °${currentUnit === 'C' ? 'F' : 'C'}`;

    // Update Chart Data (Convert existing points)
    const dataset = chartInstance.data.datasets[0];
    dataset.data = dataset.data.map(val => {
        if (currentUnit === 'F') return (val * 9/5) + 32; // C to F
        else return (val - 32) * 5/9; // F to C
    });
    dataset.label = `Temp (°${currentUnit})`;
    chartInstance.update();

    // Refresh UI with last known data
    if (lastData) updateUI(lastData);
}

// --- CHART INITIALIZATION ---
function initChart() {
    const ctx = document.getElementById('envChart').getContext('2d');
    chartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [
                { label: 'Temp (°C)', data: [], borderColor: 'red', fill: false },
                { label: 'Humidity (%)', data: [], borderColor: 'blue', fill: false }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 0 }
        }
    });
}

// --- DATA FETCHING ---
async function fetchStatus() {
    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 4000); 

        const response = await fetch(`${API_BASE_URL}/status`, { signal: controller.signal });
        clearTimeout(timeoutId);

        if (!response.ok) throw new Error(`HTTP Error: ${response.status}`);

        const data = await response.json();
        lastData = data; // Cache data
        
        setConnectionStatus(true, "CONNECTED");
        updateUI(data);
        updateChartData(data.temp, data.humidity);

    } catch (error) {
        if (error.name === 'AbortError') {
            setConnectionStatus(false, "TIMEOUT");
        } else {
            console.error("Connection Failed:", error);
            setConnectionStatus(false, "DISCONNECTED");
        }
    }
}

// --- UI UPDATER ---
function updateUI(data) {
    // Update Temp with Conversion
    if (data.temp !== undefined) {
        ui.temp.innerText = toDisplayTemp(data.temp).toFixed(1);
        ui.unitLbl.innerText = `°${currentUnit}`;
        ui.unitInputLbl.innerText = `°${currentUnit}`;
    } else {
        ui.temp.innerText = "--";
    }

    ui.hum.innerText = data.humidity !== undefined ? data.humidity.toFixed(1) : "--";
    
    // Presence
    if(data.presence) {
        ui.presenceVal.innerText = "DETECTED";
        ui.presenceVal.style.color = "green";
        ui.presenceVal.style.fontWeight = "bold";
    } else {
        ui.presenceVal.innerText = "None";
        ui.presenceVal.style.color = "grey";
        ui.presenceVal.style.fontWeight = "normal";
    }

    // Sync Threshold Input (Convert based on unit)
    // Only update if user is not currently typing
    if (document.activeElement !== ui.thresholdInput && data.target_temp) {
        const displayThreshold = toDisplayTemp(data.target_temp);
        ui.thresholdInput.value = displayThreshold.toFixed(1); // Round for cleaner UI
    }

    // Fan
    if (data.fan) {
        ui.fanText.innerText = "ON";
        ui.fanText.className = "on";
        ui.fanBtn.innerText = "Turn Off";
    } else {
        ui.fanText.innerText = "OFF";
        ui.fanText.className = "off";
        ui.fanBtn.innerText = "Turn On";
    }

    // Light
    if (data.light) {
        ui.lightText.innerText = "ON";
        ui.lightText.className = "on";
        ui.lightBtn.innerText = "Turn Off";
    } else {
        ui.lightText.innerText = "OFF";
        ui.lightText.className = "off";
        ui.lightBtn.innerText = "Turn On";
    }

    // Mode
    const isAuto = (data.mode === 'auto');
    ui.modeToggle.checked = isAuto;
    
    ui.fanBtn.disabled = isAuto;
    ui.lightBtn.disabled = isAuto;
}

// --- CHART UPDATER ---
function updateChartData(temp, hum) {
    if (temp === undefined || hum === undefined) return;

    const now = new Date();
    const timeLabel = now.getHours() + ':' + String(now.getMinutes()).padStart(2, '0') + ':' + String(now.getSeconds()).padStart(2, '0');

    if (chartInstance.data.labels.length > maxDataPoints) {
        chartInstance.data.labels.shift();
        chartInstance.data.datasets[0].data.shift();
        chartInstance.data.datasets[1].data.shift();
    }
    
    // Convert temp before pushing to chart if needed
    const displayTemp = toDisplayTemp(temp);

    chartInstance.data.labels.push(timeLabel);
    chartInstance.data.datasets[0].data.push(displayTemp);
    chartInstance.data.datasets[1].data.push(hum);
    chartInstance.update();
}

function setConnectionStatus(connected, msg) {
    ui.statusText.innerText = msg;
    ui.statusText.className = "";
    if (connected) ui.statusText.classList.add("status-connected");
    else if (msg === "TIMEOUT") ui.statusText.classList.add("status-timeout");
    else ui.statusText.classList.add("status-disconnected");
}

// --- API ACTIONS ---
async function sendCommand(endpoint, payload) {
    try {
        if(endpoint === '/config') ui.saveBtn.innerText = "...";
        
        const response = await fetch(`${API_BASE_URL}${endpoint}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!response.ok) throw new Error("Command failed");

        if(endpoint === '/config') ui.saveBtn.innerText = "Save";
        fetchStatus();
    } catch (error) {
        console.error("Command Error:", error);
        alert("Failed to reach device.");
        if(endpoint === '/config') ui.saveBtn.innerText = "Save";
    }
}

function toggleFan() {
    const isRunning = ui.fanText.innerText === "ON";
    sendCommand('/fan', { state: isRunning ? 'off' : 'on' });
}

function toggleLight() {
    const isOn = ui.lightText.innerText === "ON";
    sendCommand('/light', { state: isOn ? 'off' : 'on' });
}

function toggleMode() {
    const isAuto = ui.modeToggle.checked;
    sendCommand('/mode', { mode: isAuto ? 'auto' : 'manual' });
}

function updateThreshold() {
    const val = parseFloat(ui.thresholdInput.value);
    if (!isNaN(val)) {
        // IMPORTANT: Convert back to Celsius before sending to Backend
        const valToSend = toBackendTemp(val);
        sendCommand('/config', { target_temp: valToSend });
    } else {
        alert("Please enter a valid number");
    }
}

// --- INIT ---
window.addEventListener('DOMContentLoaded', () => {
    initChart();
    setInterval(fetchStatus, 2000);
    fetchStatus(); 
});