<script setup>
import { onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import api from "../api";
import { useAuthStore } from "../stores/auth";

const KAKAO_OAUTH_STATE_KEY = "mymanito.kakao_oauth_state";
const REDIRECT_PATH_KEY = "redirectPath";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const errorMessage = ref("");

function queryValue(value) {
  return Array.isArray(value) ? value[0] : value;
}

function getStoredRedirect() {
  const redirect = localStorage.getItem(REDIRECT_PATH_KEY);
  return redirect?.startsWith("/") && !redirect.startsWith("//") ? redirect : null;
}

onMounted(async () => {
  const code = queryValue(route.query.code);
  const returnedState = queryValue(route.query.state);
  const expectedState = sessionStorage.getItem(KAKAO_OAUTH_STATE_KEY);
  const kakaoError = queryValue(route.query.error);

  if (kakaoError) {
    errorMessage.value = "카카오 로그인이 취소되었거나 승인되지 않았습니다.";
    return;
  }

  if (!code || !expectedState || returnedState !== expectedState) {
    errorMessage.value = "유효하지 않은 카카오 로그인 요청입니다. 다시 시도해 주세요.";
    return;
  }

  sessionStorage.removeItem(KAKAO_OAUTH_STATE_KEY);

  try {
    const response = await api.post("/accounts/kakao/login/", {
      authorization_code: code,
    });

    auth.setAuthenticatedUser({
      accessToken: response.data.access,
      refreshToken: response.data.refresh,
      kakaoProfile: response.data.user,
    });
    const redirect = getStoredRedirect();
    await router.push(redirect || { name: "dashboard" });
    localStorage.removeItem(REDIRECT_PATH_KEY);
  } catch (error) {
    errorMessage.value =
      error.response?.data?.detail ||
      "로그인 처리 중 오류가 발생했습니다. 다시 시도해 주세요.";
  }
});
</script>

<template>
  <section class="flex min-h-dvh items-center justify-center bg-gradient-to-b from-amber-50 via-white to-orange-50 px-6 py-10">
    <div class="w-full max-w-sm rounded-3xl border border-amber-100 bg-white px-6 py-8 text-center shadow-sm">
      <template v-if="!errorMessage">
        <span class="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-amber-100 text-amber-600" aria-hidden="true">
          <svg class="h-6 w-6 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <path d="M20 12a8 8 0 1 1-2.34-5.66" stroke-linecap="round" />
          </svg>
        </span>
        <p class="mt-5 text-lg font-extrabold text-slate-800">로그인 정보를 확인하고 있어요</p>
        <p class="mt-2 text-sm leading-6 text-slate-500" role="status">
          잠시만 기다리면 마이마니또로 안내할게요.
        </p>
      </template>
      <template v-else>
        <span class="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-rose-50 text-rose-500" aria-hidden="true">!</span>
        <p class="mt-5 text-lg font-extrabold text-slate-800">로그인을 완료하지 못했어요</p>
        <p class="mt-2 text-sm leading-6 text-rose-600" role="alert">{{ errorMessage }}</p>
      </template>
    </div>
  </section>
</template>
