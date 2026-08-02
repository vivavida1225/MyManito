<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRouter } from "vue-router";

import api from "../api";

const props = defineProps({
  teamCode: {
    type: String,
    required: true,
  },
});

const router = useRouter();
const dashboard = ref(null);
const errorMessage = ref("");
const isLoading = ref(false);
const showEndModal = ref(false);
const confirmationCode = ref("");
const confirmationError = ref("");
const showReleaseModal = ref(false);
const releaseError = ref("");
const plannedEndDate = ref("");
const plannedEndError = ref("");
const isSavingPlannedEnd = ref(false);
const revealMode = ref("AUTO");
const revealModeError = ref("");
const isSavingRevealMode = ref(false);
const showParticipantModal = ref(false);
const showRulesModal = ref(false);
const rulesDraft = ref("");
const rulesError = ref("");
const isSavingRules = ref(false);
const showAnnouncementModal = ref(false);
const announcementMessage = ref("");
const announcementError = ref("");
const announcementStatus = ref("");
const isSendingAnnouncement = ref(false);
const browserTimeZone = Intl.DateTimeFormat().resolvedOptions().timeZone || "Asia/Seoul";

const progressPercent = computed(() => {
  if (!dashboard.value?.total_count) {
    return 0;
  }
  return Math.round((dashboard.value.claimed_count / dashboard.value.total_count) * 100);
});
const isConfirmationCodeMatched = computed(() => confirmationCode.value === props.teamCode);
const canReleaseManualResults = computed(() => (
  dashboard.value?.status === "ENDED"
  && dashboard.value?.reveal_mode === "ADMIN"
  && dashboard.value?.reveal_status === "MANUAL_PENDING"
));
const isAnyModalOpen = computed(() => (
  showEndModal.value || showReleaseModal.value || showParticipantModal.value || showRulesModal.value
  || showAnnouncementModal.value
));
let previousBodyOverflow = "";

watch(isAnyModalOpen, (isOpen) => {
  if (isOpen) {
    previousBodyOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return;
  }
  document.body.style.overflow = previousBodyOverflow;
});

async function loadDashboard() {
  errorMessage.value = "";
  isLoading.value = true;
  try {
    const response = await api.get(`/teams/${props.teamCode}/admin/dashboard/`);
    dashboard.value = response.data;
    plannedEndDate.value = dashboard.value.planned_end_date || "";
    revealMode.value = dashboard.value.reveal_mode;
  } catch (error) {
    errorMessage.value = error.response?.data?.detail || "대시보드를 불러오지 못했습니다.";
  } finally {
    isLoading.value = false;
  }
}

async function updatePlannedEnd(confirmQuizCollision = false) {
  if (!plannedEndDate.value) {
    plannedEndError.value = "종료 예정일을 입력해 주세요.";
    return;
  }

  plannedEndError.value = "";
  isSavingPlannedEnd.value = true;
  try {
    const response = await api.patch(
      `/teams/${props.teamCode}/admin/planned-end/`,
      {
        planned_end_date: plannedEndDate.value,
        planned_end_timezone: browserTimeZone,
        confirm_quiz_collision: confirmQuizCollision,
      },
    );
    dashboard.value.planned_end_date = response.data.planned_end_date;
    dashboard.value.planned_end_timezone = response.data.planned_end_timezone;
    plannedEndDate.value = response.data.planned_end_date;
  } catch (error) {
    if (
      error.response?.status === 409
      && error.response?.data?.code === "QUIZ_COLLISION_CONFIRMATION_REQUIRED"
      && !confirmQuizCollision
      && window.confirm("변경한 종료 예정일이 이미 풀이 중인 비밀 퀴즈 회차와 겹칩니다. 그래도 저장할까요?")
    ) {
      await updatePlannedEnd(true);
      return;
    }
    plannedEndError.value =
      error.response?.data?.detail ||
      error.response?.data?.planned_end_timezone?.[0] ||
      "종료 예정일을 저장하지 못했습니다.";
  } finally {
    isSavingPlannedEnd.value = false;
  }
}

async function updateRevealMode() {
  revealModeError.value = "";
  isSavingRevealMode.value = true;
  try {
    const response = await api.patch(
      `/teams/${props.teamCode}/admin/reveal-mode/`,
      { reveal_mode: revealMode.value },
    );
    dashboard.value.reveal_mode = response.data.reveal_mode;
    dashboard.value.reveal_status = response.data.reveal_status;
  } catch (error) {
    revealModeError.value = error.response?.data?.detail || "결과 공개 방식을 저장하지 못했습니다.";
  } finally {
    isSavingRevealMode.value = false;
  }
}

function openRulesEditor() {
  rulesDraft.value = dashboard.value?.rules || "";
  rulesError.value = "";
  showRulesModal.value = true;
}

async function updateTeamRules() {
  rulesError.value = "";
  isSavingRules.value = true;
  try {
    const response = await api.patch(
      `/teams/${props.teamCode}/admin/rules/`,
      { rules: rulesDraft.value },
    );
    dashboard.value.rules = response.data.rules;
    showRulesModal.value = false;
  } catch (error) {
    rulesError.value = error.response?.data?.detail || error.response?.data?.rules?.[0] || "팀 규칙을 저장하지 못했습니다.";
  } finally {
    isSavingRules.value = false;
  }
}

function openAnnouncementModal() {
  announcementMessage.value = "";
  announcementError.value = "";
  showAnnouncementModal.value = true;
}

async function sendAnnouncement() {
  if (!announcementMessage.value.trim()) {
    announcementError.value = "알림 내용을 입력해 주세요.";
    return;
  }

  announcementError.value = "";
  isSendingAnnouncement.value = true;
  try {
    const response = await api.post(
      `/teams/${props.teamCode}/admin/announcement/`,
      { message: announcementMessage.value.trim() },
    );
    announcementStatus.value = `${response.data.sent_count}명에게 팀 알림을 보냈어요.`;
    showAnnouncementModal.value = false;
  } catch (error) {
    announcementError.value = error.response?.data?.detail || error.response?.data?.message?.[0] || "팀 알림을 보내지 못했습니다.";
  } finally {
    isSendingAnnouncement.value = false;
  }
}

async function resetClaim(participant) {
  if (!window.confirm(`${participant.display_name} 님의 연결을 해제할까요?`)) {
    return;
  }

  errorMessage.value = "";
  try {
    await api.post(
      `/teams/${props.teamCode}/admin/reset-claim/`,
      { participant_id: participant.id },
    );
    await loadDashboard();
  } catch (error) {
    errorMessage.value = error.response?.data?.detail || "연결을 해제하지 못했습니다.";
  }
}

async function endGame() {
  if (!isConfirmationCodeMatched.value) {
    confirmationError.value = "팀 코드를 대소문자까지 정확히 입력해 주세요.";
    return;
  }

  errorMessage.value = "";
  confirmationError.value = "";
  isLoading.value = true;
  try {
    await api.post(
      `/teams/${props.teamCode}/admin/end/`,
      { confirmation_code: confirmationCode.value },
    );
    showEndModal.value = false;
    if (dashboard.value.reveal_mode === "ADMIN") {
      await loadDashboard();
      return;
    }
    await router.replace({ name: "team-reveal", params: { teamCode: props.teamCode } });
  } catch (error) {
    confirmationError.value = error.response?.data?.detail || error.response?.data?.confirmation_code?.[0] || "게임을 종료하지 못했습니다.";
  } finally {
    isLoading.value = false;
  }
}

async function releaseManualResults() {
  releaseError.value = "";
  isLoading.value = true;
  try {
    await api.post(`/teams/${props.teamCode}/admin/release-results/`);
    showReleaseModal.value = false;
    await loadDashboard();
  } catch (error) {
    releaseError.value = error.response?.data?.detail || error.response?.data?.confirmation_code?.[0] || "결과를 공개하지 못했습니다.";
  } finally {
    isLoading.value = false;
  }
}

onMounted(loadDashboard);
onUnmounted(() => {
  document.body.style.overflow = previousBodyOverflow;
});
</script>

<template>
  <section class="p-5">
    <div class="flex items-start justify-between gap-3">
      <div>
        <h1 class="text-xl font-bold text-slate-900">팀 관리자 대시보드</h1>
        <p class="mt-1 text-sm text-slate-600">{{ teamCode }}</p>
      </div>
      <button
        type="button"
        class="rounded-xl bg-amber-100 p-3 text-amber-800 transition hover:bg-amber-200 disabled:opacity-50"
        :disabled="!dashboard || dashboard.status !== 'ACTIVE'"
        aria-label="참여자에게 팀 알림 보내기"
        title="팀 알림 보내기"
        @click="openAnnouncementModal"
      >
        <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
          <path d="M4 11v2a2 2 0 0 0 2 2h1l2 4h2l-1.5-4H15l4 3V6l-4 3H6a2 2 0 0 0-2 2Z" stroke-linejoin="round" />
          <path d="M19 9.5a3.5 3.5 0 0 1 0 5" stroke-linecap="round" />
        </svg>
      </button>
    </div>
    <p v-if="announcementStatus" class="mt-3 text-sm font-medium text-emerald-700" role="status">{{ announcementStatus }}</p>

    <div v-if="dashboard" class="mt-6 space-y-6">
      <RouterLink
        :to="{ name: 'admin-team-quiz', params: { teamCode } }"
        class="flex items-center justify-between rounded-2xl bg-amber-50 p-5 ring-1 ring-amber-200 transition hover:bg-amber-100"
      >
        <span><span class="block font-extrabold text-slate-900">비밀 퀴즈 설정</span><span class="mt-1 block text-xs leading-5 text-slate-600">퀴즈 모드, 일정, 공통 질문과 진행 현황을 관리합니다.</span></span>
        <span class="text-xl text-amber-700" aria-hidden="true">→</span>
      </RouterLink>
      <div class="rounded-2xl bg-gradient-to-br from-amber-50 to-orange-50 p-5 ring-1 ring-amber-100">
        <div class="flex items-end justify-between">
          <p class="font-semibold text-slate-900">참여 확인 현황</p>
          <p class="text-sm text-slate-700">
            {{ dashboard.claimed_count }} / {{ dashboard.total_count }}명
          </p>
        </div>
        <div class="mt-3 h-3 overflow-hidden rounded-full bg-white shadow-inner">
          <div class="h-full rounded-full bg-gradient-to-r from-amber-400 to-orange-500 transition-all duration-500" :style="{ width: `${progressPercent}%` }" />
        </div>
        <p class="mt-2 text-right text-xs text-slate-500">{{ progressPercent }}% 완료</p>
        <div class="mt-4 grid grid-cols-2 gap-2">
          <button
            type="button"
            class="rounded-xl border border-amber-200 bg-white px-3 py-2.5 text-sm font-bold text-slate-700"
            @click="showParticipantModal = true"
          >
            참여자 관리
          </button>
          <button
            type="button"
            class="rounded-xl border border-amber-200 bg-white px-3 py-2.5 text-sm font-bold text-slate-700 disabled:opacity-50"
            :disabled="dashboard.status !== 'ACTIVE'"
            @click="openRulesEditor"
          >
            팀 규칙 수정
          </button>
        </div>
      </div>

      <form class="rounded-xl border border-slate-200 p-4" @submit.prevent="updatePlannedEnd()">
        <div class="flex items-center justify-between gap-3">
          <h2 class="font-semibold text-slate-900">게임 종료 예정일</h2>
          <span class="text-xs text-slate-400">{{ browserTimeZone }}</span>
        </div>
        <input
          v-model="plannedEndDate"
          type="date"
          class="mt-3 w-full rounded-xl border border-slate-300 px-3 py-2.5"
          :disabled="dashboard.status !== 'ACTIVE' || isSavingPlannedEnd"
        />
        <p class="mt-2 text-xs leading-5 text-slate-500">
          해당 날짜의 자정부터 D-Day!로 표시됩니다. 실제 게임 종료는 아래 종료 버튼으로만 진행됩니다.
        </p>
        <p v-if="plannedEndError" class="mt-2 text-sm text-red-600">{{ plannedEndError }}</p>
        <button
          type="submit"
          class="mt-3 w-full rounded-xl border border-slate-900 px-4 py-2.5 text-sm font-semibold text-slate-900 disabled:opacity-50"
          :disabled="dashboard.status !== 'ACTIVE' || isSavingPlannedEnd"
        >
          {{ isSavingPlannedEnd ? "저장 중..." : "종료 예정일 저장" }}
        </button>
      </form>

      <form class="rounded-xl border border-slate-200 p-4" @submit.prevent="updateRevealMode">
        <h2 class="font-semibold text-slate-900">게임 종료 후 결과 공개 방식</h2>
        <p class="mt-2 text-xs leading-5 text-slate-500">진행 중인 팀에서만 변경할 수 있으며, 게임 종료 후에는 잠깁니다.</p>
        <label class="mt-3 flex cursor-pointer gap-3 rounded-lg p-2 hover:bg-slate-50">
          <input v-model="revealMode" value="AUTO" type="radio" :disabled="dashboard.status !== 'ACTIVE' || isSavingRevealMode" />
          <span>
            <span class="block text-sm font-semibold text-slate-800">참가자에게 자동 공개</span>
            <span class="mt-1 block text-xs leading-5 text-slate-500">게임 종료 후 모든 참가자가 앱에서 자신의 결과를 확인합니다.</span>
          </span>
        </label>
        <label class="mt-2 flex cursor-pointer gap-3 rounded-lg p-2 hover:bg-slate-50">
          <input v-model="revealMode" value="ADMIN" type="radio" :disabled="dashboard.status !== 'ACTIVE' || isSavingRevealMode" />
          <span>
            <span class="block text-sm font-semibold text-slate-800">관리자가 외부에서 공개</span>
            <span class="mt-1 block text-xs leading-5 text-slate-500">종료 후 관리자만 전체 배정표를 확인하고, 외부 행사 뒤 결과를 열 수 있습니다.</span>
          </span>
        </label>
        <p v-if="revealModeError" class="mt-2 text-sm text-red-600">{{ revealModeError }}</p>
        <button
          type="submit"
          class="mt-3 w-full rounded-xl border border-slate-900 px-4 py-2.5 text-sm font-semibold text-slate-900 disabled:opacity-50"
          :disabled="dashboard.status !== 'ACTIVE' || isSavingRevealMode || revealMode === dashboard.reveal_mode"
        >
          {{ isSavingRevealMode ? "저장 중..." : "결과 공개 방식 저장" }}
        </button>
      </form>

      <button
        type="button"
        class="w-full rounded-xl bg-red-600 px-4 py-3 font-semibold text-white disabled:opacity-50"
        :disabled="dashboard.status !== 'ACTIVE'"
        @click="showEndModal = true; confirmationCode = ''; confirmationError = ''"
      >
        게임 종료 및 결과 공개
      </button>

      <div
        v-if="dashboard.reveal_assignments"
        class="rounded-xl border border-amber-200 bg-amber-50 p-4"
      >
        <h2 class="font-semibold text-slate-900">외부 공개용 전체 배정표</h2>
        <p class="mt-1 text-xs leading-5 text-slate-600">
          관리자만 볼 수 있습니다. 이 정보를 바탕으로 플랫폼 외부에서 결과를 공개해 주세요.
        </p>
        <div class="mt-3 grid grid-cols-[1fr_auto_1fr] items-center gap-3 rounded-t-lg border border-b-0 border-amber-200 bg-amber-100 px-3 py-2 text-xs font-bold text-amber-900">
          <span>마니또</span>
          <span aria-hidden="true">→</span>
          <span class="text-right">마니또가 챙겨준 사람</span>
        </div>
        <ul class="divide-y divide-amber-200 rounded-b-lg border border-amber-200 bg-white">
          <li
            v-for="assignment in dashboard.reveal_assignments"
            :key="assignment.from_name"
            class="grid grid-cols-[1fr_auto_1fr] items-center gap-3 px-3 py-2 text-sm"
          >
            <span class="font-medium text-slate-800">{{ assignment.from_name }}</span>
            <span class="text-slate-400">→</span>
            <span class="text-right font-medium text-slate-800">{{ assignment.to_name }}</span>
          </li>
        </ul>
        <button
          v-if="canReleaseManualResults"
          type="button"
          class="mt-4 w-full rounded-xl bg-violet-600 px-4 py-3 text-sm font-bold text-white disabled:opacity-50"
          :disabled="isLoading"
          @click="showReleaseModal = true; releaseError = ''"
        >
          모든 결과 확인 완료 · 참가자에게 공개하기
        </button>
        <p v-else-if="dashboard.reveal_status === 'MANUAL_RELEASED'" class="mt-4 text-center text-sm font-bold text-emerald-700">
          참가자에게 결과를 공개했습니다.
        </p>
      </div>
    </div>

    <p v-if="errorMessage" class="mt-4 text-sm text-red-600">{{ errorMessage }}</p>

    <div
      v-if="showParticipantModal"
      class="fixed inset-0 z-50 flex items-end bg-slate-950/45 p-4 sm:items-center"
      role="dialog"
      aria-modal="true"
      aria-labelledby="participant-management-title"
    >
      <div class="mx-auto max-h-[85dvh] w-full max-w-md overflow-y-auto overscroll-contain rounded-2xl bg-white p-5 shadow-xl">
        <div class="flex items-start justify-between gap-3">
          <div>
            <p class="text-sm font-bold text-amber-600">{{ dashboard.claimed_count }} / {{ dashboard.total_count }}명 확인 완료</p>
            <h2 id="participant-management-title" class="mt-1 text-lg font-bold text-slate-900">참여자 관리</h2>
          </div>
          <button
            type="button"
            class="rounded-lg p-2 text-slate-500 hover:bg-slate-100"
            aria-label="참여자 관리 닫기"
            @click="showParticipantModal = false"
          >
            ✕
          </button>
        </div>

        <div class="mt-5">
          <h3 class="font-semibold text-slate-900">아직 입장하지 않은 참여자</h3>
          <p v-if="!dashboard.unclaimed_names.length" class="mt-2 rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-500">모두 확인했습니다.</p>
          <ul v-else class="mt-2 divide-y divide-slate-200 rounded-xl border border-slate-200">
            <li v-for="name in dashboard.unclaimed_names" :key="name" class="px-4 py-3 text-sm text-slate-700">{{ name }}</li>
          </ul>
        </div>

        <div class="mt-5">
          <h3 class="font-semibold text-slate-900">확인 완료 참여자</h3>
          <ul class="mt-2 divide-y divide-slate-200 rounded-xl border border-slate-200">
            <li
              v-for="participant in dashboard.claimed_participants"
              :key="participant.id"
              class="flex items-center justify-between gap-3 px-4 py-3"
            >
              <div>
                <p class="text-sm font-medium text-slate-800">{{ participant.display_name }}</p>
                <p class="text-xs text-slate-500">카카오: {{ participant.claimed_by_nickname }}</p>
              </div>
              <button
                type="button"
                class="rounded-lg border border-red-300 px-3 py-1.5 text-xs font-semibold text-red-700 disabled:opacity-50"
                :disabled="dashboard.status !== 'ACTIVE'"
                @click="resetClaim(participant)"
              >
                연결 해제
              </button>
            </li>
          </ul>
        </div>
      </div>
    </div>

    <div
      v-if="showAnnouncementModal"
      class="fixed inset-0 z-50 flex items-end bg-slate-950/45 p-4 sm:items-center"
      role="dialog"
      aria-modal="true"
      aria-labelledby="announcement-title"
    >
      <form class="mx-auto max-h-[85dvh] w-full max-w-md overflow-y-auto overscroll-contain rounded-2xl bg-white p-5 shadow-xl" @submit.prevent="sendAnnouncement">
        <p class="text-sm font-bold text-amber-600">팀 공지</p>
        <h2 id="announcement-title" class="mt-1 text-lg font-bold text-slate-900">참여자에게 알림 보내기</h2>
        <p class="mt-2 text-sm leading-6 text-slate-600">본인 확인을 마친 참여자의 앱 내 알림함에 전달됩니다.</p>
        <textarea
          v-model="announcementMessage"
          rows="4"
          maxlength="255"
          class="mt-4 w-full rounded-xl border border-slate-300 px-3 py-3 text-sm leading-6 outline-none focus:border-amber-400 focus:ring-4 focus:ring-amber-100"
          placeholder="예: 오늘은 마니또에게 따뜻한 한마디를 건네 주세요!"
        />
        <p class="mt-1 text-right text-xs text-slate-400">{{ announcementMessage.length }} / 255</p>
        <p v-if="announcementError" class="mt-2 text-sm text-red-600" role="alert">{{ announcementError }}</p>
        <div class="mt-5 grid grid-cols-2 gap-3">
          <button
            type="button"
            class="rounded-xl border border-slate-300 px-4 py-3 text-sm font-semibold text-slate-700"
            @click="showAnnouncementModal = false; announcementError = ''"
          >
            취소
          </button>
          <button
            type="submit"
            class="rounded-xl bg-amber-400 px-4 py-3 text-sm font-bold text-amber-950 disabled:opacity-50"
            :disabled="isSendingAnnouncement"
          >
            {{ isSendingAnnouncement ? "보내는 중..." : "알림 보내기" }}
          </button>
        </div>
      </form>
    </div>

    <div
      v-if="showRulesModal"
      class="fixed inset-0 z-50 flex items-end bg-slate-950/45 p-4 sm:items-center"
      role="dialog"
      aria-modal="true"
      aria-labelledby="rules-editor-title"
    >
      <form class="mx-auto max-h-[85dvh] w-full max-w-md overflow-y-auto overscroll-contain rounded-2xl bg-white p-5 shadow-xl" @submit.prevent="updateTeamRules">
        <p class="text-sm font-bold text-amber-600">진행 중인 팀 설정</p>
        <h2 id="rules-editor-title" class="mt-1 text-lg font-bold text-slate-900">팀 규칙 수정</h2>
        <p class="mt-2 text-sm leading-6 text-slate-600">수정한 규칙은 팀 참여 화면과 팀 홈에 바로 표시됩니다.</p>
        <textarea
          v-model="rulesDraft"
          rows="10"
          maxlength="10000"
          class="mt-4 w-full rounded-xl border border-slate-300 px-3 py-3 text-sm leading-6 outline-none focus:border-amber-400 focus:ring-4 focus:ring-amber-100"
          placeholder="참여자에게 보여줄 팀 규칙을 작성해 주세요."
        />
        <p v-if="rulesError" class="mt-2 text-sm text-red-600" role="alert">{{ rulesError }}</p>
        <div class="mt-5 grid grid-cols-2 gap-3">
          <button
            type="button"
            class="rounded-xl border border-slate-300 px-4 py-3 text-sm font-semibold text-slate-700"
            @click="showRulesModal = false; rulesError = ''"
          >
            취소
          </button>
          <button
            type="submit"
            class="rounded-xl bg-amber-400 px-4 py-3 text-sm font-bold text-amber-950 disabled:opacity-50"
            :disabled="isSavingRules"
          >
            {{ isSavingRules ? "저장 중..." : "규칙 저장" }}
          </button>
        </div>
      </form>
    </div>

    <div
      v-if="showEndModal"
      class="fixed inset-0 z-50 flex items-end bg-slate-950/45 p-4 sm:items-center"
      role="dialog"
      aria-modal="true"
    >
      <form class="mx-auto max-h-[85dvh] w-full max-w-md overflow-y-auto overscroll-contain rounded-2xl bg-white p-5 shadow-xl" @submit.prevent="endGame">
        <p class="text-sm font-bold text-red-500">되돌릴 수 없는 작업</p>
        <h2 class="mt-1 text-lg font-bold text-slate-900">정말 게임을 종료할까요?</h2>
        <p class="mt-3 text-sm leading-6 text-slate-700">
          종료 후 채팅 내역과 이미지는 7일간 보관된 뒤 삭제됩니다. 계속하려면 팀 코드
          <strong>{{ teamCode }}</strong>를 똑같이 입력하세요.
        </p>
        <input
          v-model="confirmationCode"
          autocomplete="off"
          class="mt-4 w-full rounded-xl border border-slate-300 px-3 py-2.5"
          :placeholder="teamCode"
        />
        <p v-if="confirmationCode && !isConfirmationCodeMatched" class="mt-2 text-xs font-medium text-red-600">
          팀 코드가 일치하지 않습니다.
        </p>
        <p v-if="confirmationError" class="mt-2 text-sm text-red-600" role="alert">{{ confirmationError }}</p>
        <div class="mt-5 grid grid-cols-2 gap-3">
          <button
            type="button"
            class="rounded-xl border border-slate-300 px-4 py-3 font-semibold text-slate-700"
            @click="showEndModal = false; confirmationCode = ''; confirmationError = ''"
          >
            취소
          </button>
          <button
            type="submit"
            class="rounded-xl bg-red-600 px-4 py-3 font-semibold text-white disabled:opacity-50"
            :disabled="!isConfirmationCodeMatched || isLoading"
          >
            종료하기
          </button>
        </div>
      </form>
    </div>

    <div
      v-if="showReleaseModal"
      class="fixed inset-0 z-50 flex items-end bg-slate-950/45 p-4 sm:items-center"
      role="dialog"
      aria-modal="true"
    >
      <form class="mx-auto max-h-[85dvh] w-full max-w-md overflow-y-auto overscroll-contain rounded-2xl bg-white p-5 shadow-xl" @submit.prevent="releaseManualResults">
        <p class="text-sm font-bold text-violet-600">전체 배정표 확인 완료</p>
        <h2 class="mt-1 text-lg font-bold text-slate-900">참가자에게 결과를 공개할까요?</h2>
        <p class="mt-3 text-sm leading-6 text-slate-700">
          공개 후에는 모든 참가자가 앱에서 자신의 마니또 결과를 볼 수 있습니다.
        </p>
        <p v-if="releaseError" class="mt-2 text-sm text-red-600" role="alert">{{ releaseError }}</p>
        <div class="mt-5 grid grid-cols-2 gap-3">
          <button
            type="button"
            class="rounded-xl border border-slate-300 px-4 py-3 font-semibold text-slate-700"
            @click="showReleaseModal = false; releaseError = ''"
          >
            아직 확인 중
          </button>
          <button
            type="submit"
            class="rounded-xl bg-violet-600 px-4 py-3 font-semibold text-white disabled:opacity-50"
            :disabled="isLoading"
          >
            결과 공개하기
          </button>
        </div>
      </form>
    </div>
  </section>
</template>
