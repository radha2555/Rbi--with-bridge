// server.js
const express = require('express');
const { spawn } = require('child_process');
const axios = require('axios');
const cors = require('cors');

const app = express();
const PORT = 3001; // Port for the Node.js proxy server
const FASTAPI_PORT = 8000;
const FASTAPI_URL = `http://localhost:${FASTAPI_PORT}`;

let fastapiProcess = null;
let inactivityTimer = null;
const INACTIVITY_TIMEOUT = 2 * 60 * 1000; // 2 minutes in milliseconds

app.use(express.json());
app.use(cors({
    origin: 'http://localhost:3000' // Allow your React app's origin
}));

// Determine the correct startup script based on the OS
const STARTUP_SCRIPT_NAME = process.platform === 'win32' ? 'start_fastapi.bat' : 'start_fastapi.sh';

// Function to start the FastAPI process
function startFastAPIServer() {
    if (fastapiProcess) {
        console.log("FastAPI server is already running. Not starting a new one.");
        return;
    }

    console.log(`Attempting to start FastAPI server using ${STARTUP_SCRIPT_NAME}...`);
    fastapiProcess = spawn(STARTUP_SCRIPT_NAME, [], {
        cwd: 'C:/Users/Hp/Desktop/RBI-catbot-main/backend', // This path should point to your FastAPI project root
        detached: true, 
        shell: true 
    });

    fastapiProcess.stdout.on('data', (data) => {
        console.log(`[FastAPI stdout]: ${data.toString().trim()}`);
    });

    fastapiProcess.stderr.on('data', (data) => {
        console.error(`[FastAPI stderr]: ${data.toString().trim()}`);
    });

    fastapiProcess.on('close', (code) => {
        console.log(`FastAPI process exited with code ${code}.`);
        fastapiProcess = null;
        clearInterval(inactivityTimer);
        inactivityTimer = null;
    });

    fastapiProcess.on('error', (err) => {
        console.error(`Failed to start FastAPI process using ${STARTUP_SCRIPT_NAME}: ${err.message}.`);
        console.error("Please ensure the script exists in the correct 'cwd' and has proper permissions.");
        fastapiProcess = null;
        clearInterval(inactivityTimer);
        inactivityTimer = null;
    });

    console.log(`FastAPI process PID: ${fastapiProcess.pid}`);
    resetInactivityTimer();
}

// Function to shut down the FastAPI process gracefully
async function shutdownFastAPIServer() {
    if (!fastapiProcess) {
        console.log("FastAPI server is not running. No shutdown needed.");
        return;
    }

    console.log("Attempting to shut down FastAPI server gracefully...");
    try {
        const response = await axios.post(`${FASTAPI_URL}/shutdown`, {}, { timeout: 2000 });
        console.log(`FastAPI shutdown endpoint responded: ${response.data.message}`);
        
        setTimeout(() => {
            if (fastapiProcess) {
                console.log("FastAPI process still active after graceful shutdown attempt. Force killing.");
                try {
                    process.kill(-fastapiProcess.pid, 'SIGKILL');
                } catch (killErr) {
                    console.error(`Error force killing process ${fastapiProcess.pid}: ${killErr.message}`);
                }
                fastapiProcess = null;
            }
        }, 3000);
        
    } catch (error) {
        console.error("Error triggering FastAPI graceful shutdown endpoint:", error.message);
        console.log("Graceful shutdown failed. Forcefully killing FastAPI process.");
        if (fastapiProcess && fastapiProcess.pid) {
             try {
                process.kill(-fastapiProcess.pid, 'SIGKILL');
            } catch (killErr) {
                console.error(`Error force killing process ${fastapiProcess.pid}: ${killErr.message}`);
            }
        }
        fastapiProcess = null;
    } finally {
        clearInterval(inactivityTimer);
        inactivityTimer = null;
    }
}

// Function to reset the inactivity timer
function resetInactivityTimer() {
    clearInterval(inactivityTimer);
    inactivityTimer = setTimeout(() => {
        console.log("Inactivity timer expired. Initiating FastAPI server shutdown...");
        shutdownFastAPIServer();
    }, INACTIVITY_TIMEOUT);
    console.log(`Inactivity timer reset. Will shut down in ${INACTIVITY_TIMEOUT / 1000} seconds if idle.`);
}

// API endpoint for the frontend to request starting the backend
app.post('/api/start-backend', (req, res) => {
    startFastAPIServer();
    res.json({ message: "Backend start initiated." });
});

// API endpoint for the frontend to explicitly request shutting down the backend
app.post('/api/shutdown-backend', (req, res) => {
    shutdownFastAPIServer();
    res.json({ message: "Backend shutdown initiated." });
});

// API endpoint for the frontend to check the current status of the backend
app.get('/api/backend-status', async (req, res) => {
    if (!fastapiProcess) {
        // If the child process is not even started or has officially closed, it's inactive.
        return res.json({ active: false, message: "FastAPI process is not running." });
    }
    try {
        // Attempt to hit the FastAPI health endpoint
        // Increased timeout to give FastAPI more time to fully initialize and respond.
        const response = await axios.get(`${FASTAPI_URL}/health`, { timeout: 5000 }); // Increased timeout to 5 seconds
        // If we get a 200 OK, FastAPI is active and responsive.
        if (response.status === 200) {
            console.log("FastAPI health check successful."); // Added log for success
            return res.json({ active: true, message: "FastAPI server is active." });
        }
    } catch (error) {
        // If the health check fails (e.g., connection refused, timeout)
        let errorMessage = `FastAPI health check from /backend-status failed: ${error.message}`;
        if (error.code) { // Check for specific error codes like 'ECONNREFUSED' or 'ETIMEDOUT'
            errorMessage += ` (Code: ${error.code})`;
        }
        console.error(errorMessage);
        // IMPORTANT: DO NOT set fastapiProcess = null here.
        // The process.on('close') listener is responsible for updating fastapiProcess to null
        // when the child process truly exits. This allows for temporary network issues
        // or initial startup delays without prematurely marking the backend as dead.
    }
    // If we reach here, it means fastapiProcess is not null, but the health check failed.
    // So, we report it as inactive for this particular check.
    res.json({ active: false, message: "FastAPI server is not responsive or has crashed." });
});

// Proxy all other requests to the FastAPI server
app.use('/api', async (req, res) => {
    if (!fastapiProcess) {
        return res.status(503).json({ error: "Backend server is not running or not ready." });
    }

    resetInactivityTimer();

    const targetPath = req.originalUrl.replace(/^\/api/, '');
    const targetUrl = `${FASTAPI_URL}${targetPath}`;

    try {
        const response = await axios({
            method: req.method,
            url: targetUrl,
            headers: req.headers,
            data: req.body,
        });

        res.status(response.status).send(response.data);
    } catch (error) {
        if (error.response) {
            console.error(`FastAPI responded with error ${error.response.status}:`, error.response.data);
            res.status(error.response.status).send(error.response.data);
        } else if (error.request) {
            console.error("No response received from FastAPI. It might be down or unreachable:", error.message);
            res.status(500).json({ error: "No response from backend; it might be starting or has crashed." });
        } else {
            console.error("Error setting up request to FastAPI:", error.message);
            res.status(500).json({ error: "Proxy error during request processing." });
        }
    }
});

// Start the Node.js proxy server
app.listen(PORT, () => {
    console.log(`Node.js proxy server listening on port ${PORT}`);
    console.log(`Proxying requests from http://localhost:${PORT}/api/* to http://localhost:${FASTAPI_PORT}/*`);
});

// Handle graceful shutdown of the Node.js proxy and its child processes
process.on('SIGINT', () => {
    console.log("\nNode.js proxy received SIGINT. Shutting down...");
    shutdownFastAPIServer().then(() => {
        console.log("FastAPI shutdown initiated. Exiting Node.js proxy.");
        process.exit(0);
    }).catch(err => {
        console.error("Error during Node.js SIGINT shutdown:", err);
        process.exit(1);
    });
});

process.on('SIGTERM', () => {
    console.log("\nNode.js proxy received SIGTERM. Shutting down...");
    shutdownFastAPIServer().then(() => {
        console.log("FastAPI shutdown initiated. Exiting Node.js proxy.");
        process.exit(0);
    }).catch(err => {
        console.error("Error during Node.js SIGTERM shutdown:", err);
        process.exit(1);
    });
});
