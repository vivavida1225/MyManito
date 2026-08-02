<script setup>
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRouter } from "vue-router";

import api from "../api";
import messagingImage from "../assets/mani_messaging.webp";
import waitingImage from "../assets/mani_waiting.webp";

const props = defineProps({
  teamCode: {
    type: String,
    required: true,
  },
});

const router = useRouter();
const team = ref(null);
const assignment = ref(null);
const countdown = ref(null);
const rooms = ref([]);
const leaderboard = ref(null);
const errorMessage = ref("");
const isLoading = ref(false);
const now = ref(Date.now());
let countdownTimer;

const isClaimed = computed(() => assignment.value?.is_claimed === true);
const caredForRoom = computed(() => rooms.value.find((room) => room.relationship_label === "내가 챙겨줄 사람"));
const caringForMeRoom = computed(() => rooms.value.find((room) => room.relationship_label === "나를 챙겨주는 마니또"));
const teamRules = computed(() => (team.value?.rules || "").split(/\r?\n/).map((rule) => rule.trim()).filter(Boolean));

function getTeamMidnightTimestamp(dateString, timeZone) {
  const [year, month, day] = dateString.split("-").map(Number);
  const utcGuess = Date.UTC(year, month - 1, day);
  const formatParts = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(utcGuess));
  const parts = Object.fromEntries(formatParts.map(({ type, value }) => [type, value]));
  const offset = Date.UTC(
    Number(parts.year),
    Number(parts.month) - 1,
    Number(parts.day),
    Number(parts.hour),
    Number(parts.minute),
    Number(parts.second),
  ) - utcGuess;

  return utcGuess - offset;
}

const endTimestamp = computed(() => {
  if (!countdown.value?.planned_end_date) {
    return null;
  }

  return getTeamMidnightTimestamp(
    countdown.value.planned_end_date,
    countdown.value.planned_end_timezone || "Asia/Seoul",
  );
});

const remainingTime = computed(() => {
  if (!endTimestamp.value) {
    return "종료일 미설정";
  }

  const difference = endTimestamp.value - now.value;
  if (difference <= 0) {
    return "D-Day!";
  }

  const minutes = Math.floor(difference / 60_000);
  const days = Math.floor(minutes / (60 * 24));
  const hours = Math.floor((minutes % (60 * 24)) / 60);
  const remainingMinutes = minutes % 60;
  return `${days ? `${days}일 ` : ""}${hours}시간 ${remainingMinutes}분`;
});

const endDateLabel = computed(() => {
  if (!endTimestamp.value) {
    return "관리자가 아직 종료일을 정하지 않았어요.";
  }

  return new Intl.DateTimeFormat("ko-KR", {
    dateStyle: "long",
    timeZone: countdown.value.planned_end_timezone || "Asia/Seoul",
  }).format(new Date(endTimestamp.value));
});

async function loadTeamHome() {
  isLoading.value = true;
  errorMessage.value = "";

  try {
    const response = await api.get(`/teams/${props.teamCode}/`);
    team.value = response.data;

    if (team.value.status === "ENDED") {
      await router.replace({ name: "team-reveal", params: { teamCode: props.teamCode } });
      return;
    }

    const [assignmentResult, countdownResult, roomResult, myTeamsResult, leaderboardResult] = await Promise.allSettled([
      api.get(`/teams/${props.teamCode}/my-assignment/`),
      api.get(`/teams/${props.teamCode}/countdown/`),
      api.get("/chat/rooms/"),
      api.get("/teams/mine/"),
      api.get(`/teams/${props.teamCode}/leaderboard/`),
    ]);

    if (assignmentResult.status === "fulfilled") {
      assignment.value = assignmentResult.value.data;
    }
    if (countdownResult.status === "fulfilled") {
      countdown.value = countdownResult.value.data;
    } else if (myTeamsResult.status === "fulfilled") {
      countdown.value = (myTeamsResult.value.data.teams || []).find((item) => item.code === props.teamCode)?.countdown || null;
    }
    if (roomResult.status === "fulfilled") {
      rooms.value = (roomResult.value.data.rooms || []).filter((room) => room.team_code === props.teamCode);
    }
    if (leaderboardResult.status === "fulfilled") {
      leaderboard.value = leaderboardResult.value.data;
    }
  } catch (error) {
    errorMessage.value = error.response?.data?.detail || "팀 정보를 불러오지 못했습니다.";
  } finally {
    isLoading.value = false;
  }
}

onMounted(() => {
  loadTeamHome();
  countdownTimer = window.setInterval(() => {
    now.value = Date.now();
  }, 60_000);
});

onUnmounted(() => window.clearInterval(countdownTimer));
</script>

<template>
  <section class="p-5 pb-10">
    <div>
      <p class="text-sm font-bold text-amber-500">{{ teamCode }}</p>
      <h1 class="mt-1 text-2xl font-extrabold text-slate-800">팀 대시보드</h1>
    </div>

    <p v-if="isLoading && !team" class="py-16 text-center text-sm text-slate-500">팀 정보를 불러오고 있어요...</p>

    <div v-else-if="team" class="mt-6 space-y-4">
      <div class="overflow-hidden rounded-3xl bg-gradient-to-br from-amber-400 to-orange-400 p-5 text-amber-950 shadow-sm">
        <div class="flex items-center justify-between gap-3">
          <div>
            <p class="text-sm font-bold text-amber-950/70">D-Day까지</p>
            <p class="mt-1 text-2xl font-extrabold">{{ remainingTime }}</p>
            <p class="mt-2 text-xs font-medium text-amber-950/70">{{ endDateLabel }}</p>
          </div>
        </div>
      </div>

      <RouterLink
        :to="{ name: 'team-leaderboard', params: { teamCode } }"
        class="flex items-center justify-between rounded-3xl bg-violet-50 p-5 shadow-sm ring-1 ring-violet-100 transition hover:bg-violet-100"
      >
        <span>
          <span class="block text-xl font-extrabold text-slate-800">팀 랭킹 보기</span>
          <span class="mt-1 block text-sm font-bold text-violet-600">{{ leaderboard?.my_rank ?? 0 }}위/{{ leaderboard?.my_score ?? 0 }}점</span>
        </span>
        <span class="text-xl text-violet-600" aria-hidden="true">→</span>
      </RouterLink>

      <div v-if="teamRules.length" class="rounded-2xl border border-slate-200 px-4 py-4">
        <p class="font-bold text-slate-700">📣우리 팀 규칙</p>
        <ol class="mt-3 space-y-1 text-sm font-medium leading-6 text-slate-600">
          <li v-for="(rule, index) in teamRules" :key="index" class="rounded-xl bg-slate-50 px-3 py-1">
            {{ rule }}
          </li>
        </ol>
      </div>

      <div v-else class="rounded-3xl bg-white p-5 text-center shadow-sm ring-1 ring-slate-100">
        <img :src="waitingImage" alt="기다리는 마니" class="mx-auto w-28" />
        <h2 class="mt-1 text-lg font-extrabold text-slate-800">아직 본인 확인 전이에요</h2>
        <p class="mt-2 text-sm leading-6 text-slate-500">이름을 확인하면 내가 챙겨줄 사람과 채팅방이 열려요.</p>
        <RouterLink
          :to="{ name: 'participant-claim', params: { teamCode } }"
          class="mt-4 inline-flex min-h-11 items-center justify-center rounded-xl bg-amber-400 px-4 py-2.5 text-sm font-bold text-amber-950"
        >
          내 이름 확인하기
        </RouterLink>
      </div>

      <div class="rounded-3xl bg-white p-5 shadow-sm ring-1 ring-slate-100">
        <div class="flex items-center justify-between gap-3">
          <div>
            <p class="text-sm font-bold text-sky-600">이 팀의 익명 채팅</p>
            <h2 class="mt-1 text-lg font-extrabold text-slate-800">마니또에게 메시지 보내기</h2>
          </div>
          <img :src="messagingImage" alt="메시지를 보내는 마니" class="h-16 w-16 object-contain" />
        </div>

        <div v-if="isClaimed" class="mt-4 grid gap-3">
          <RouterLink
            v-if="caredForRoom"
            :to="{ name: 'chat-room', params: { roomId: caredForRoom.room_id } }"
            class="flex items-center justify-between rounded-2xl bg-amber-50 px-4 py-4 transition hover:bg-amber-100"
          >
            <span>
              <span class="block text-sm font-extrabold text-slate-800">{{ assignment.assigned_to.display_name }} 님과의 채팅</span>
              <span class="mt-1 block text-xs text-slate-500">{{ caredForRoom.counterpart_claimed ? "지금 메시지를 보내 보세요" : "상대방의 본인 확인을 기다리고 있어요" }}</span>
            </span>
            <span class="text-xl text-amber-600" aria-hidden="true">→</span>
          </RouterLink>
          <p v-else class="rounded-2xl bg-slate-50 px-4 py-4 text-sm text-slate-500">채팅방을 준비하고 있어요.</p>

          <RouterLink
            v-if="caringForMeRoom"
            :to="{ name: 'chat-room', params: { roomId: caringForMeRoom.room_id } }"
            class="flex items-center justify-between rounded-2xl bg-sky-50 px-4 py-4 transition hover:bg-sky-100"
          >
            <span>
              <span class="block text-sm font-extrabold text-slate-800">나를 챙겨주는 마니또와의 채팅</span>
              <span class="mt-1 block text-xs text-slate-500">{{ caringForMeRoom.counterpart_claimed ? "도착한 마음을 확인해 보세요" : "상대방의 본인 확인을 기다리고 있어요" }}</span>
            </span>
            <span class="text-xl text-sky-600" aria-hidden="true">→</span>
          </RouterLink>
          <p v-else class="rounded-2xl bg-slate-50 px-4 py-4 text-sm text-slate-500">나를 챙겨줄 마니또의 채팅방을 준비하고 있어요.</p>
        </div>
        <p v-else class="mt-4 rounded-2xl bg-slate-50 px-4 py-4 text-sm leading-6 text-slate-500">본인 확인을 마치면 두 개의 익명 채팅방으로 바로 이동할 수 있어요.</p>
      </div>
    </div>

    <div v-else-if="errorMessage" class="mt-10 rounded-2xl border border-red-100 bg-red-50 p-5 text-center">
      <p class="text-sm text-red-700">{{ errorMessage }}</p>
      <button type="button" class="mt-3 text-sm font-bold text-red-700 underline" @click="loadTeamHome">다시 시도</button>
    </div>
  </section>
</template>
