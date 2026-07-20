<script setup>
import { computed, ref } from "vue";
import { useRoute } from "vue-router";

import introducingImage from "../assets/mani_introducing.webp";
import { useAuthStore } from "../stores/auth";

const activeGuide = ref("participant");
const consentError = ref("");
const route = useRoute();
const auth = useAuthStore();
const KAKAO_AUTHORIZE_URL = "https://kauth.kakao.com/oauth/authorize";
const KAKAO_OAUTH_STATE_KEY = "mymanito.kakao_oauth_state";
const REDIRECT_PATH_KEY = "redirectPath";
const needsTalkMessageConsent = computed(
  () => !auth.kakaoProfile?.kakao_scopes?.includes("talk_message"),
);

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

const participantSteps = [
  {
    title: "카카오톡으로 로그인하기",
    description: "로그인 과정에서 ‘카카오톡 메시지 전송’ 동의도 꼭 완료해 주세요. 동의하지 않으면 새 메시지 알림을 받을 수 없어요.",
  },
  {
    title: "팀 코드와 규칙 확인하기",
    description: "초대받은 팀 코드를 입력하고, 게임 규칙을 읽은 뒤 동의하고 입장해요.",
  },
  {
    title: "내 이름을 정확히 확인하기",
    description: "카카오 닉네임과 같은 이름은 추천 카드로 먼저 보여요. 그래도 반드시 한 번 더 확인해 주세요. 다른 사람의 이름을 선택하면 게임 진행이 꼬일 수 있어요.",
  },
  {
    title: "내가 챙겨줄 사람과 익명 프로필 설정하기",
    description: "배정 결과에서는 내가 챙겨줄 사람만 확인할 수 있어요. 채팅 전에는 실명, 이니셜, 소속처럼 나를 유추할 수 있는 표현을 피해 익명 닉네임과 프로필을 정해 주세요.",
  },
  {
    title: "두 개의 익명 채팅방 이용하기",
    description: "‘내가 챙겨줄 사람’과 ‘나를 챙겨주는 마니또’ 방에서 각각 대화할 수 있어요. 채팅 목록의 팀 코드와 최근 메시지를 확인해 원하는 방으로 들어가세요.",
  },
  {
    title: "게임 종료 후 결과 확인하기",
    description: "관리자가 게임을 종료하면 결과 공개 방식에 따라 내 마니또와 내가 챙겨준 사람이 공개돼요. 종료된 채팅방과 대화는 7일 동안만 유지됩니다.",
  },
  {
    title: "익명 리더보드 즐기기",
    description: "채팅, 좋아요, 팀 접속 활동은 서버에서만 점수로 반영돼요. 정확한 점수는 공개하지 않고 순위는 매시 정각에 갱신되며, 결과가 공개된 뒤에만 실제 이름과 게임 별명이 함께 보여요.",
  },
];

const adminSteps = [
  {
    title: "팀 만들기",
    description: "공백 없는 팀 코드와 참가자 명단을 입력해요. 동명이인은 ‘김민수A’, ‘김민수B’처럼 구분해 등록해 주세요.",
  },
  {
    title: "규칙·종료 예정일·공개 방식 정하기",
    description: "팀 규칙과 종료 예정일을 정하고, 종료 뒤 자동 공개할지 외부 행사 후 관리자가 공개할지 선택해요. 진행 중인 팀에서는 종료 예정일과 공개 방식을 변경할 수 있어요.",
  },
  {
    title: "팀 코드 공유하기",
    description: "팀 생성 뒤 표시되는 팀 코드를 카카오톡, 디스코드, 단체 채팅방 등으로 팀원에게 전달해 주세요.",
  },
  {
    title: "참여 확인 현황 살피기",
    description: "관리자 대시보드에서 참여 진행률과 아직 입장하지 않은 참가자를 보고 참여를 독려할 수 있어요. 진행 중에는 관리자도 다른 사람의 배정 결과를 볼 수 없어요.",
  },
  {
    title: "잘못된 본인 확인 바로잡기",
    description: "참가자가 다른 사람의 이름으로 입장했다면, 확인 완료 참여자 목록에서 연결 해제를 눌러 다시 본인 확인하도록 안내해 주세요.",
  },
  {
    title: "게임 종료와 결과 공개",
    description: "게임 종료는 팀 코드를 다시 입력해야 실행돼요. 자동 공개 방식은 바로 모든 참가자에게 결과를 공개하고, 외부 공개 방식은 관리자만 전체 배정표를 확인한 뒤 이후에 ‘참가자에게 공개하기’를 눌러요.",
  },
];
</script>

<template>
  <section class="p-5 pb-10">
    <img :src="introducingImage" alt="마이마니또 이용 가이드" class="mx-auto w-72 max-w-full object-contain" />

    <aside class="mt-6 rounded-2xl border border-amber-200 bg-amber-50 p-4" aria-labelledby="kakao-notification-guide">
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

    <div class="mt-6 grid grid-cols-2 gap-2 rounded-2xl bg-slate-100 p-1.5" role="tablist" aria-label="이용자 유형 선택">
      <button
        type="button"
        class="rounded-xl px-3 py-3 text-sm font-bold transition"
        :class="activeGuide === 'participant' ? 'bg-white text-amber-700 shadow-sm' : 'text-slate-500'"
        role="tab"
        :aria-selected="activeGuide === 'participant'"
        @click="activeGuide = 'participant'"
      >
        참여자 가이드
      </button>
      <button
        type="button"
        class="rounded-xl px-3 py-3 text-sm font-bold transition"
        :class="activeGuide === 'admin' ? 'bg-white text-amber-700 shadow-sm' : 'text-slate-500'"
        role="tab"
        :aria-selected="activeGuide === 'admin'"
        @click="activeGuide = 'admin'"
      >
        팀 관리자 가이드
      </button>
    </div>

    <div class="mt-6">
      <div v-if="activeGuide === 'participant'">
        <p class="text-sm font-bold text-sky-600">참여자 흐름</p>
        <h2 class="mt-1 text-xl font-extrabold text-slate-800">초대받은 팀에서 설렘을 시작해요</h2>
        <ol class="mt-4 space-y-3">
          <li v-for="(step, index) in participantSteps" :key="step.title" class="flex gap-3 rounded-2xl bg-white p-4 shadow-sm ring-1 ring-slate-100">
            <span class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-amber-100 text-sm font-extrabold text-amber-800">{{ index + 1 }}</span>
            <div>
              <h3 class="font-bold text-slate-800">{{ step.title }}</h3>
              <p class="mt-1 text-sm leading-6 text-slate-600">{{ step.description }}</p>
            </div>
          </li>
        </ol>
      </div>

      <div v-else>
        <p class="text-sm font-bold text-violet-600">팀 관리자 흐름</p>
        <h2 class="mt-1 text-xl font-extrabold text-slate-800">공정한 게임을 안전하게 운영해요</h2>
        <ol class="mt-4 space-y-3">
          <li v-for="(step, index) in adminSteps" :key="step.title" class="flex gap-3 rounded-2xl bg-white p-4 shadow-sm ring-1 ring-slate-100">
            <span class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-violet-100 text-sm font-extrabold text-violet-700">{{ index + 1 }}</span>
            <div>
              <h3 class="font-bold text-slate-800">{{ step.title }}</h3>
              <p class="mt-1 text-sm leading-6 text-slate-600">{{ step.description }}</p>
            </div>
          </li>
        </ol>
      </div>
    </div>
  </section>
</template>
