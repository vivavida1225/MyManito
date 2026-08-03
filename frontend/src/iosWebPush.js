import api from "./api";

const vapidPublicKey = import.meta.env.VITE_IOS_WEB_PUSH_VAPID_PUBLIC_KEY || "";
const iosServiceWorkerPath = "/ios-web-push-sw.js";
const iosServiceWorkerScope = "/";

export function isIosStandalone() {
  return window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone === true;
}

export async function syncIosWebPushSubscription() {
  if (!vapidPublicKey || !supportsIosWebPush() || !isIosStandalone() || Notification.permission !== "granted") {
    return false;
  }

  const registration = await registerIosServiceWorker();
  const subscription = await registration.pushManager.getSubscription();
  if (!subscription || !usesIosVapidKey(subscription)) {
    return false;
  }

  await saveIosSubscription(subscription);
  return true;
}

export async function subscribeIosWebPush() {
  if (!vapidPublicKey) {
    throw new Error("iOS 알림용 VAPID 공개 키가 아직 설정되지 않았습니다.");
  }
  if (!supportsIosWebPush()) {
    throw new Error("이 기기에서는 iOS 웹 푸시를 지원하지 않습니다.");
  }
  if (!isIosStandalone()) {
    throw new Error("iOS에서는 홈 화면에 추가한 MyManito 앱에서만 알림을 켤 수 있습니다.");
  }

  const permission = await Notification.requestPermission();
  if (permission !== "granted") {
    throw new Error("알림 권한이 허용되지 않았습니다.");
  }

  const registration = await registerIosServiceWorker();
  let subscription = await registration.pushManager.getSubscription();
  let replacedEndpoint = "";
  if (subscription && !usesIosVapidKey(subscription)) {
    replacedEndpoint = subscription.endpoint;
    const unsubscribed = await subscription.unsubscribe();
    if (!unsubscribed) {
      throw new Error("기존 알림 구독을 갱신하지 못했습니다. 잠시 후 다시 시도해 주세요.");
    }
    subscription = null;
  }
  subscription = subscription || await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: base64UrlToUint8Array(vapidPublicKey),
  });
  await saveIosSubscription(subscription);
  if (replacedEndpoint && replacedEndpoint !== subscription.endpoint) {
    await deleteIosSubscription(replacedEndpoint);
  }
}

function supportsIosWebPush() {
  return "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
}

async function registerIosServiceWorker() {
  return navigator.serviceWorker.register(iosServiceWorkerPath, { scope: iosServiceWorkerScope });
}

function usesIosVapidKey(subscription) {
  const applicationServerKey = subscription.options?.applicationServerKey;
  if (!applicationServerKey) {
    return false;
  }
  const currentKey = new Uint8Array(applicationServerKey);
  const expectedKey = base64UrlToUint8Array(vapidPublicKey);
  return currentKey.length === expectedKey.length
    && currentKey.every((value, index) => value === expectedKey[index]);
}

async function saveIosSubscription(subscription) {
  const subscriptionData = subscription.toJSON();
  if (!subscriptionData.keys?.p256dh || !subscriptionData.keys?.auth) {
    throw new Error("iOS 웹 푸시 구독 키를 확인하지 못했습니다.");
  }
  await api.post("/accounts/ios-web-push-subscriptions/", {
    endpoint: subscription.endpoint,
    p256dh: subscriptionData.keys.p256dh,
    auth: subscriptionData.keys.auth,
  });
}

async function deleteIosSubscription(endpoint) {
  await api.delete("/accounts/ios-web-push-subscriptions/", {
    data: { endpoint },
  });
}

export async function unsubscribeIosWebPush() {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
    return;
  }

  const registration = await navigator.serviceWorker.getRegistration(iosServiceWorkerScope);
  const subscription = await registration?.pushManager.getSubscription();
  if (!subscription) {
    return;
  }

  await deleteIosSubscription(subscription.endpoint);
  await subscription.unsubscribe();
}

function base64UrlToUint8Array(value) {
  const padded = `${value}${"=".repeat((4 - value.length % 4) % 4)}`;
  const base64 = padded.replace(/-/g, "+").replace(/_/g, "/");
  const raw = window.atob(base64);
  return Uint8Array.from(raw, (character) => character.charCodeAt(0));
}
