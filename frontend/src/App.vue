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
            :to="{ name: 'notification-settings' }"
            class="rounded-full p-2 text-slate-600 transition hover:bg-amber-50 hover:text-amber-600 focus:outline-none focus:ring-2 focus:ring-amber-400"
            aria-label="알림 설정"
          >
            <svg class="h-5 w-5" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <path d="M19.43 12.98c.04-.32.07-.65.07-.98s-.03-.66-.08-.98l2.11-1.65a.5.5 0 0 0 .12-.64l-2-3.46a.5.5 0 0 0-.61-.22l-2.49 1a7.3 7.3 0 0 0-1.69-.98L14.5 2.42A.5.5 0 0 0 14 2h-4a.5.5 0 0 0-.49.42l-.38 2.65a7.3 7.3 0 0 0-1.69.98l-2.49-1a.5.5 0 0 0-.61.22l-2 3.46a.5.5 0 0 0 .12.64l2.11 1.65c-.05.32-.08.65-.08.98s.03.66.08.98l-2.11 1.65a.5.5 0 0 0-.12.64l2 3.46a.5.5 0 0 0 .61.22l2.49-1c.52.4 1.09.73 1.69.98l.38 2.65c.04.24.25.42.49.42h4c.24 0 .45-.18.49-.42l.38-2.65c.6-.25 1.17-.58 1.69-.98l2.49 1a.5.5 0 0 0 .61-.22l2-3.46a.5.5 0 0 0-.12-.64l-2.11-1.65ZM12 15.5A3.5 3.5 0 1 1 12 8a3.5 3.5 0 0 1 0 7.5Z" />
            </svg>
          </RouterLink>
          <RouterLink
            :to="{ name: 'help' }"
            class="relative rounded-full p-2 transition hover:bg-amber-50 hover:text-amber-600 focus:outline-none focus:ring-2 focus:ring-amber-400"
            :class="needsTalkMessageConsent ? 'text-amber-600' : 'text-slate-600'"
            :aria-label="needsTalkMessageConsent ? '카카오톡 알림 설정이 필요합니다. 서비스 이용 가이드' : '서비스 이용 가이드'"
          >
            <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <circle cx="12" cy="12" r="9" />
              <path d="M9.7 9a2.4 2.4 0 1 1 4.1 1.7c-.9.8-1.8 1.3-1.8 2.8" />
              <circle cx="12" cy="17" r="1" fill="currentColor" stroke="none" />
            </svg>
            <span
              v-if="needsTalkMessageConsent"
              class="absolute -right-0.5 -top-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-amber-400 text-[10px] font-extrabold text-amber-950 ring-2 ring-white"
              aria-hidden="true"
            >
              !
            </span>
          </RouterLink>
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
import { useRealtimeStore } from "./stores/realtime";

const route = useRoute();
const auth = useAuthStore();
const realtime = useRealtimeStore();
const showNavbar = computed(() => route.meta.requiresAuth);
const needsTalkMessageConsent = computed(
  () => !auth.kakaoProfile?.kakao_scopes?.includes("talk_message"),
);
const unreadNotificationCount = ref(0);

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
  realtime.start();
  window.addEventListener("notifications-updated", loadUnreadNotificationCount);
  window.addEventListener("realtime-notifications-changed", loadUnreadNotificationCount);
});

onUnmounted(() => {
  realtime.stop();
  window.removeEventListener("notifications-updated", loadUnreadNotificationCount);
  window.removeEventListener("realtime-notifications-changed", loadUnreadNotificationCount);
});

watch(() => route.fullPath, loadUnreadNotificationCount);
</script>
