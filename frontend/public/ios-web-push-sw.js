const appOrigin = self.location.origin;

self.addEventListener("push", (event) => {
  if (!event.data) {
    return;
  }

  let payload;
  try {
    payload = event.data.json();
  } catch {
    return;
  }

  event.waitUntil(self.registration.showNotification(payload.title || "MyManito 새 알림", {
    body: payload.body || "새 소식이 도착했습니다.",
    icon: "/favicon.webp",
    data: { path: payload.path || "/notifications" },
  }));
});

self.addEventListener("notificationclick", (event) => {
  const path = event.notification.data?.path;
  if (!path) {
    return;
  }

  event.notification.close();
  const targetUrl = new URL(path, appOrigin).href;
  event.waitUntil(clients.matchAll({ type: "window", includeUncontrolled: true }).then((windowClients) => {
    const existingClient = windowClients.find((client) => client.url.startsWith(appOrigin));
    if (existingClient) {
      return existingClient.focus().then(() => existingClient.navigate(targetUrl));
    }
    return clients.openWindow(targetUrl);
  }));
});
