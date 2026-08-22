self.addEventListener("install", (e) => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(clients.claim()));

self.addEventListener("message", (e) => {
  if (e.data && e.data.type === "SCHEDULE_PILL") {
    const { name, delayMs } = e.data;
    setTimeout(() => {
      self.registration.showNotification("💊 MediNova Medicine Reminder", {
        body: `Time to take your scheduled dose: ${name}`,
        icon: "https://cdn-icons-png.flaticon.com/512/2966/2966327.png",
        vibrate: [200, 100, 200],
        tag: "med-reminder",
        renotify: true
      });
    }, delayMs);
  }
});
