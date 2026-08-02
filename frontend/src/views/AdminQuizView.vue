<script setup>
import { onMounted, onUnmounted, reactive, ref } from "vue";

import api from "../api";

const props = defineProps({ teamCode: { type: String, required: true } });
const browserTimeZone = Intl.DateTimeFormat().resolvedOptions().timeZone || "Asia/Seoul";
const dashboard = ref(null);
const form = reactive({ enabled: false, quiz_timezone: browserTimeZone, reference_days: 2, solve_days: 3, next_common_question: "" });
const errorMessage = ref("");
const statusMessage = ref("");
const isLoading = ref(false);
const isSaving = ref(false);

function syncForm() {
  if (!dashboard.value) return;
  form.enabled = dashboard.value.enabled;
  form.quiz_timezone = dashboard.value.quiz_timezone || browserTimeZone;
  form.reference_days = dashboard.value.reference_days;
  form.solve_days = dashboard.value.solve_days;
  form.next_common_question = dashboard.value.next_common_question || "";
}

function formatDateTime(value) {
  if (!value) return "미정";
  return new Intl.DateTimeFormat("ko-KR", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function phaseLabel(phase) {
  return {
    REFERENCE: "기준 답안",
    SOLVE: "풀이",
    EVALUATION: "평가",
    SETTLING: "정산 중",
  }[phase] || phase;
}

async function loadDashboard() {
  isLoading.value = true;
  errorMessage.value = "";
  try {
    const response = await api.get(`/teams/${props.teamCode}/admin/quiz/`);
    dashboard.value = response.data;
    syncForm();
  } catch (error) {
    errorMessage.value = error.response?.data?.detail || "퀴즈 설정을 불러오지 못했습니다.";
  } finally {
    isLoading.value = false;
  }
}

async function saveSettings() {
  if (form.reference_days + form.solve_days > 7) {
    errorMessage.value = "입력일수와 풀이일수 합계는 7일 이하여야 합니다.";
    return;
  }
  isSaving.value = true;
  errorMessage.value = "";
  try {
    const response = await api.patch(`/teams/${props.teamCode}/admin/quiz/`, { ...form });
    dashboard.value = response.data;
    syncForm();
    statusMessage.value = "비밀 퀴즈 설정을 저장했어요.";
  } catch (error) {
    errorMessage.value = error.response?.data?.detail || "퀴즈 설정을 저장하지 못했습니다.";
  } finally {
    isSaving.value = false;
  }
}

async function decide(decision) {
  const pending = dashboard.value?.pending_decision;
  const label = decision === "PROCEED" ? "진행" : "취소";
  if (!pending || !window.confirm(`이번 회차를 ${label}으로 확정할까요? 이 결정은 바꿀 수 없습니다.`)) return;
  isSaving.value = true;
  errorMessage.value = "";
  try {
    await api.post(`/teams/${props.teamCode}/admin/quiz/rounds/${pending.round_id}/decision/`, { decision });
    statusMessage.value = `이번 회차를 ${label}으로 확정했어요.`;
    await loadDashboard();
  } catch (error) {
    errorMessage.value = error.response?.data?.detail || "회차 결정을 저장하지 못했습니다.";
  } finally {
    isSaving.value = false;
  }
}

async function remindPending(round) {
  if (!round?.can_remind || round.pending_count < 1) return;
  if (!window.confirm(`${round.sequence}회차 ${phaseLabel(round.phase)} 미완료자 ${round.pending_count}명에게 알림을 다시 보낼까요? 대상 명단은 공개되지 않습니다.`)) return;
  isSaving.value = true;
  errorMessage.value = "";
  try {
    const response = await api.post(`/teams/${props.teamCode}/admin/quiz/rounds/${round.id}/remind-pending/`);
    statusMessage.value = `미완료자 ${response.data.reminded_count}명에게 재알림을 보냈어요.`;
    await loadDashboard();
  } catch (error) {
    errorMessage.value = error.response?.data?.detail || "미완료자에게 재알림을 보내지 못했습니다.";
  } finally {
    isSaving.value = false;
  }
}

function handleQuizChanged(event) {
  if (!event.detail?.team_code || event.detail.team_code === props.teamCode) loadDashboard();
}

onMounted(() => {
  loadDashboard();
  window.addEventListener("realtime-quiz-changed", handleQuizChanged);
});
onUnmounted(() => window.removeEventListener("realtime-quiz-changed", handleQuizChanged));
</script>

<template>
  <section class="p-5 pb-12">
    <div>
      <p class="text-sm font-bold text-amber-500">{{ teamCode }}</p>
      <h1 class="mt-1 text-2xl font-extrabold text-slate-800">비밀 퀴즈 설정</h1>
    </div>
    <p v-if="statusMessage" class="mt-4 rounded-xl bg-emerald-50 p-3 text-sm font-bold text-emerald-700">{{ statusMessage }}</p>
    <p v-if="errorMessage" class="mt-4 rounded-xl bg-red-50 p-3 text-sm text-red-700" role="alert">{{ errorMessage }}</p>
    <p v-if="isLoading && !dashboard" class="py-16 text-center text-sm text-slate-500">설정을 불러오고 있어요...</p>

    <div v-else-if="dashboard" class="mt-6 space-y-5">
      <form class="rounded-3xl bg-white p-5 shadow-sm ring-1 ring-slate-100" @submit.prevent="saveSettings">
        <label class="flex items-center justify-between gap-4">
          <span><span class="block font-extrabold text-slate-800">퀴즈 모드</span><span class="mt-1 block text-xs leading-5 text-slate-500">OFF로 바꿔도 이미 시작한 회차는 정산됩니다.</span></span>
          <input v-model="form.enabled" type="checkbox" class="h-6 w-6 accent-amber-500" />
        </label>
        <div class="mt-5 grid grid-cols-2 gap-3">
          <label class="text-sm font-bold text-slate-700">기준 답안 입력일수<input v-model.number="form.reference_days" type="number" min="1" max="6" class="mt-2 w-full rounded-xl border border-slate-200 px-3 py-3" /></label>
          <label class="text-sm font-bold text-slate-700">풀이일수<input v-model.number="form.solve_days" type="number" min="1" max="6" class="mt-2 w-full rounded-xl border border-slate-200 px-3 py-3" /></label>
        </div>
        <p class="mt-2 text-xs text-slate-500">회차 주기 {{ form.reference_days + form.solve_days }}일 · 최대 7일</p>
        <label class="mt-5 block text-sm font-bold text-slate-700">관리자 시간대<input v-model="form.quiz_timezone" :disabled="dashboard.timezone_locked" class="mt-2 w-full rounded-xl border border-slate-200 px-3 py-3 disabled:bg-slate-100" /></label>
        <label class="mt-5 block text-sm font-bold text-slate-700">다음 회차 공통 질문<textarea v-model="form.next_common_question" rows="4" class="mt-2 w-full rounded-xl border border-slate-200 p-3 text-sm leading-6" placeholder="비워 두면 참가자별 랜덤 질문이 배정됩니다." /></label>
        <button class="mt-5 min-h-12 w-full rounded-xl bg-amber-400 px-4 py-3 font-extrabold text-amber-950 disabled:opacity-50" :disabled="isSaving || dashboard.team_status !== 'ACTIVE'" type="submit">{{ isSaving ? "저장 중..." : "설정 저장" }}</button>
      </form>

      <article class="rounded-3xl bg-sky-50 p-5 ring-1 ring-sky-100">
        <h2 class="font-extrabold text-slate-800">다음 일정</h2>
        <p class="mt-2 text-sm text-slate-600">시작 {{ formatDateTime(dashboard.next_round_starts_at) }}</p>
        <p v-if="dashboard.next_round_collision" class="mt-3 rounded-xl bg-orange-100 p-3 text-sm font-bold text-orange-800">현재 종료 예정일과 다음 회차 풀이기간이 겹칩니다.</p>
      </article>

      <article v-if="dashboard.pending_decision" class="rounded-3xl bg-orange-50 p-5 ring-2 ring-orange-300">
        <p class="text-sm font-extrabold text-orange-700">종료 예정일 충돌</p>
        <h2 class="mt-1 text-lg font-extrabold text-slate-800">이번 회차를 진행할까요?</h2>
        <p class="mt-2 text-sm leading-6 text-slate-600">{{ formatDateTime(dashboard.pending_decision.reference_ends_at) }}까지 결정하지 않으면 자동 취소되고 퀴즈 모드가 꺼집니다.</p>
        <div class="mt-4 grid grid-cols-2 gap-3"><button class="rounded-xl border border-orange-300 bg-white px-3 py-3 text-sm font-bold text-orange-800" :disabled="isSaving" @click="decide('CANCEL')">이번 회차 취소</button><button class="rounded-xl bg-orange-500 px-3 py-3 text-sm font-extrabold text-white" :disabled="isSaving" @click="decide('PROCEED')">이번 회차 진행</button></div>
      </article>

      <article v-for="round in dashboard.rounds" :key="round.id" class="rounded-3xl bg-white p-5 shadow-sm ring-1 ring-slate-100">
        <div class="flex items-center justify-between gap-3"><h2 class="font-extrabold text-slate-800">{{ round.sequence }}회차 진행 현황</h2><span class="rounded-full bg-violet-100 px-3 py-1 text-xs font-bold text-violet-700">{{ phaseLabel(round.phase) }}</span></div>
        <dl class="mt-4 grid grid-cols-2 gap-3 text-sm">
          <div class="rounded-2xl bg-slate-50 p-4"><dt class="font-bold text-slate-500">기준 답안</dt><dd class="mt-1 text-xl font-extrabold text-slate-800">{{ round.progress.reference.completed }}/{{ round.progress.reference.total }}명</dd></div>
          <div class="rounded-2xl bg-slate-50 p-4"><dt class="font-bold text-slate-500">풀이 저장</dt><dd class="mt-1 text-xl font-extrabold text-slate-800">{{ round.progress.solution_saved.completed }}/{{ round.progress.solution_saved.total }}명</dd></div>
          <div class="rounded-2xl bg-slate-50 p-4"><dt class="font-bold text-slate-500">자동 제출</dt><dd class="mt-1 text-xl font-extrabold text-slate-800">{{ round.progress.solution_submitted.completed }}/{{ round.progress.solution_submitted.total }}명</dd></div>
          <div class="rounded-2xl bg-slate-50 p-4"><dt class="font-bold text-slate-500">평가 저장</dt><dd class="mt-1 text-xl font-extrabold text-slate-800">{{ round.progress.evaluation.completed }}/{{ round.progress.evaluation.total }}명</dd></div>
        </dl>
        <button
          v-if="round.can_remind"
          type="button"
          class="mt-4 min-h-12 w-full rounded-xl bg-violet-600 px-4 py-3 text-sm font-extrabold text-white disabled:bg-slate-200 disabled:text-slate-500"
          :disabled="isSaving || round.pending_count < 1"
          @click="remindPending(round)"
        >
          {{ round.pending_count > 0 ? `미완료자 ${round.pending_count}명에게 재알림` : "현재 단계 모두 완료" }}
        </button>
      </article>
    </div>
  </section>
</template>
