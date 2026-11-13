const express = require('express');
const cors = require('cors');
const DSAEngine = require('./cpp-bridge/dsaEngine');

const app = express();
const PORT = 3001;

app.use(cors());
app.use(express.json());

// Initialize DSA Engine
const engine = new DSAEngine();
let engineReady = false;

engine.start()
    .then(() => {
        engineReady = true;
        console.log('[Server] DSA Engine ready');
    })
    .catch(err => {
        console.error('[Server] Failed to start DSA Engine:', err);
    });

// API Routes
app.post('/api/flood/start', async (req, res) => {
    try {
        if (!engineReady) {
            return res.status(503).json({ error: 'Engine not ready' });
        }

        const { sourceZone } = req.body;
        const result = await engine.startFlood(sourceZone);
        res.json(result);
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.post('/api/flood/step', async (req, res) => {
    try {
        if (!engineReady) {
            return res.status(503).json({ error: 'Engine not ready' });
        }

        const result = await engine.floodStep();
        res.json(result);
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.get('/api/flood/state', async (req, res) => {
    try {
        if (!engineReady) {
            return res.status(503).json({ error: 'Engine not ready' });
        }

        const result = await engine.getFloodState();
        res.json(result);
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.get('/health', (req, res) => {
    res.json({
        status: 'ok',
        engineReady
    });
});

app.listen(PORT, () => {
    console.log(`[Server] Running on http://localhost:${PORT}`);
});

// Cleanup on exit
process.on('SIGINT', () => {
    console.log('\n[Server] Shutting down...');
    engine.stop();
    process.exit(0);
});
