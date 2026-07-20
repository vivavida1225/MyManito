<script setup>
import { ref } from "vue";
import { useRoute } from "vue-router";

import introducingImage from "../assets/mani_introducing.webp";

const KAKAO_AUTHORIZE_URL = "https://kauth.kakao.com/oauth/authorize";
const KAKAO_OAUTH_STATE_KEY = "mymanito.kakao_oauth_state";
const REDIRECT_PATH_KEY = "redirectPath";

const route = useRoute();
const loginError = ref("");
const showTalkMessageNotice = ref(false);
const hasAcknowledgedTalkMessage = ref(false);

function createOAuthState() {
  const bytes = new Uint32Array(4);
  window.crypto.getRandomValues(bytes);
  return Array.from(bytes, (value) => value.toString(36)).join("");
}

function getSafeRedirect(value) {
  const redirect = Array.isArray(value) ? value[0] : value;
  return redirect?.startsWith("/") && !redirect.startsWith("//") ? redirect : null;
}

function loginWithKakao() {
  const clientId = import.meta.env.VITE_KAKAO_REST_API_KEY;
  const redirectUri = import.meta.env.VITE_KAKAO_REDIRECT_URI;

  if (!clientId || !redirectUri) {
    loginError.value = "카카오 로그인 환경 설정이 누락되었습니다.";
    return;
  }

  const state = createOAuthState();
  const redirect = getSafeRedirect(route.query.redirect);
  sessionStorage.setItem(KAKAO_OAUTH_STATE_KEY, state);
  if (redirect) {
    localStorage.setItem(REDIRECT_PATH_KEY, redirect);
  }

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

function openTalkMessageNotice() {
  loginError.value = "";
  hasAcknowledgedTalkMessage.value = false;
  showTalkMessageNotice.value = true;
}

function continueKakaoLogin() {
  if (!hasAcknowledgedTalkMessage.value) {
    return;
  }
  showTalkMessageNotice.value = false;
  loginWithKakao();
}
</script>

<template>
  <section class="flex min-h-dvh flex-col overflow-hidden bg-gradient-to-b from-amber-50 via-white to-orange-50 px-6 py-10">
    <div class="mx-auto w-full max-w-sm text-center">
      <p class="text-sm font-bold tracking-widest text-amber-500">MY MANITO</p>
      <h1 class="mt-3 text-3xl font-extrabold tracking-tight text-slate-800">
        마음을 전하는<br />
        <span class="text-amber-500">익명 마니또</span>
      </h1>
      <p class="mt-4 text-sm leading-6 text-slate-500">
        설렘은 지키고, 마음은 더 가까이.<br />
        친구들과 특별한 마니또를 시작해 보세요.
      </p>
    </div>

    <div class="flex flex-1 items-center justify-center py-6">
      <img
        :src="introducingImage"
        alt="마니또를 소개하는 다람쥐 마니"
        class="w-full max-w-xs drop-shadow-sm"
      />
    </div>

    <div class="mx-auto w-full max-w-sm">
      <button
        type="button"
        class="flex min-h-14 w-full items-center justify-center gap-2 rounded-2xl bg-[#FEE500] px-4 py-3 font-bold text-[#191919] shadow-sm transition hover:bg-[#f6dc00] focus:outline-none focus:ring-4 focus:ring-[#FEE500]/50 active:scale-[0.98]"
        @click="openTalkMessageNotice"
      >
        <svg class="h-5 w-5" viewBox="0 0 24 24" aria-hidden="true">
          <path fill="currentColor" d="M12 3C6.48 3 2 6.5 2 10.82c0 2.8 1.82 5.26 4.55 6.65l-.92 3.4c-.08.3.26.54.52.37l4.06-2.68c.58.08 1.18.12 1.79.12 5.52 0 10-3.5 10-7.82S17.52 3 12 3Z" />
        </svg>
        카카오 로그인으로 시작하기
      </button>
      <p v-if="loginError" class="mt-3 text-center text-sm text-red-600" role="alert">
        {{ loginError }}
      </p>
    </div>

    <div
      v-if="showTalkMessageNotice"
      class="fixed inset-0 z-50 flex items-end bg-slate-950/45 p-4 sm:items-center"
      role="dialog"
      aria-modal="true"
      aria-labelledby="talk-message-notice-title"
    >
      <form class="mx-auto w-full max-w-md rounded-3xl bg-white p-5 shadow-2xl" @submit.prevent="continueKakaoLogin">
        <p class="text-sm font-bold text-amber-500">카카오톡 알림 설정</p>
        <h2 id="talk-message-notice-title" class="mt-1 text-xl font-extrabold text-slate-800">
          메시지 전송 동의가 필요해요
        </h2>
        <p class="mt-3 text-sm leading-6 text-slate-600">
          다음 카카오 동의 화면에서 <strong class="text-slate-800">카카오톡 메시지 전송</strong> 항목에 동의해야
          마니또가 보낸 메시지를 카카오톡 나에게 보내기 기능을 통한 알림으로 받아볼 수 있어요.
        </p>
        <p class="mt-2 text-xs leading-5 text-amber-700">
          동의하지 않아도 로그인은 가능하지만, 카카오톡 메시지 알림은 받을 수 없습니다.
        </p>
        <label class="mt-5 flex cursor-pointer items-start gap-3 rounded-2xl bg-amber-50 p-3 text-sm leading-5 text-slate-700">
          <input v-model="hasAcknowledgedTalkMessage" type="checkbox" class="mt-0.5 h-4 w-4 rounded border-amber-300 text-amber-500 focus:ring-amber-400" />
          카카오 로그인 화면에서 메시지 전송 동의 항목을 확인하겠습니다.
        </label>
        <div class="mt-5 grid grid-cols-2 gap-3">
          <button
            type="button"
            class="rounded-xl border border-slate-200 px-4 py-3 text-sm font-bold text-slate-600"
            @click="showTalkMessageNotice = false"
          >
            나중에 할게요
          </button>
          <button
            type="submit"
            class="rounded-xl bg-[#FEE500] px-4 py-3 text-sm font-bold text-[#191919] disabled:opacity-50"
            :disabled="!hasAcknowledgedTalkMessage"
          >
            확인하고 로그인
          </button>
        </div>
      </form>
    </div>
  </section>
</template>
