import { initializeApp } from "firebase/app";
import { deleteToken, getMessaging, getToken, isSupported, onMessage } from "firebase/messaging";

import api from "./api";

const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY || "AIzaSyCOsNcMvmrNsTlFK2mqkQzF7TdY_dVRwAI",
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN || "mymanito-alert.firebaseapp.com",
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID || "mymanito-alert",
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET || "mymanito-alert.firebasestorage.app",
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID || "525194715167",
  appId: import.meta.env.VITE_FIREBASE_APP_ID || "1:525194715167:web:a5ccabeb61934a6aaeb52a",
};
const vapidKey = import.meta.env.VITE_FIREBASE_VAPID_KEY || "BOph7mAWGG9QvBQIGPu67UjvTHPqCnzx2QNfY3wUaRSDrQSYbfJZdz11qZMzCg1vYE17g234QWp_XB3k66lKmxg";

const firebaseApp = initializeApp(firebaseConfig);
let foregroundListenerStarted = false;

export function webPushPermission() {
  if (!("Notification" in window) || !("serviceWorker" in navigator)) {
    return "unsupported";
  }
  return Notification.permission;
}

export async function enableWebPush() {
  if (webPushPermission() === "unsupported") {
    throw new Error("이 브라우저는 웹 푸시 알림을 지원하지 않습니다.");
  }

  const permission = await Notification.requestPermission();
  if (permission !== "granted") {
    throw new Error("브라우저 알림 권한이 허용되지 않았습니다.");
  }

  await syncWebPushDevice();
}

export async function syncWebPushDevice() {
  if (webPushPermission() !== "granted" || !(await isSupported())) {
    return false;
  }

  await navigator.serviceWorker.register("/firebase-messaging-sw.js");
  const registration = await navigator.serviceWorker.ready;
  if (!registration.active) {
    throw new Error("알림 서비스 워커를 준비하지 못했습니다. 페이지를 새로고침해 다시 시도해 주세요.");
  }
  const messaging = getMessaging(firebaseApp);
  const token = await getToken(messaging, { vapidKey, serviceWorkerRegistration: registration });
  if (!token) {
    throw new Error("이 기기의 알림 등록 토큰을 받지 못했습니다.");
  }

  await api.post("/accounts/web-push-devices/", { token });
  startForegroundListener(messaging);
  return true;
}

export async function disableWebPush() {
  if (webPushPermission() !== "granted" || !(await isSupported())) {
    return;
  }

  const registration = await navigator.serviceWorker.getRegistration();
  if (!registration?.active) {
    return;
  }

  const messaging = getMessaging(firebaseApp);
  const token = await getToken(messaging, { vapidKey, serviceWorkerRegistration: registration });
  if (token) {
    await api.delete("/accounts/web-push-devices/", { data: { token } });
  }
  await deleteToken(messaging);
}

function startForegroundListener(messaging) {
  if (foregroundListenerStarted) {
    return;
  }
  foregroundListenerStarted = true;
  onMessage(messaging, (payload) => {
    const { title = "MyManito 새 알림", body = "새 소식이 도착했습니다.", path = "/notifications" } = payload.data || {};
    const notification = new Notification(title, { body, icon: "/favicon.webp" });
    notification.onclick = () => {
      window.focus();
      window.location.assign(path);
      notification.close();
    };
  });
}
