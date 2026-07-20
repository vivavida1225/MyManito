<script setup>
import { computed, onMounted, ref } from "vue";

import api from "../api";
import { getDefaultProfileImage } from "../assets/profiles";

const props = defineProps({
  teamCode: { type: String, required: true },
});

const leaderboard = ref(null);
const errorMessage = ref("");
const isLoading = ref(false);

const updatedLabel = computed(() => {
  if (!leaderboard.value?.updated_at) return "";
  return new Intl.DateTimeFormat("ko-KR", { dateStyle: "short", timeStyle: "short" }).format(new Date(leaderboard.value.updated_at));
});
const podiumEntries = computed(() => {
  const entries = leaderboard.value?.entries || [];
  return [
    { entry: entries[1], place: 2 },
    { entry: entries[0], place: 1 },
    { entry: entries[2], place: 3 },
  ];
});
const remainingEntries = computed(() => (leaderboard.value?.entries || []).slice(3));

async function loadLeaderboard() {
  isLoading.value = true;
  errorMessage.value = "";
  try {
    const response = await api.get(`/teams/${props.teamCode}/leaderboard/`);
    leaderboard.value = response.data;
  } catch (error) {
    errorMessage.value = error.response?.data?.detail || "리더보드를 불러오지 못했습니다.";
  } finally {
    isLoading.value = false;
  }
}

onMounted(loadLeaderboard);
</script>

<template>
  <section class="p-5 pb-10">
    <div class="flex items-start justify-between gap-4">
      <div>
        <p class="text-sm font-bold text-violet-600">{{ teamCode }}</p>
        <h1 class="mt-1 text-2xl font-extrabold text-slate-800">팀 리더보드</h1>
      </div>
      <button type="button" class="rounded-xl bg-white px-3 py-2 text-sm font-bold text-slate-600 shadow-sm ring-1 ring-slate-100 disabled:opacity-50" :disabled="isLoading" @click="loadLeaderboard">새로고침</button>
    </div>

    <p v-if="isLoading && !leaderboard" class="py-16 text-center text-sm text-slate-500">리더보드를 불러오고 있어요...</p>
    <p v-else-if="errorMessage" class="mt-8 rounded-2xl bg-red-50 p-4 text-center text-sm text-red-700">{{ errorMessage }}</p>
    <div v-else-if="leaderboard" class="mt-6">
      <section class="overflow-hidden rounded-[2rem] bg-violet-100 shadow-sm ring-1 ring-violet-100">
        <div class="bg-violet-600 px-4 pb-8 pt-5 text-center text-white">
          <p class="mx-auto inline-flex rounded-full bg-white px-6 py-2 text-lg font-extrabold text-violet-700 shadow-sm">LEADERBOARD</p>
          <p class="mt-3 text-xs font-medium text-violet-100">마지막 갱신 {{ updatedLabel }} · 매시 정각 갱신</p>

          <div class="mt-5 flex min-h-48 items-end justify-center gap-2">
            <article
              v-for="podium in podiumEntries"
              :key="podium.place"
              class="relative flex w-[30%] max-w-28 flex-col items-center rounded-t-2xl px-2 pb-4 pt-3 text-slate-800 shadow-sm"
              :class="[
                podium.place === 1 ? 'min-h-44' : 'min-h-36',
                podium.entry?.is_me ? 'bg-amber-50 ring-4 ring-amber-300' : 'bg-white',
              ]"
            >
              <template v-if="podium.entry">
                <div class="relative mt-1">
                  <img :src="getDefaultProfileImage(podium.entry.avatar_key)" :alt="`${podium.entry.game_nickname} 프로필`" class="h-14 w-14 rounded-full border-2 border-violet-100 object-cover" />
                  <svg
                    class="absolute -top-2 left-1/2 h-8 w-10 -translate-x-1/2 drop-shadow-md"
                    :class="podium.place === 1 ? 'text-amber-400' : podium.place === 2 ? 'text-slate-300' : 'text-orange-500'"
                    viewBox="0 0 32 24"
                    role="img"
                    :aria-label="podium.place === 1 ? '금관' : podium.place === 2 ? '은관' : '동관'"
                  >
                    <path fill="currentColor" stroke="#ffffff" stroke-linejoin="round" stroke-opacity="0.7" stroke-width="1.2" d="M3 20 5.5 7l6 5L16 2l4.5 10 6-5L29 20H3Z" />
                    <path fill="#ffffff" fill-opacity="0.4" d="m6.5 16 1.1-5.2 3.9 3.2 1.1 2H6.5Zm8.3-2L16 6.2l1.6 7.8h-2.8Z" />
                    <circle cx="16" cy="6" r="1.8" fill="#fff7d6" />
                  </svg>
                </div>
                <p class="mt-2 w-full truncate text-sm font-extrabold">{{ podium.entry.name }}</p>
                <p v-if="leaderboard.results_released" class="mt-0.5 w-full truncate text-xs text-slate-500">{{ podium.entry.game_nickname }}</p>
                <p v-if="leaderboard.results_released" class="mt-1 text-sm font-extrabold text-violet-700">{{ podium.entry.score }}점</p>
                <span v-if="podium.entry.is_me" class="mt-1 rounded-full bg-amber-200 px-2 py-0.5 text-[11px] font-bold text-amber-900">나</span>
              </template>
              <span v-else class="mt-7 text-sm text-slate-300">-</span>
              <span class="absolute -bottom-4 flex h-8 w-8 items-center justify-center rounded-full bg-violet-500 text-sm font-extrabold text-white ring-4 ring-violet-600">{{ podium.entry?.rank || podium.place }}</span>
            </article>
          </div>
        </div>

        <div class="space-y-3 px-4 pb-5 pt-7">
          <p class="text-center text-sm font-bold text-violet-800">
            {{ leaderboard.results_released ? "결과가 공개되어 최종 점수와 실제 이름을 함께 보여드려요." : "정확한 점수는 공개하지 않으며, 게임용 별명과 프로필로만 표시돼요." }}
          </p>
          <article
            v-for="entry in remainingEntries"
            :key="entry.game_nickname + entry.rank"
            class="flex items-center gap-3 rounded-full px-4 py-3 shadow-sm ring-1"
            :class="entry.is_me ? 'bg-amber-50 ring-amber-300' : 'bg-white ring-violet-100'"
          >
            <span class="w-7 text-center text-base font-extrabold text-violet-600">{{ entry.rank }}</span>
            <img :src="getDefaultProfileImage(entry.avatar_key)" :alt="`${entry.game_nickname} 프로필`" class="h-10 w-10 rounded-full object-cover" />
            <div class="min-w-0 flex-1">
              <p class="truncate font-extrabold text-slate-800">{{ entry.name }}</p>
              <p v-if="leaderboard.results_released" class="mt-0.5 truncate text-xs text-slate-500">{{ entry.game_nickname }}</p>
            </div>
            <div class="flex shrink-0 items-center gap-2">
              <span v-if="leaderboard.results_released" class="rounded-full bg-violet-600 px-3 py-1 text-sm font-extrabold text-white">{{ entry.score }}점</span>
              <span v-if="entry.is_me" class="rounded-full bg-amber-200 px-2 py-1 text-xs font-bold text-amber-900">나</span>
            </div>
          </article>
        </div>
      </section>
    </div>
  </section>
</template>
