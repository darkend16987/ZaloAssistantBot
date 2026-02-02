// src/threadManager.js
import fs from 'fs/promises';
import { ACTIVE_THREADS_PATH } from './config.js';

let activeThreads = new Map();

export async function saveThreadsToFile() {
    try {
        const threadsObject = Object.fromEntries(activeThreads);
        await fs.writeFile(ACTIVE_THREADS_PATH, JSON.stringify(threadsObject, null, 2));
    } catch (error) {
        console.error("LỖI khi lưu active threads vào file:", error);
    }
}

export async function loadThreadsFromFile() {
    try {
        const data = await fs.readFile(ACTIVE_THREADS_PATH, "utf-8");
        const threadsObject = JSON.parse(data);
        activeThreads = new Map(Object.entries(threadsObject));
        console.log(`✅ Đã tải thành công ${activeThreads.size} cuộc hội thoại từ file lưu trữ.`);
    } catch (error) {
        if (error.code === 'ENOENT') {
            console.warn("WARN: Không tìm thấy file active_threads.json. Sẽ tạo file mới khi có tin nhắn đầu tiên.");
        } else {
            console.error("LỖI khi tải active threads từ file:", error);
        }
    }
}

export function updateThread(threadId, data) {
    activeThreads.set(threadId, data);
    return saveThreadsToFile();
}

export function getThread(threadId) {
    return activeThreads.get(threadId);
}

export function getActiveThreadsSize() {
    return activeThreads.size;
}
