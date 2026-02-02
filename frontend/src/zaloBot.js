// src/zaloBot.js
import fs from 'fs/promises';
import fetch from 'node-fetch';
import { Zalo } from "zca-js";
import { CREDENTIALS_PATH, PYTHON_API_URL, POLICY_BOT_API_URL } from './config.js';
import * as ThreadManager from './threadManager.js';

let api;

export function getApi() {
    return api;
}

export async function loginAndInit() {
    const zalo = new Zalo();
    try {
        console.log("INFO: Đang thử đăng nhập bằng phiên đã lưu...");
        const savedCredentials = JSON.parse(await fs.readFile(CREDENTIALS_PATH, "utf-8"));
        api = await zalo.login(savedCredentials);
        console.log("✅ Đăng nhập bằng phiên đã lưu thành công!");
    } catch (error) {
        console.warn("WARN: Không thể đăng nhập bằng phiên đã lưu. Chuyển qua quét mã QR.");

        api = await zalo.loginQR({ qrPath: "./qr.png" });
        console.log("✅ Đăng nhập bằng QR thành công!");

        const newCredentials = {
            imei: api.getContext().imei,
            userAgent: api.getContext().userAgent,
            cookie: api.getContext().cookie.toJSON()?.cookies,
        };
        await fs.writeFile(CREDENTIALS_PATH, JSON.stringify(newCredentials, null, 2));
        console.log(`INFO: Đã lưu phiên đăng nhập mới vào file '${CREDENTIALS_PATH}'.`);
    }

    const myUid = api.getContext().uid;
    const profileData = await api.getUserInfo(myUid);
    const myProfile = profileData.changed_profiles[myUid];

    console.log("========================================");
    console.log(`🤖 Bot đang chạy dưới tên: ${myProfile.displayName}`);
    console.log(`👂 Bot đã sẵn sàng lắng nghe tin nhắn...`);
    console.log("========================================");
}

export function startMessageListener() {
    const { listener } = api;

    listener.on("message", async (message) => {
        // Cập nhật thông tin cuộc hội thoại
        ThreadManager.updateThread(message.threadId, {
            type: message.type,
            lastActive: new Date(),
            senderName: message.data.dName,
        });
        console.log(`INFO: Cập nhật hoạt động cho threadId: ${message.threadId}. Tổng số thread đang theo dõi: ${ThreadManager.getActiveThreadsSize()}`);

        const isPlainText = typeof message.data.content === "string";
        const isFromOtherUser = !message.isSelf;

        if (isPlainText && isFromOtherUser && message.data.content) {
            const userMessage = message.data.content;
            const userId = message.threadId;

            console.log(`> Nhận được tin nhắn từ [${message.data.dName}]: "${userMessage}"`);
            console.log(`> Đang chuyển tiếp đến bộ não Python để xử lý...`);

            try {

                // --- ROUTING LOGIC (REVERTED) ---
                // Always forward to the main Python backend as requested.
                const targetApiUrl = PYTHON_API_URL;

                console.log(`> Forwarding message to: [General Assistant] (URL: ${targetApiUrl})`);

                const response = await fetch(targetApiUrl, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ user_id: userId, message: userMessage })
                });

                if (!response.ok) {
                    throw new Error(`API Python trả về lỗi: ${response.status} ${response.statusText}`);
                }

                const data = await response.json();
                const replyText = data.reply;

                if (replyText) {
                    await api.sendMessage({ msg: replyText }, userId, message.type);
                    console.log(`> Đã gửi phản hồi từ AI: "${replyText.substring(0, 80)}..."`);
                }

            } catch (e) {
                console.error("LỖI NGHIÊM TRỌNG khi gọi API Python:", e.message);
                await api.sendMessage(
                    { msg: "Xin lỗi, bộ não của tôi đang gặp chút sự cố. Vui lòng thử lại sau giây lát." },
                    userId,
                    message.type
                );
            }
        }
    });

    listener.onConnected(() => console.log("INFO: Listener đã kết nối thành công tới Zalo."));
    listener.onClosed(() => console.warn("WARN: Listener đã bị ngắt kết nối. Cần khởi động lại."));
    listener.onError((error) => console.error("LỖI LISTENER:", error));

    listener.start();
}
