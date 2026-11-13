const { spawn } = require('child_process');
const path = require('path');

class DSAEngine {
    constructor() {
        this.process = null;
        this.isReady = false;
    }

    start() {
        return new Promise((resolve, reject) => {
            const enginePath = path.join(__dirname, '../../../dsa-engine/build/dsa_engine.exe');

            this.process = spawn(enginePath, [], {
                cwd: path.join(__dirname, '../../../dsa-engine'),
                stdio: ['pipe', 'pipe', 'pipe']
            });

            this.process.stdout.on('data', (data) => {
                const lines = data.toString().trim().split('\n');
                lines.forEach(line => {
                    if (line.trim()) {
                        try {
                            const response = JSON.parse(line);
                            console.log('[DSA Engine]:', response);
                        } catch (e) {
                            console.log('[DSA Engine - Raw]:', line);
                        }
                    }
                });
            });

            this.process.stderr.on('data', (data) => {
                console.error('[DSA Engine Error]:', data.toString());
            });

            this.process.on('close', (code) => {
                console.log(`[DSA Engine] Process exited with code ${code}`);
                this.isReady = false;
            });

            // Test connection
            this.sendCommand({ command: 'PING' })
                .then(response => {
                    if (response.status === 'OK') {
                        return this.sendCommand({ command: 'INIT_SYSTEM' });
                    }
                    throw new Error('PING failed');
                })
                .then(response => {
                    if (response.status === 'READY') {
                        this.isReady = true;
                        console.log(`[DSA Engine] Initialized with ${response.zones_loaded} zones`);
                        resolve();
                    } else {
                        throw new Error('INIT_SYSTEM failed: ' + response.message);
                    }
                })
                .catch(reject);
        });
    }

    sendCommand(command) {
        return new Promise((resolve, reject) => {
            if (!this.process) {
                return reject(new Error('Engine not started'));
            }

            const commandStr = JSON.stringify(command) + '\n';

            // Set up one-time listener for response
            const responseHandler = (data) => {
                const lines = data.toString().trim().split('\n');
                for (const line of lines) {
                    if (line.trim()) {
                        try {
                            const response = JSON.parse(line);
                            this.process.stdout.removeListener('data', responseHandler);
                            resolve(response);
                            return;
                        } catch (e) {
                            // Not JSON, continue
                        }
                    }
                }
            };

            this.process.stdout.on('data', responseHandler);
            this.process.stdin.write(commandStr);

            // Timeout after 5 seconds
            setTimeout(() => {
                this.process.stdout.removeListener('data', responseHandler);
                reject(new Error('Command timeout'));
            }, 5000);
        });
    }

    async startFlood(sourceZone) {
        return this.sendCommand({
            command: 'START_FLOOD',
            source_zone: sourceZone
        });
    }

    async floodStep() {
        return this.sendCommand({
            command: 'FLOOD_STEP'
        });
    }

    async getFloodState() {
        return this.sendCommand({
            command: 'GET_FLOOD_STATE'
        });
    }

    stop() {
        if (this.process) {
            this.process.kill();
            this.process = null;
            this.isReady = false;
        }
    }
}

module.exports = DSAEngine;
