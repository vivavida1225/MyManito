import { defineStore } from "pinia";

import { useAuthStore } from "./auth";

const MAX_RECONNECT_DELAY_MS = 30_000;

function realtimeUrl() {
  if (import.meta.env.VITE_REALTIME_URL) {
    return import.meta.env.VITE_REALTIME_URL;
  }
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/ws/realtime/`;
}

export const useRealtimeStore = defineStore("realtime", {
  state: () => ({
    socket: null,
    reconnectTimer: null,
    reconnectAttempts: 0,
    isStarted: false,
  }),

  actions: {
    start() {
      if (this.isStarted) {
        return;
      }
      this.isStarted = true;
      window.addEventListener("auth-token-updated", this.reconnect);
      window.addEventListener("auth-logout", this.stop);
      this.connect();
    },

    stop() {
      this.isStarted = false;
      window.removeEventListener("auth-token-updated", this.reconnect);
      window.removeEventListener("auth-logout", this.stop);
      window.clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
      const socket = this.socket;
      this.socket = null;
      if (socket) {
        window.dispatchEvent(new Event("realtime-connection-closed"));
        socket.close();
      }
    },

    reconnect() {
      this.stop();
      this.start();
    },

    connect() {
      const auth = useAuthStore();
      auth.initialize();
      if (!this.isStarted || !auth.accessToken || this.socket) {
        return;
      }

      try {
        const socket = new WebSocket(realtimeUrl(), ["mymanito-v1", auth.accessToken]);
        this.socket = socket;
        socket.onopen = () => {
          if (this.socket !== socket) {
            return;
          }
          this.reconnectAttempts = 0;
          window.dispatchEvent(new Event("realtime-chat-rooms-changed"));
          window.dispatchEvent(new Event("realtime-notifications-changed"));
        };
        socket.onmessage = (message) => this.handleMessage(message);
        socket.onclose = (event) => {
          if (this.socket !== socket) {
            return;
          }
          this.socket = null;
          window.dispatchEvent(new Event("realtime-connection-closed"));
          if (event.code === 4401) {
            auth.logoutAndRedirect();
            return;
          }
          this.scheduleReconnect();
        };
        socket.onerror = () => socket.close();
      } catch {
        this.scheduleReconnect();
      }
    },

    scheduleReconnect() {
      const auth = useAuthStore();
      if (!this.isStarted || !auth.accessToken || this.reconnectTimer) {
        return;
      }
      const delay = Math.min(1_000 * 2 ** this.reconnectAttempts, MAX_RECONNECT_DELAY_MS);
      this.reconnectAttempts += 1;
      this.reconnectTimer = window.setTimeout(() => {
        this.reconnectTimer = null;
        this.connect();
      }, delay);
    },

    sendChatMessage({ tempId, content, roomId = null, feedbackThreadId = null }) {
      if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
        throw new Error("실시간 연결이 끊어져 있습니다.");
      }
      this.socket.send(JSON.stringify({
        event: "chat.message.send",
        tempId,
        content,
        ...(roomId ? { roomId } : { feedbackThreadId }),
      }));
    },

    handleMessage(message) {
      try {
        const event = JSON.parse(message.data);
        const eventName = {
          "chat.message.created": "realtime-chat-message",
          "chat.message.failed": "realtime-chat-message-failed",
          "chat.rooms.changed": "realtime-chat-rooms-changed",
          "notifications.changed": "realtime-notifications-changed",
        }[event.event];
        if (eventName) {
          window.dispatchEvent(new CustomEvent(eventName, { detail: event }));
        }
      } catch {
        // 잘못된 실시간 이벤트는 현재 화면을 중단시키지 않는다.
      }
    },
  },
});
