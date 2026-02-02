// frontend/index.js
import express from 'express';
import { PORT } from './src/config.js';
import * as ThreadManager from './src/threadManager.js';
import * as ZaloBot from './src/zaloBot.js';

// --- Web Server for Active Notifications ---
function startWebServer() {
    const app = express();
    app.use(express.json());

    app.post('/send-message', async (req, res) => {
        const { target_id, message } = req.body;

        if (!target_id || !message) {
            return res.status(400).json({ error: "Missing 'target_id' or 'message'." });
        }

        const api = ZaloBot.getApi();
        if (!api) {
            return res.status(503).json({ error: "Zalo API not ready." });
        }

        const threadInfo = ThreadManager.getThread(target_id);

        if (!threadInfo) {
            console.error(`ERROR: No thread info for ${target_id}. Interaction required first.`);
            return res.status(404).json({ success: false, error: `No info for threadId ${target_id}.` });
        }

        try {
            console.log(`> Sending active message to ${target_id} (Type: ${threadInfo.type})`);
            await api.sendMessage({ msg: message }, target_id, threadInfo.type);
            console.log(`> Sent successfully to ${target_id}.`);
            res.status(200).json({ success: true, message: "Message sent." });
        } catch (error) {
            console.error(`ERROR sending message to ${target_id}:`, error);
            res.status(500).json({ success: false, error: "Internal error sending message." });
        }
    });

    app.listen(PORT, () => {
        console.log(`🚀 Web server listening on port ${PORT} for python commands.`);
    });
}

// --- Main Execution ---
async function main() {
    try {
        await ThreadManager.loadThreadsFromFile();
        await ZaloBot.loginAndInit();
        ZaloBot.startMessageListener();
        startWebServer();
    } catch (error) {
        console.error("❌ CRITICAL ERROR STARTING BOT:", error);
        process.exit(1);
    }
}

main();
