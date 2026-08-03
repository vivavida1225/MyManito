<script setup>
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import api from "../api";
import { disableWebPush, enableWebPush, syncWebPushDevice, webPushPermission } from "../firebase";
import {
  isIosStandalone,
  subscribeIosWebPush,
  syncIosWebPushSubscription,
  unsubscribeIosWebPush,
} from "../iosWebPush";
import { useAuthStore } from "../stores/auth";

const platform = ref("ANDROID");
const isLoading = ref(true);
const isSaving = ref(false);
const isRegistered = ref(false);
const message = ref("");
const errorMessage = ref("");
const kakaoNotificationEnabled = ref(true);
const isUpdatingKakaoNotification = ref(false);
const isOpeningFeedback = ref(false);
const isLoggingOut = ref(false);
const consentError = ref("");
const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const iosStandalone = computed(() => isIosStandalone());
const needsTalkMessageConsent = computed(
  () => !auth.kakaoProfile?.kakao_scopes?.includes("talk_message"),
);
const KAKAO_AUTHORIZE_URL = "https://kauth.kakao.com/oauth/authorize";
const KAKAO_OAUTH_STATE_KEY = "mymanito.kakao_oauth_state";
const REDIRECT_PATH_KEY = "redirectPath";

function createOAuthState() {
  const bytes = new Uint32Array(4);
  window.crypto.getRandomValues(bytes);
  return Array.from(bytes, (value) => value.toString(36)).join("");
}

function requestTalkMessageConsent() {
  const clientId = import.meta.env.VITE_KAKAO_REST_API_KEY;
  const redirectUri = import.meta.env.VITE_KAKAO_REDIRECT_URI;
  if (!clientId || !redirectUri) {
    consentError.value = "카카오 로그인 환경 설정을 확인해 주세요.";
    return;
  }

  const state = createOAuthState();
  sessionStorage.setItem(KAKAO_OAUTH_STATE_KEY, state);
  localStorage.setItem(REDIRECT_PATH_KEY, route.fullPath);

  const authorizationUrl = new URL(KAKAO_AUTHORIZE_URL);
  authorizationUrl.search = new URLSearchParams({
    client_id: clientId,
    redirect_uri: redirectUri,
    response_type: "code",
    scope: "talk_message,profile_nickname,profile_image,account_email",
    state,
  }).toString();
  window.location.assign(authorizationUrl.toString());
}

async function loadSettings() {
  isLoading.value = true;
  try {
    const response = await api.get("/accounts/notification-settings/");
    platform.value = response.data.notification_platform;
    kakaoNotificationEnabled.value = response.data.kakao_notification_enabled ?? true;
    isRegistered.value = platform.value === "IOS"
      ? await syncIosWebPushSubscription()
      : await syncWebPushDevice();
  } catch (error) {
    errorMessage.value = error.response?.data?.detail || "알림 설정을 불러오지 못했습니다.";
  } finally {
    isLoading.value = false;
  }
}

async function selectPlatform(nextPlatform) {
  if (isSaving.value || platform.value === nextPlatform) {
    return;
  }

  isSaving.value = true;
  errorMessage.value = "";
  message.value = "";
  try {
    await api.patch("/accounts/notification-settings/", { notification_platform: nextPlatform });
    platform.value = nextPlatform;
    isRegistered.value = false;
    message.value = nextPlatform === "IOS"
      ? "iOS 알림을 사용하려면 안내에 따라 홈 화면 앱에서 등록해 주세요."
      : "Android 알림 방식으로 변경했어요.";
  } catch (error) {
    errorMessage.value = error.response?.data?.detail || "기기 유형을 저장하지 못했습니다.";
  } finally {
    isSaving.value = false;
  }
}

async function registerNotifications() {
  isSaving.value = true;
  errorMessage.value = "";
  message.value = "";
  try {
    if (platform.value === "IOS") {
      await subscribeIosWebPush();
    } else {
      await enableWebPush();
    }
    isRegistered.value = true;
    message.value = "이 기기의 알림을 켰어요.";
  } catch (error) {
    errorMessage.value = error.message || "기기 알림을 켜지 못했습니다.";
  } finally {
    isSaving.value = false;
  }
}

async function toggleKakaoNotification() {
  if (isUpdatingKakaoNotification.value) {
    return;
  }

  isUpdatingKakaoNotification.value = true;
  errorMessage.value = "";
  try {
    const response = await api.patch("/accounts/notification-settings/", {
      kakao_notification_enabled: !kakaoNotificationEnabled.value,
    });
    kakaoNotificationEnabled.value = response.data.kakao_notification_enabled;
  } catch (error) {
    errorMessage.value = error.response?.data?.detail || "카카오톡 알림 설정을 저장하지 못했습니다.";
  } finally {
    isUpdatingKakaoNotification.value = false;
  }
}

async function openFeedback() {
  if (isOpeningFeedback.value) {
    return;
  }

  isOpeningFeedback.value = true;
  errorMessage.value = "";
  try {
    const response = await api.post("/chat/feedback/");
    await router.push({ name: "feedback-room", params: { threadId: response.data.thread_id } });
  } catch (error) {
    errorMessage.value = error.response?.data?.detail || "피드백 대화방을 열지 못했습니다.";
  } finally {
    isOpeningFeedback.value = false;
  }
}

async function logoutCurrentDevice() {
  if (isLoggingOut.value) {
    return;
  }

  isLoggingOut.value = true;
  try {
    try {
      if (platform.value === "IOS") {
        await unsubscribeIosWebPush();
      } else {
        await disableWebPush();
      }
    } catch {
      // 기기 구독 해제 실패가 서비스 로그아웃을 막아서는 안 된다.
    }

    try {
      if (auth.refreshToken) {
        await api.post("/accounts/logout/", { refresh: auth.refreshToken });
      }
    } catch {
      // 서버 폐기 실패와 무관하게 현재 브라우저의 세션은 반드시 제거한다.
    }
  } finally {
    auth.logout();
    isLoggingOut.value = false;
    await router.replace({ name: "home" });
  }
}

onMounted(loadSettings);
</script>

<template>
  <section class="p-5 pb-10">
    <p class="text-sm font-bold text-sky-600">내 기기 설정</p>
    <h1 class="mt-1 text-2xl font-extrabold text-slate-800">알림 설정</h1>
    <p class="mt-2 text-sm leading-6 text-slate-500">사용 중인 기기에 맞는 알림 방식을 선택해 주세요.</p>

    <div v-if="isLoading" class="py-16 text-center text-sm text-slate-500">알림 설정을 불러오고 있어요...</div>

    <template v-else>
      <div class="mt-6 grid grid-cols-2 gap-3">
        <button
          type="button"
          class="rounded-2xl border p-4 text-left transition focus:outline-none focus:ring-4 focus:ring-sky-100"
          :class="platform === 'ANDROID' ? 'border-sky-400 bg-sky-50' : 'border-slate-200 bg-white'"
          :disabled="isSaving"
          @click="selectPlatform('ANDROID')"
        >
          <span class="mt-2 block font-extrabold text-slate-800">Android</span>
          <span class="mt-1 block text-xs leading-5 text-slate-500">Chrome 브라우저 알림</span>
        </button>
        <button
          type="button"
          class="rounded-2xl border p-4 text-left transition focus:outline-none focus:ring-4 focus:ring-sky-100"
          :class="platform === 'IOS' ? 'border-sky-400 bg-sky-50' : 'border-slate-200 bg-white'"
          :disabled="isSaving"
          @click="selectPlatform('IOS')"
        >
          <span class="mt-2 block font-extrabold text-slate-800">iPhone</span>
          <span class="mt-1 block text-xs leading-5 text-slate-500">홈 화면 웹앱 알림</span>
        </button>
      </div>

      <div v-if="platform === 'IOS'" class="mt-6 rounded-2xl border border-amber-200 bg-amber-50 p-4">
        <p class="font-extrabold text-amber-900">iOS 알림을 받는 방법</p>
        <p class="mt-2 text-sm leading-6 text-amber-900/80">iOS 16.4 이상에서만 지원하며, 일반 Safari·Chrome 탭에서는 기기 알림을 받을 수 없어요.</p>
        <ol class="mt-2 list-decimal space-y-1 pl-5 text-sm leading-6 text-amber-900/80">
          <li>Safari 또는 Chrome의 공유 메뉴에서 <strong>홈 화면에 추가</strong>를 선택해 주세요.</li>
          <li>홈 화면의 MyManito 아이콘으로 앱을 다시 열어 주세요.</li>
          <li>아래 버튼을 눌러 알림 권한을 허용해 주세요.</li>
        </ol>
        <p v-if="!iosStandalone" class="mt-3 text-sm font-bold text-amber-800">현재는 홈 화면 앱으로 열려 있지 않아요.</p>
      </div>

      <button
        type="button"
        class="mt-6 w-full rounded-2xl bg-sky-600 px-4 py-3 text-sm font-extrabold text-white disabled:opacity-50"
        :disabled="isSaving || isRegistered"
        @click="registerNotifications"
      >
        {{ isRegistered ? "이 기기의 알림이 켜져 있어요" : isSaving ? "설정 중..." : "이 기기 알림 켜기" }}
      </button>

      <p v-if="message" class="mt-3 text-sm font-bold text-emerald-700" role="status">{{ message }}</p>
      <p v-if="errorMessage" class="mt-3 text-sm text-red-600" role="alert">{{ errorMessage }}</p>
      <p v-if="platform === 'ANDROID' && webPushPermission() === 'denied'" class="mt-3 text-sm text-slate-500">브라우저 설정에서 MyManito 알림을 허용해 주세요.</p>

      <aside class="mt-8 rounded-2xl border border-amber-200 bg-amber-50 p-4" aria-labelledby="kakao-notification-guide">
        <p id="kakao-notification-guide" class="text-sm font-extrabold text-amber-900">카카오톡 알림은 ‘나와의 채팅’을 확인해 주세요</p>
        <p class="mt-2 text-sm leading-6 text-amber-900/80">
          익명 마니또의 새 메시지는 카카오톡 친구가 아닌 <strong>내 카카오톡의 ‘나와의 채팅’</strong>으로 도착해요.
          소리·진동 알림 없이 조용히 도착할 수 있으니, 카카오톡의 <strong>나와의 채팅</strong>을 가끔 확인해 주세요.
        </p>
        <p v-if="needsTalkMessageConsent" class="mt-2 text-xs leading-5 text-amber-800">알림을 받으려면 카카오 로그인 중 ‘카카오톡 메시지 전송’ 항목에 동의해야 합니다.</p>
        <p v-else class="mt-2 text-xs font-bold leading-5 text-emerald-700">카카오톡 메시지 전송 동의가 완료되어 있어요.</p>
        <div v-if="needsTalkMessageConsent" class="mt-4 flex justify-end">
          <button
            type="button"
            class="rounded-xl bg-amber-400 px-3 py-2 text-xs font-extrabold text-amber-950 transition hover:bg-amber-300 focus:outline-none focus:ring-4 focus:ring-amber-200"
            @click="requestTalkMessageConsent"
          >
            메시지 전송 동의하러 가기 →
          </button>
        </div>
        <p v-if="consentError" class="mt-2 text-right text-xs font-medium text-red-600" role="alert">{{ consentError }}</p>
      </aside>

      <div class="mt-4 flex items-center justify-between gap-4 rounded-2xl border border-amber-200 bg-white p-4">
        <div>
          <p class="font-extrabold text-slate-800">카카오톡 알림</p>
          <p class="mt-1 text-sm leading-5 text-slate-500">내 카카오톡의 ‘나와의 채팅’으로 새 메시지를 받을지 선택해 주세요.</p>
        </div>
        <button
          type="button"
          class="relative h-8 w-14 shrink-0 rounded-full transition focus:outline-none focus:ring-4 focus:ring-amber-100 disabled:opacity-50"
          :class="kakaoNotificationEnabled ? 'bg-amber-400' : 'bg-slate-300'"
          :aria-label="kakaoNotificationEnabled ? '카카오톡 알림 비활성화' : '카카오톡 알림 활성화'"
          :aria-pressed="kakaoNotificationEnabled"
          :disabled="isUpdatingKakaoNotification"
          @click="toggleKakaoNotification"
        >
          <span
            class="absolute left-1 top-1 h-6 w-6 rounded-full bg-white shadow-sm transition-transform"
            :class="kakaoNotificationEnabled ? 'translate-x-6' : 'translate-x-0'"
          />
        </button>
      </div>
      <p class="mt-2 text-xs font-bold" :class="kakaoNotificationEnabled ? 'text-emerald-700' : 'text-slate-500'">
        {{ kakaoNotificationEnabled ? "카카오톡 알림이 켜져 있어요." : "카카오톡 알림이 꺼져 있어요." }}
      </p>

      <div class="mt-8 flex justify-end">
        <button
          type="button"
          class="rounded-xl bg-slate-800 px-4 py-3 text-sm font-extrabold text-white shadow-sm transition hover:bg-slate-700 disabled:opacity-50"
          :disabled="isOpeningFeedback"
          @click="openFeedback"
        >
          {{ isOpeningFeedback ? "대화방 여는 중..." : "개발자에게 피드백" }}
        </button>
      </div>

      <div class="mt-8 border-t border-slate-200 pt-6">
        <button
          type="button"
          class="w-full rounded-2xl border border-rose-200 bg-white px-4 py-3 text-sm font-extrabold text-rose-600 transition hover:bg-rose-50 disabled:opacity-50"
          :disabled="isLoggingOut"
          @click="logoutCurrentDevice"
        >
          {{ isLoggingOut ? "로그아웃 중..." : "현재 기기에서 로그아웃" }}
        </button>
        <p class="mt-2 text-center text-xs leading-5 text-slate-500">
          다른 기기의 로그인과 알림 설정에는 영향을 주지 않아요.
        </p>
      </div>
    </template>
  </section>
</template>
