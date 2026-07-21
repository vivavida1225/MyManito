<script setup>
import { computed, onMounted, ref } from "vue";

import api from "../api";
import introducingImage from "../assets/mani_introducing_only.webp";
import runningManiImage from "../assets/mani_running_card.webp";
import thinkingImage from "../assets/mani_thinking.webp";
import waitingImage from "../assets/mani_waiting.webp";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const teams = ref([]);
const isLoading = ref(false);
const hasLoaded = ref(false);
const errorMessage = ref("");

const activeTeams = computed(() => teams.value.filter((team) => team.status === "ACTIVE"));
const managedTeams = computed(() => teams.value.filter((team) => (
  team.is_owner && (
    team.status === "ACTIVE"
    || (team.status === "ENDED" && team.reveal_mode === "ADMIN" && team.reveal_status === "MANUAL_PENDING")
  )
)));
const endedTeams = computed(() => teams.value.filter((team) => team.status === "ENDED"));

async function loadTeams() {
  errorMessage.value = "";
  isLoading.value = true;

  try {
    const response = await api.get("/teams/mine/");
    teams.value = response.data.teams || [];
  } catch (error) {
    errorMessage.value = error.response?.data?.detail || "팀 목록을 불러오지 못했습니다.";
  } finally {
    isLoading.value = false;
    hasLoaded.value = true;
  }
}

function teamDestination(team) {
  if (team.status === "ENDED" && team.result_status === "RESULT_AVAILABLE") {
    return { name: "team-reveal", params: { teamCode: team.code } };
  }

  return { name: "team-home", params: { teamCode: team.code } };
}

onMounted(loadTeams);
</script>

<template>
  <section class="p-5 pb-10">
    <p class="text-sm font-semibold text-amber-500">안녕하세요{{ auth.kakaoProfile?.nickname ? `, ${auth.kakaoProfile.nickname}님` : "" }}!</p>
    <h1 class="mt-1 text-2xl font-extrabold tracking-tight text-slate-800">오늘의 마니또</h1>
    <p class="mt-2 text-sm leading-6 text-slate-500">새 팀을 만들거나 초대 코드로 친구들의 게임에 참여해 보세요.</p>

    <div class="mt-6 grid grid-cols-2 gap-3">
      <RouterLink
        :to="{ name: 'team-create' }"
        class="flex min-h-44 flex-col items-center justify-center rounded-2xl bg-amber-400 px-3 py-4 text-center text-sm font-bold text-amber-950 shadow-sm transition hover:bg-amber-300 focus:outline-none focus:ring-4 focus:ring-amber-200"
      >
        <img :src="introducingImage" alt="마니또를 소개하는 마니" class="h-24 w-full object-contain" />
        <span class="mt-2 block">새 팀 만들기</span>
      </RouterLink>
      <RouterLink
        :to="{ name: 'team-join' }"
        class="flex min-h-44 flex-col items-center justify-center rounded-2xl border border-amber-200 bg-white px-3 py-4 text-center text-sm font-bold text-slate-700 shadow-sm transition hover:bg-amber-50 focus:outline-none focus:ring-4 focus:ring-amber-100"
      >
        <img :src="thinkingImage" alt="생각하는 마니" class="h-24 w-full object-contain" />
        <span class="mt-2 block">기존 팀 참여하기</span>
      </RouterLink>
    </div>

    <div v-if="isLoading && !hasLoaded" class="py-16 text-center text-sm text-slate-500">
      팀 목록을 불러오고 있어요...
    </div>

    <div v-else-if="errorMessage" class="mt-8 rounded-2xl border border-red-100 bg-red-50 p-4 text-center">
      <p class="text-sm text-red-700">{{ errorMessage }}</p>
      <button type="button" class="mt-3 text-sm font-bold text-red-700 underline" @click="loadTeams">다시 시도</button>
    </div>

    <div v-else-if="hasLoaded && teams.length === 0" class="mt-10 text-center">
      <img :src="waitingImage" alt="기다리고 있는 다람쥐 마니" class="mx-auto w-48" />
      <h2 class="mt-2 text-lg font-bold text-slate-800">아직 참여 중인 마니또 팀이 없어요!</h2>
      <p class="mt-2 text-sm leading-6 text-slate-500">새 팀을 만들거나 친구에게 받은 팀 코드로 참여해 보세요.</p>
    </div>

    <template v-else>
      <div v-if="activeTeams.length" class="mt-8">
        <div class="flex items-center justify-between">
          <h2 class="text-base font-bold text-slate-800">진행 중인 팀</h2>
          <span class="text-xs font-medium text-slate-400">{{ activeTeams.length }}개</span>
        </div>
        <div class="mt-3 space-y-3">
          <RouterLink
            v-for="team in activeTeams"
            :key="team.code"
            :to="teamDestination(team)"
            class="block rounded-2xl border border-amber-100 bg-white p-4 shadow-sm transition hover:border-amber-300 focus:outline-none focus:ring-4 focus:ring-amber-100"
          >
            <div class="flex items-start justify-between gap-3">
              <div>
                <p class="text-xs font-semibold text-amber-600">{{ team.is_owner ? `팀 코드 · ${team.code}` : "참여 중인 마니또 팀" }}</p>
                <p class="mt-1 font-bold text-slate-800">{{ team.is_owner ? "내가 만든 마니또 팀" : team.code }}</p>
              </div>
              <span class="rounded-full bg-amber-100 px-2 py-1 text-xs font-bold text-amber-700">
                {{ team.countdown?.remaining || "종료일 미설정" }}
              </span>
            </div>
            <div class="mt-3 flex gap-2 text-xs text-slate-500">
              <span>{{ team.claim_status === "CLAIMED" ? "본인 확인 완료" : "본인 확인 필요" }}</span>
              <span v-if="team.unread_count">· 새 메시지 {{ team.unread_count }}</span>
            </div>
          </RouterLink>
        </div>
      </div>

      <div v-if="managedTeams.length" class="mt-8">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-xs font-bold text-violet-500">내가 만든 팀 관리</p>
            <h2 class="mt-1 text-base font-bold text-slate-800">관리자 팀 현황 조회</h2>
          </div>
          <span class="rounded-full bg-violet-100 px-2 py-1 text-xs font-bold text-violet-700">{{ managedTeams.length }}개</span>
        </div>
        <p class="mt-2 text-sm leading-5 text-slate-500">참여 현황 확인, 오매칭 연결 해제, D-Day 설정과 게임 종료를 관리하세요.</p>
        <div class="mt-3 space-y-3">
          <RouterLink
            v-for="team in managedTeams"
            :key="team.code"
            :to="{ name: 'team-admin-dashboard', params: { teamCode: team.code } }"
            class="block rounded-2xl border border-violet-100 bg-gradient-to-br from-violet-50 to-white p-4 shadow-sm transition hover:border-violet-300 focus:outline-none focus:ring-4 focus:ring-violet-100"
          >
            <div class="flex items-start justify-between gap-3">
              <div>
                <p class="text-xs font-semibold text-violet-600">관리자 · 팀 코드 {{ team.code }}</p>
                <p class="mt-1 font-bold text-slate-800">{{ team.status === 'ACTIVE' ? '팀 현황 관리하기' : '결과 공개 확인이 필요해요' }}</p>
              </div>
              <span class="rounded-full bg-white px-2 py-1 text-xs font-bold text-violet-700 shadow-sm ring-1 ring-violet-100">
                {{ team.status === 'ACTIVE' ? (team.countdown?.remaining || "종료일 미설정") : "공개 대기" }}
              </span>
            </div>
            <div class="mt-4 flex items-center justify-between text-sm font-bold text-violet-700">
              <span>{{ team.status === 'ACTIVE' ? (team.unread_count ? `새 메시지 ${team.unread_count}건` : "관리자 설정 열기") : "모든 결과 확인 완료" }}</span>
              <span aria-hidden="true">→</span>
            </div>
          </RouterLink>
        </div>
      </div>

      <div v-if="endedTeams.length" class="mt-8">
        <div class="flex items-center justify-between">
          <h2 class="text-base font-bold text-slate-800">종료된 팀</h2>
          <span class="text-xs font-medium text-slate-400">결과와 채팅은 종료 후 7일간 보관돼요</span>
        </div>
        <div class="mt-3 space-y-3">
          <RouterLink
            v-for="team in endedTeams"
            :key="team.code"
            :to="teamDestination(team)"
            class="block rounded-2xl border border-slate-200 bg-white p-4 shadow-sm"
          >
            <div class="flex items-center justify-between gap-3">
              <div>
                <p class="text-xs font-semibold text-slate-400">팀 코드 · {{ team.code }}</p>
                <p class="mt-1 font-bold text-slate-700">{{ team.result_status === "RESULT_AVAILABLE" ? "마니또 결과를 확인해 보세요" : "관리자의 확인을 기다려 주세요" }}</p>
              </div>
              <img
                v-if="team.result_status === 'RESULT_AVAILABLE'"
                :src="runningManiImage"
                alt="선물을 들고 달리는 마니"
                class="h-11 w-11 object-contain"
              />
              <span v-else class="text-lg" aria-hidden="true">⏳</span>
            </div>
          </RouterLink>
        </div>
      </div>
    </template>
  </section>
</template>
