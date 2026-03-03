/**
 * Web Worker that runs simulations client-side using Pyodide.
 *
 * Message protocol:
 *   Main → Worker:
 *     {type: "init", wheelUrl: string}  -- Load Pyodide and install package
 *     {type: "run", deckJson: string, configJson: string}  -- Run simulation
 *
 *   Worker → Main:
 *     {type: "init_progress", message: string}  -- Init status updates
 *     {type: "ready"}  -- Pyodide loaded and ready
 *     {type: "progress", current: number, total: number}  -- Sim progress
 *     {type: "result", data: Array}  -- Simulation results
 *     {type: "error", message: string}  -- Error occurred
 */

let pyodide = null;

async function initPyodide(wheelUrl) {
    try {
        postMessage({type: "init_progress", message: "Loading Pyodide runtime..."});
        importScripts("https://cdn.jsdelivr.net/pyodide/v0.27.5/full/pyodide.js");

        pyodide = await loadPyodide();

        postMessage({type: "init_progress", message: "Installing numpy..."});
        await pyodide.loadPackage("numpy");

        postMessage({type: "init_progress", message: "Installing simulation engine..."});
        await pyodide.loadPackage("micropip");
        const micropip = pyodide.pyimport("micropip");
        await micropip.install(wheelUrl, {deps: false});

        postMessage({type: "init_progress", message: "Ready"});
        postMessage({type: "ready"});
    } catch (err) {
        postMessage({type: "error", message: "Failed to initialize Pyodide: " + err.message});
    }
}

async function runSimulation(deckJson, configJson) {
    if (!pyodide) {
        postMessage({type: "error", message: "Pyodide not initialized"});
        return;
    }

    try {
        // Define progress callback that posts messages back to main thread
        pyodide.globals.set("_js_progress_callback", function(current, total) {
            postMessage({type: "progress", current: current, total: total});
        });

        // Run the simulation
        const resultJson = await pyodide.runPythonAsync(`
from auto_goldfish.pyodide_runner import run_simulation as _run_sim

_result = _run_sim(
    ${JSON.stringify(deckJson)},
    ${JSON.stringify(configJson)},
    progress_callback=_js_progress_callback,
)
_result
`);

        const results = JSON.parse(resultJson);
        postMessage({type: "result", data: results});
    } catch (err) {
        postMessage({type: "error", message: "Simulation failed: " + err.message});
    }
}

onmessage = function(e) {
    const msg = e.data;
    if (msg.type === "init") {
        initPyodide(msg.wheelUrl);
    } else if (msg.type === "run") {
        runSimulation(msg.deckJson, msg.configJson);
    }
};
