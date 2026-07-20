<template>
  <div class="min-h-dvh bg-slate-100">
    <main class="mx-auto min-h-dvh w-full max-w-md bg-gray-50 shadow-sm sm:shadow-xl">
      <header
        v-if="showNavbar"
        class="sticky top-0 z-10 flex h-16 items-center justify-between border-b border-amber-100 bg-white/95 px-5 backdrop-blur"
      >
        <RouterLink
          :to="{ name: 'dashboard' }"
          class="rounded-lg focus:outline-none focus:ring-2 focus:ring-amber-400"
          aria-label="MyManito 대시보드로 이동"
        >
          <img :src="navbarLogo" alt="MyManito" class="h-8 w-auto" />
        </RouterLink>

        <nav class="flex items-center gap-1" aria-label="주요 메뉴">
          <RouterLink
            :to="{ name: 'notifications' }"
            class="relative rounded-full p-2 text-slate-600 transition hover:bg-amber-50 hover:text-amber-600 focus:outline-none focus:ring-2 focus:ring-amber-400"
            aria-label="알림함"
          >
            <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9" />
              <path d="M10 21h4" />
            </svg>
            <span
              v-if="unreadNotificationCount"
              class="absolute -right-0.5 -top-0.5 flex min-h-5 min-w-5 items-center justify-center rounded-full bg-rose-500 px-1 text-[10px] font-extrabold text-white ring-2 ring-white"
            >
              {{ unreadNotificationCount > 99 ? "99+" : unreadNotificationCount }}
            </span>
          </RouterLink>
          <RouterLink
            :to="{ name: 'chat-list' }"
            class="rounded-full p-2 text-slate-600 transition hover:bg-amber-50 hover:text-amber-600 focus:outline-none focus:ring-2 focus:ring-amber-400"
            aria-label="채팅 목록"
          >
            <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <path d="M21 11.5a8.4 8.4 0 0 1-9 8.5 9.7 9.7 0 0 1-4.8-1.3L3 20l1.4-3.7A8.4 8.4 0 0 1 3 11.5 8.4 8.4 0 0 1 12 3a8.4 8.4 0 0 1 9 8.5Z" />
            </svg>
          </RouterLink>
        </nav>
      </header>
      <RouterView />
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute } from "vue-router";

import api from "./api";
import navbarLogo from "./assets/MyManito_navbar.webp";
import { useAuthStore } from "./stores/auth";

const route = useRoute();
const auth = useAuthStore();
const showNavbar = computed(() => route.meta.requiresAuth);
const unreadNotificationCount = ref(0);
let notificationPoller;

async function loadUnreadNotificationCount() {
  if (!auth.isAuthenticated) {
    unreadNotificationCount.value = 0;
    return;
  }

  try {
    const response = await api.get("/notifications/");
    unreadNotificationCount.value = response.data.unread_count || 0;
  } catch {
    // 알림 조회 실패가 현재 화면 사용을 막지는 않는다.
  }
}

onMounted(() => {
  loadUnreadNotificationCount();
  notificationPoller = window.setInterval(loadUnreadNotificationCount, 15_000);
  window.addEventListener("notifications-updated", loadUnreadNotificationCount);
});

onUnmounted(() => {
  window.clearInterval(notificationPoller);
  window.removeEventListener("notifications-updated", loadUnreadNotificationCount);
});

watch(() => route.fullPath, loadUnreadNotificationCount);
</script>
