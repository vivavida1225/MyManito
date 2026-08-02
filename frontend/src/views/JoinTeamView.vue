<script setup>
import { computed, onMounted, ref } from "vue";

import api from "../api";
import waitingImage from "../assets/mani_waiting.webp";
import ClaimModal from "../components/ClaimModal.vue";
import TeamDashboardCard from "../components/TeamDashboardCard.vue";
import { useAuthStore } from "../stores/auth";

const props = defineProps({
  initialTeamCode: {
    type: String,
    default: "",
  },
  autoStart: {
    type: Boolean,
    default: false,
  },
});

const auth = useAuthStore();
const teamCode = ref(props.initialTeamCode);
const team = ref(null);
const participants = ref([]);
const selectedParticipant = ref(null);
const claimResult = ref(null);
const step = ref("code");
const isLoading = ref(false);
const errorMessage = ref("");
const showClaimConfirm = ref(false);
const dashboardTeam = ref(null);

const myKakaoNickname = computed(() => auth.kakaoProfile?.nickname || "");
const matchedParticipant = computed(
  () => participants.value.find((participant) => participant.display_name === myKakaoNickname.value) || null,
);
const otherParticipants = computed(() =>
  participants.value.filter((participant) => participant.id !== matchedParticipant.value?.id),
);
const teamDashboardCard = computed(() => dashboardTeam.value || {
  code: team.value?.code || teamCode.value.trim(),
  is_owner: false,
  status: "ACTIVE",
  claim_status: "CLAIMED",
  countdown: null,
  unread_count: 0,
});

function teamPath(suffix = "") {
  return `/teams/${encodeURIComponent(teamCode.value.trim())}${suffix}`;
}

async function loadDashboardTeam() {
  try {
    const response = await api.get("/teams/mine/");
    dashboardTeam.value = (response.data.teams || []).find(
      (item) => item.code === teamCode.value.trim(),
    ) || null;
  } catch {
    dashboardTeam.value = null;
  }
}

async function findTeam() {
  errorMessage.value = "";
  if (!teamCode.value.trim()) {
    errorMessage.value = "팀 코드를 입력해 주세요.";
    return;
  }

  isLoading.value = true;
  try {
    const response = await api.get(teamPath("/"));
    team.value = response.data;
    if (!team.value.is_joinable) {
      errorMessage.value = "현재 참여할 수 없는 팀입니다.";
      return;
    }
    step.value = "rules";
  } catch (error) {
    errorMessage.value =
      error.response?.data?.detail || "팀 정보를 불러오지 못했습니다.";
  } finally {
    isLoading.value = false;
  }
}

async function agreeAndLoadParticipants() {
  errorMessage.value = "";
  isLoading.value = true;
  try {
    const assignmentResponse = await api.get(teamPath("/my-assignment/"));
    if (assignmentResponse.data.is_claimed) {
      claimResult.value = assignmentResponse.data;
      step.value = "result";
      await loadDashboardTeam();
      return;
    }

    const response = await api.get(teamPath("/unclaimed/"));
    participants.value = response.data.participants;
    selectedParticipant.value = matchedParticipant.value;

    if (participants.value.length === 0) {
      errorMessage.value = "확인할 수 있는 미등록 이름이 없습니다.";
      return;
    }
    step.value = "claim";
  } catch (error) {
    errorMessage.value =
      error.response?.data?.detail || "참여자 명단을 불러오지 못했습니다.";
  } finally {
    isLoading.value = false;
  }
}

function requestClaim(participant) {
  selectedParticipant.value = participant;
  showClaimConfirm.value = true;
}

async function confirmClaim() {
  if (!selectedParticipant.value) {
    return;
  }

  errorMessage.value = "";
  isLoading.value = true;
  try {
    const response = await api.post(teamPath("/claim/"), {
      participant_id: selectedParticipant.value.id,
    });
    claimResult.value = response.data;
    showClaimConfirm.value = false;
    step.value = "result";
    await loadDashboardTeam();
  } catch (error) {
    showClaimConfirm.value = false;
    errorMessage.value =
      error.response?.data?.detail || "이름 확인에 실패했습니다. 새로고침 후 다시 시도해 주세요.";
  } finally {
    isLoading.value = false;
  }
}

onMounted(() => {
  if (props.autoStart && teamCode.value.trim()) {
    findTeam();
  }
});
</script>

<template>
  <section class="p-5 pb-10">
    <div class="flex items-center justify-between gap-4">
      <div>
        <p class="text-sm font-semibold text-amber-500">당신의 배정 결과는...</p>
        <h1 class="mt-1 text-2xl font-extrabold text-slate-800">팀 참여하기</h1>
      </div>
    </div>

    <form v-if="step === 'code'" class="mt-6 space-y-4" @submit.prevent="findTeam">
      <label class="block">
        <span class="text-sm font-medium text-slate-700">팀 코드</span>
        <input
          v-model.trim="teamCode"
          required
          class="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-3 outline-none transition focus:border-amber-400 focus:ring-4 focus:ring-amber-100"
          placeholder="초대받은 팀 코드"
        />
      </label>
      <button
        type="submit"
        class="w-full rounded-2xl bg-amber-400 px-4 py-4 font-bold text-amber-950 shadow-sm disabled:opacity-50"
        :disabled="isLoading"
      >
        팀 규칙 확인하기
      </button>
    </form>
    <div v-if="step === 'code'" class="mt-10 flex justify-center">
      <img :src="waitingImage" alt="팀 코드를 기다리는 마니" class="w-64 max-w-[78%] object-contain" />
    </div>

    <div v-else-if="step === 'rules'" class="mt-6 space-y-5">
      <div class="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-100">
        <h2 class="font-semibold text-slate-900">{{ team.code }} 규칙</h2>
        <p class="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-700">
          {{ team.rules || "등록된 규칙이 없습니다." }}
        </p>
      </div>
      <button
        class="w-full rounded-2xl bg-amber-400 px-4 py-4 font-bold text-amber-950 shadow-sm disabled:opacity-50"
        :disabled="isLoading"
        @click="agreeAndLoadParticipants"
      >
        동의하고 입장
      </button>
    </div>

    <div v-else-if="step === 'claim'" class="mt-6 space-y-4">
      <h2 class="text-lg font-bold text-slate-800">본인의 이름을 선택해 주세요</h2>
      <p class="text-sm leading-6 text-slate-500">선택을 완료하면 변경하기 어려우니 꼭 본인 이름인지 확인해 주세요.</p>
      <div v-if="matchedParticipant" class="rounded-2xl border border-amber-200 bg-amber-50 p-4 shadow-sm">
        <p class="text-xs font-bold text-amber-700">카카오 닉네임과 일치하는 이름</p>
        <button
          type="button"
          class="mt-2 flex w-full items-center justify-between rounded-xl bg-amber-400 px-4 py-3 text-left text-amber-950 transition hover:bg-amber-300 focus:outline-none focus:ring-4 focus:ring-amber-200"
          @click="requestClaim(matchedParticipant)"
        >
          <span>
            <span class="block text-lg font-extrabold">{{ matchedParticipant.display_name }}</span>
            <span class="mt-1 block text-sm font-medium">님으로 계속하기</span>
          </span>
          <span class="text-2xl" aria-hidden="true">→</span>
        </button>
      </div>
      <p v-if="otherParticipants.length" class="pt-2 text-sm font-bold text-slate-700">다른 이름으로 참여해야 하나요?</p>
      <div v-if="otherParticipants.length" class="grid gap-2">
        <button
          v-for="participant in otherParticipants"
          :key="participant.id"
          type="button"
          class="rounded-xl border px-4 py-3 text-left font-bold transition"
          :class="
            selectedParticipant?.id === participant.id
              ? 'border-slate-900 bg-slate-100 text-slate-900'
              : 'border-slate-300 text-slate-700'
          "
          @click="requestClaim(participant)"
        >
          {{ participant.display_name }}
        </button>
      </div>
    </div>

    <div v-else-if="step === 'result'" class="mt-6 space-y-6">
      <div class="rounded-3xl bg-gradient-to-br from-amber-100 to-orange-50 p-6 text-center">
        <p class="text-sm font-medium text-slate-600">당신이 챙겨줄 사람은...</p>
        <p class="mt-2 text-2xl font-bold text-slate-900">
          {{ claimResult.assigned_to.display_name }}
        </p>
        <p class="mt-1 text-sm text-slate-600">님입니다!</p>
      </div>
      <div>
        <p class="mb-3 text-sm font-bold text-slate-700">참여한 팀 대시보드</p>
        <TeamDashboardCard :team="teamDashboardCard" />
      </div>
    </div>

    <p v-if="errorMessage" class="mt-4 text-sm text-red-600" role="alert">{{ errorMessage }}</p>

    <ClaimModal
      v-if="showClaimConfirm && selectedParticipant"
      :name="selectedParticipant.display_name"
      :is-loading="isLoading"
      @cancel="showClaimConfirm = false"
      @confirm="confirmClaim"
    />
  </section>
</template>
