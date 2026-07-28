import api from "./api";

const vapidPublicKey = import.meta.env.VITE_IOS_WEB_PUSH_VAPID_PUBLIC_KEY || "";

export function isIosStandalone() {
  return window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone === true;
}

export async function subscribeIosWebPush() {
  if (!vapidPublicKey) {
    throw new Error("iOS 알림용 VAPID 공개 키가 아직 설정되지 않았습니다.");
  }
  if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) {
    throw new Error("이 기기에서는 iOS 웹 푸시를 지원하지 않습니다.");
  }
  if (!isIosStandalone()) {
    throw new Error("iOS에서는 홈 화면에 추가한 MyManito 앱에서만 알림을 켤 수 있습니다.");
  }

  const permission = await Notification.requestPermission();
  if (permission !== "granted") {
    throw new Error("알림 권한이 허용되지 않았습니다.");
  }

  await navigator.serviceWorker.register("/ios-web-push-sw.js");
  const registration = await navigator.serviceWorker.ready;
  const subscription = await registration.pushManager.getSubscription()
    || await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: base64UrlToUint8Array(vapidPublicKey),
    });
  const subscriptionData = subscription.toJSON();
  await api.post("/accounts/ios-web-push-subscriptions/", {
    endpoint: subscription.endpoint,
    p256dh: subscriptionData.keys.p256dh,
    auth: subscriptionData.keys.auth,
  });
}

export async function unsubscribeIosWebPush() {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
    return;
  }

  const registration = await navigator.serviceWorker.getRegistration();
  const subscription = await registration?.pushManager.getSubscription();
  if (!subscription) {
    return;
  }

  await api.delete("/accounts/ios-web-push-subscriptions/", {
    data: { endpoint: subscription.endpoint },
  });
  await subscription.unsubscribe();
}

function base64UrlToUint8Array(value) {
  const padded = `${value}${"=".repeat((4 - value.length % 4) % 4)}`;
  const base64 = padded.replace(/-/g, "+").replace(/_/g, "/");
  const raw = window.atob(base64);
  return Uint8Array.from(raw, (character) => character.charCodeAt(0));
}
