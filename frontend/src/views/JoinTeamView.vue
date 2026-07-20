<script setup>
import { computed, ref } from "vue";

import api from "../api";
import celebratingImage from "../assets/mani_celebrating.webp";
import messagingImage from "../assets/mani_messaging.webp";
import waitingImage from "../assets/mani_waiting.webp";
import ClaimModal from "../components/ClaimModal.vue";
import { useAuthStore } from "../stores/auth";

const auth = useAuthStore();
const teamCode = ref("");
const team = ref(null);
const participants = ref([]);
const selectedParticipant = ref(null);
const claimResult = ref(null);
const step = ref("code");
const isLoading = ref(false);
const errorMessage = ref("");
const showClaimConfirm = ref(false);
const anonymousNickname = ref("");
const anonymousNicknameSaved = ref(false);

const myKakaoNickname = computed(() => auth.kakaoProfile?.nickname || "");

function teamPath(suffix = "") {
  return `/teams/${encodeURIComponent(teamCode.value.trim())}${suffix}`;
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
      anonymousNickname.value = assignmentResponse.data.anonymous_nickname || "";
      step.value = "result";
      return;
    }

    const response = await api.get(teamPath("/unclaimed/"));
    participants.value = response.data.participants;
    selectedParticipant.value =
      participants.value.find(
        (participant) => participant.display_name === myKakaoNickname.value,
      ) || null;

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
  } catch (error) {
    showClaimConfirm.value = false;
    errorMessage.value =
      error.response?.data?.detail || "이름 확인에 실패했습니다. 새로고침 후 다시 시도해 주세요.";
  } finally {
    isLoading.value = false;
  }
}

async function saveAnonymousNickname() {
  errorMessage.value = "";
  anonymousNicknameSaved.value = false;
  if (!anonymousNickname.value.trim()) {
    errorMessage.value = "익명 닉네임을 입력해 주세요.";
    return;
  }

  isLoading.value = true;
  try {
    await api.post(teamPath("/anonymous-nickname/"), {
      anonymous_nickname: anonymousNickname.value.trim(),
    });
    anonymousNicknameSaved.value = true;
  } catch (error) {
    errorMessage.value =
      error.response?.data?.detail || "익명 닉네임을 저장하지 못했습니다.";
  } finally {
    isLoading.value = false;
  }
}
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
      <p v-if="selectedParticipant && selectedParticipant.display_name === myKakaoNickname" class="rounded-xl bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
        카카오 닉네임과 일치하는 이름을 찾았어요. 그래도 한 번 더 확인해 주세요!
      </p>
      <div class="grid gap-2">
        <button
          v-for="participant in participants"
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
      <form class="space-y-3" @submit.prevent="saveAnonymousNickname">
        <label class="block">
          <span class="text-sm font-medium text-slate-700">채팅용 익명 닉네임</span>
          <input
            v-model="anonymousNickname"
            maxlength="50"
            class="mt-1 w-full rounded-xl border border-slate-300 px-3 py-2.5"
            placeholder="상대에게 보일 이름"
          />
          <p class="mt-2 text-xs leading-5 text-amber-700">
            실명, 이니셜, 소속 등 본인을 유추할 수 있는 닉네임은 사용하지 말아 주세요.
          </p>
        </label>
        <button
          type="submit"
          class="w-full rounded-xl border border-slate-900 px-4 py-3 font-semibold text-slate-900 disabled:opacity-50"
          :disabled="isLoading"
        >
          익명 닉네임 저장
        </button>
        <p v-if="anonymousNicknameSaved" class="text-center text-sm text-emerald-700">
          익명 닉네임을 저장했습니다.
        </p>
      </form>
      <div v-if="anonymousNicknameSaved" class="flex flex-col items-center pt-2">
        <img :src="celebratingImage" alt="축하하는 마니" class="w-56 max-w-[78%] object-contain" />
        <RouterLink
          :to="{ name: 'team-home', params: { teamCode: teamCode.trim() } }"
          class="mt-3 w-full rounded-xl bg-amber-400 px-4 py-3 text-center font-bold text-amber-950 shadow-sm"
        >
          팀 메인으로 가기
        </RouterLink>
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
