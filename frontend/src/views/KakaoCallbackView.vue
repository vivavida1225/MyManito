<script setup>
import { onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import api from "../api";
import { useAuthStore } from "../stores/auth";

const KAKAO_OAUTH_STATE_KEY = "mymanito.kakao_oauth_state";
const POST_LOGIN_REDIRECT_KEY = "mymanito.post_login_redirect";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const errorMessage = ref("");

function queryValue(value) {
  return Array.isArray(value) ? value[0] : value;
}

function getStoredRedirect() {
  const redirect = sessionStorage.getItem(POST_LOGIN_REDIRECT_KEY);
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
    sessionStorage.removeItem(POST_LOGIN_REDIRECT_KEY);
    await router.replace(redirect || { name: "dashboard" });
  } catch (error) {
    errorMessage.value =
      error.response?.data?.detail ||
      "로그인 처리 중 오류가 발생했습니다. 다시 시도해 주세요.";
  }
});
</script>

<template>
  <section class="p-5">
    <p v-if="!errorMessage" class="text-sm text-slate-600">
      카카오 로그인 정보를 확인하고 있습니다.
    </p>
    <p v-else class="text-sm text-red-600">{{ errorMessage }}</p>
  </section>
</template>
