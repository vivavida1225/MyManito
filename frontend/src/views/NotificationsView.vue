<script setup>
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRouter } from "vue-router";

import api from "../api";
import waitingImage from "../assets/mani_waiting.webp";

const router = useRouter();
const notifications = ref([]);
const errorMessage = ref("");
const isLoading = ref(false);
const isMarkingAllRead = ref(false);
const isClearing = ref(false);
const hasUnreadNotifications = computed(() => notifications.value.some((notification) => !notification.is_read));

function formatCreatedAt(createdAt) {
  return new Intl.DateTimeFormat("ko-KR", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(createdAt));
}

function notificationIcon(kind) {
  return {
    MESSAGE: "💌",
    FEEDBACK_MESSAGE: "💬",
    COUNTERPART_CLAIMED: "🙌",
    PARTICIPANT_CLAIMED: "✅",
    DDAY: "📅",
    RESULT_AVAILABLE: "🎉",
    TEAM_ANNOUNCEMENT: "📣",
  }[kind] || "🔔";
}

async function loadNotifications() {
  isLoading.value = true;
  errorMessage.value = "";
  try {
    const response = await api.get("/notifications/");
    notifications.value = response.data.notifications || [];
    window.dispatchEvent(new Event("notifications-updated"));
  } catch (error) {
    errorMessage.value = error.response?.data?.detail || "알림을 불러오지 못했습니다.";
  } finally {
    isLoading.value = false;
  }
}

async function openNotification(notification) {
  if (notification.kind === "MESSAGE" && notification.data?.room_id) {
    await router.push({ name: "chat-room", params: { roomId: notification.data.room_id } });
    return;
  }

  if (notification.kind === "FEEDBACK_MESSAGE" && notification.data?.feedback_thread_id) {
    await router.push({
      name: "feedback-room",
      params: { threadId: notification.data.feedback_thread_id },
    });
    return;
  }

  if (!notification.is_read) {
    try {
      await api.post(`/notifications/${notification.id}/read/`);
      notification.is_read = true;
      window.dispatchEvent(new Event("notifications-updated"));
    } catch (error) {
      errorMessage.value = error.response?.data?.detail || "알림을 읽음 처리하지 못했습니다.";
      return;
    }
  }

  if (notification.kind === "RESULT_AVAILABLE") {
    await router.push({ name: "team-reveal", params: { teamCode: notification.team_code } });
    return;
  }

  if (notification.team_code) {
    await router.push({ name: "team-home", params: { teamCode: notification.team_code } });
  }
}

async function markAllAsRead() {
  if (!hasUnreadNotifications.value) {
    return;
  }

  isMarkingAllRead.value = true;
  errorMessage.value = "";
  try {
    await api.post("/notifications/read-all/");
    notifications.value.forEach((notification) => {
      notification.is_read = true;
    });
    window.dispatchEvent(new Event("notifications-updated"));
  } catch (error) {
    errorMessage.value = error.response?.data?.detail || "알림을 읽음 처리하지 못했습니다.";
  } finally {
    isMarkingAllRead.value = false;
  }
}

async function clearNotifications() {
  if (!notifications.value.length || !window.confirm("알림함의 모든 알림을 비울까요?")) {
    return;
  }

  isClearing.value = true;
  errorMessage.value = "";
  try {
    await api.delete("/notifications/clear/");
    notifications.value = [];
    window.dispatchEvent(new Event("notifications-updated"));
  } catch (error) {
    errorMessage.value = error.response?.data?.detail || "알림을 비우지 못했습니다.";
  } finally {
    isClearing.value = false;
  }
}

onMounted(() => {
  loadNotifications();
  window.addEventListener("realtime-notifications-changed", loadNotifications);
});

onUnmounted(() => {
  window.removeEventListener("realtime-notifications-changed", loadNotifications);
});
</script>

<template>
  <section class="p-5 pb-10">
    <div class="flex items-start justify-between gap-3">
      <div>
        <p class="text-sm font-bold text-amber-500">새 소식 모아보기</p>
        <h1 class="mt-1 text-2xl font-extrabold text-slate-800">알림함</h1>
      </div>
      <div class="flex gap-2">
        <button
          type="button"
          class="rounded-xl bg-white px-3 py-2 text-sm font-bold text-slate-600 shadow-sm ring-1 ring-slate-100 disabled:opacity-50"
          :disabled="isLoading || isMarkingAllRead || isClearing || !hasUnreadNotifications"
          @click="markAllAsRead"
        >
          {{ isMarkingAllRead ? "처리 중..." : "모두 읽음" }}
        </button>
        <button
          type="button"
          class="rounded-xl bg-white px-3 py-2 text-sm font-bold text-slate-600 shadow-sm ring-1 ring-slate-100 disabled:opacity-50"
          :disabled="isLoading || isMarkingAllRead || isClearing || !notifications.length"
          @click="clearNotifications"
        >
          {{ isClearing ? "비우는 중..." : "알림 비우기" }}
        </button>
      </div>
    </div>

    <p v-if="isLoading && !notifications.length" class="py-16 text-center text-sm text-slate-500">알림을 불러오고 있어요...</p>

    <div v-else-if="notifications.length" class="mt-6 space-y-3">
      <button
        v-for="notification in notifications"
        :key="notification.id"
        type="button"
        class="flex w-full items-center gap-3 rounded-2xl p-4 text-left transition"
        :class="notification.is_read ? 'bg-white ring-1 ring-slate-100' : 'bg-amber-50 ring-1 ring-amber-200'"
        @click="openNotification(notification)"
      >
        <span class="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-white text-xl shadow-sm" aria-hidden="true">
          {{ notificationIcon(notification.kind) }}
        </span>
        <span class="min-w-0 flex-1">
          <span class="flex items-center gap-2">
            <span class="truncate text-sm font-extrabold text-slate-800">{{ notification.title }}</span>
            <span v-if="!notification.is_read" class="h-2 w-2 shrink-0 rounded-full bg-rose-500" aria-label="읽지 않음" />
          </span>
          <span class="mt-1 block text-sm leading-5 text-slate-500">{{ notification.body }}</span>
          <span class="mt-1 block text-xs text-slate-400">
            <template v-if="notification.team_code">{{ notification.team_code }} · </template>{{ formatCreatedAt(notification.created_at) }}
          </span>
        </span>
        <span class="text-lg text-slate-400" aria-hidden="true">›</span>
      </button>
    </div>

    <div v-else-if="!isLoading" class="mt-12 text-center">
      <img :src="waitingImage" alt="기다리는 마니" class="mx-auto w-36" />
      <h2 class="mt-2 text-lg font-extrabold text-slate-800">아직 새로운 알림이 없어요</h2>
      <p class="mt-2 text-sm text-slate-500">채팅이나 팀 소식이 오면 이곳에서 알려 드릴게요.</p>
    </div>

    <p v-if="errorMessage" class="mt-4 text-sm text-red-600" role="alert">{{ errorMessage }}</p>
  </section>
</template>
