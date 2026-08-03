<script setup>
import { onMounted, onUnmounted, reactive, ref } from "vue";

import api from "../api";

const props = defineProps({ teamCode: { type: String, required: true } });
const dashboard = ref(null);
const rotationClockHours = Array.from({ length: 12 }, (_, index) => index + 1);
const form = reactive({ enabled: false, rotation_hour: 12, reference_days: 2, solve_days: 3, next_common_question: "" });
const errorMessage = ref("");
const statusMessage = ref("");
const isLoading = ref(false);
const isSaving = ref(false);
const activeHelp = ref("");
const isRotationPickerOpen = ref(false);
const rotationPeriod = ref("PM");

function toggleHelp(name) {
  isRotationPickerOpen.value = false;
  activeHelp.value = activeHelp.value === name ? "" : name;
}

function closeOverlays() {
  activeHelp.value = "";
  isRotationPickerOpen.value = false;
}

function rotationPeriodForHour(hour) {
  return hour < 12 ? "AM" : "PM";
}

function toggleRotationPicker() {
  const willOpen = !isRotationPickerOpen.value;
  activeHelp.value = "";
  if (willOpen) rotationPeriod.value = rotationPeriodForHour(form.rotation_hour);
  isRotationPickerOpen.value = willOpen;
}

function rotationHourForPeriod(clockHour) {
  const hour = clockHour % 12;
  return rotationPeriod.value === "PM" ? hour + 12 : hour;
}

function selectRotationHour(clockHour) {
  form.rotation_hour = rotationHourForPeriod(clockHour);
  isRotationPickerOpen.value = false;
}

function isRotationHourSelected(clockHour) {
  return form.rotation_hour === rotationHourForPeriod(clockHour);
}

function syncForm() {
  if (!dashboard.value) return;
  form.enabled = dashboard.value.enabled;
  form.rotation_hour = dashboard.value.rotation_hour ?? 12;
  rotationPeriod.value = rotationPeriodForHour(form.rotation_hour);
  form.reference_days = dashboard.value.reference_days;
  form.solve_days = dashboard.value.solve_days;
  form.next_common_question = dashboard.value.next_common_question || "";
}

function formatDateTime(value) {
  if (!value) return "미정";
  return new Intl.DateTimeFormat("ko-KR", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function formatRotationHour(hour) {
  if (hour === 0) return "오전 12시";
  if (hour === 12) return "오후 12시";
  return hour < 12 ? `오전 ${hour}시` : `오후 ${hour - 12}시`;
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
  <section class="p-5 pb-12" @pointerdown="closeOverlays">
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
          <div class="relative">
            <div class="flex items-center justify-between gap-1.5 text-sm font-bold text-slate-700">
              <label for="reference-days">기준 답안 입력일수</label>
              <div class="relative shrink-0">
                <button
                  type="button"
                  class="inline-flex h-5 w-5 items-center justify-center rounded-full border border-slate-400 text-xs font-bold leading-none text-slate-500 focus:outline-none focus:ring-2 focus:ring-amber-300"
                  aria-label="기준 답안 입력일수 도움말"
                  aria-controls="reference-days-help"
                  :aria-expanded="activeHelp === 'reference'"
                  @pointerdown.stop
                  @click="toggleHelp('reference')"
                  @keydown.esc.stop="activeHelp = ''"
                >
                  i
                </button>
                <div
                  v-if="activeHelp === 'reference'"
                  id="reference-days-help"
                  role="tooltip"
                  class="absolute left-1/2 top-7 z-20 w-64 max-w-[calc(100vw-3rem)] -translate-x-1/2 rounded-xl bg-slate-800 px-3 py-2 text-xs font-medium leading-5 text-white shadow-lg"
                  @pointerdown.stop
                >
                  <span aria-hidden="true" class="absolute -top-1 left-1/2 h-2 w-2 -translate-x-1/2 rotate-45 bg-slate-800"></span>
                  다음에 마니또가 풀 문제의 답안을 미리 입력하고, 이전 단계에서 마니또가 푼 문제를 채점하는 기간이에요.
                </div>
              </div>
            </div>
            <input id="reference-days" v-model.number="form.reference_days" type="number" min="1" max="6" class="mt-2 w-full rounded-xl border border-slate-200 px-3 py-3" />
          </div>
          <div class="relative">
            <div class="flex items-center justify-between gap-1.5 text-sm font-bold text-slate-700">
              <label for="solve-days">풀이일수</label>
              <div class="relative shrink-0">
                <button
                  type="button"
                  class="inline-flex h-5 w-5 items-center justify-center rounded-full border border-slate-400 text-xs font-bold leading-none text-slate-500 focus:outline-none focus:ring-2 focus:ring-amber-300"
                  aria-label="풀이일수 도움말"
                  aria-controls="solve-days-help"
                  :aria-expanded="activeHelp === 'solve'"
                  @pointerdown.stop
                  @click="toggleHelp('solve')"
                  @keydown.esc.stop="activeHelp = ''"
                >
                  i
                </button>
                <div
                  v-if="activeHelp === 'solve'"
                  id="solve-days-help"
                  role="tooltip"
                  class="absolute right-0 top-7 z-20 w-64 max-w-[calc(100vw-3rem)] rounded-xl bg-slate-800 px-3 py-2 text-xs font-medium leading-5 text-white shadow-lg"
                  @pointerdown.stop
                >
                  <span aria-hidden="true" class="absolute -top-1 right-1.5 h-2 w-2 rotate-45 bg-slate-800"></span>
                  상대방이 낸 문제에 대한 답안을 입력해야 하는 기간이에요.
                </div>
              </div>
            </div>
            <input id="solve-days" v-model.number="form.solve_days" type="number" min="1" max="6" class="mt-2 w-full rounded-xl border border-slate-200 px-3 py-3" />
          </div>
        </div>
        <p class="mt-2 text-xs text-slate-500">회차 주기 {{ form.reference_days + form.solve_days }}일 · 최대 7일</p>
        <div class="mt-5 text-sm font-bold text-slate-700">
          <span>기준 시간</span>
          <div class="relative mt-2">
            <button
              type="button"
              class="flex min-h-12 w-full items-center justify-between rounded-xl border border-slate-200 bg-white px-4 py-3 text-left text-sm font-bold text-slate-700 focus:outline-none focus:ring-4 focus:ring-amber-100 disabled:bg-slate-100 disabled:text-slate-500"
              :disabled="dashboard.rotation_hour_locked"
              aria-haspopup="dialog"
              aria-controls="rotation-hour-picker"
              :aria-expanded="isRotationPickerOpen"
              :aria-label="`기준 시간: ${formatRotationHour(form.rotation_hour)}`"
              @pointerdown.stop
              @click="toggleRotationPicker"
              @keydown.esc.stop="isRotationPickerOpen = false"
            >
              <span>{{ formatRotationHour(form.rotation_hour) }}</span>
              <svg aria-hidden="true" class="h-5 w-5 transition-transform" :class="{ 'rotate-180': isRotationPickerOpen }" viewBox="0 0 20 20" fill="none">
                <path d="m5 7.5 5 5 5-5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
              </svg>
            </button>

            <div
              v-if="isRotationPickerOpen"
              id="rotation-hour-picker"
              role="dialog"
              aria-label="기준 시간 선택"
              class="absolute left-0 right-0 top-full z-30 mt-2 rounded-2xl border border-slate-200 bg-white p-3 shadow-xl"
              @pointerdown.stop
              @keydown.esc.stop="isRotationPickerOpen = false"
            >
              <div class="grid grid-cols-2 gap-1 rounded-xl bg-slate-100 p-1" role="group" aria-label="오전 또는 오후 선택">
                <button
                  v-for="period in ['AM', 'PM']"
                  :key="period"
                  type="button"
                  class="min-h-12 rounded-lg px-3 py-2 text-sm font-extrabold transition"
                  :class="rotationPeriod === period ? 'bg-white text-amber-700 shadow-sm' : 'text-slate-500'"
                  :aria-pressed="rotationPeriod === period"
                  @click="rotationPeriod = period"
                >
                  {{ period === "AM" ? "오전" : "오후" }}
                </button>
              </div>
              <div class="mt-3 grid grid-cols-4 gap-2" role="group" aria-label="시간 선택">
                <button
                  v-for="hour in rotationClockHours"
                  :key="hour"
                  type="button"
                  class="min-h-12 rounded-xl px-2 py-2 text-sm font-extrabold transition focus:outline-none focus:ring-2 focus:ring-amber-300"
                  :class="isRotationHourSelected(hour) ? 'bg-amber-400 text-amber-950' : 'bg-slate-50 text-slate-700 hover:bg-amber-50'"
                  :aria-pressed="isRotationHourSelected(hour)"
                  @click="selectRotationHour(hour)"
                >
                  {{ hour }}시
                </button>
              </div>
            </div>
          </div>
          <span class="mt-2 block text-xs font-normal leading-5 text-slate-500">
            <template v-if="dashboard.rotation_hour_locked">진행 중인 회차가 끝나면 변경할 수 있어요.</template>
            <template v-else>{{ dashboard.quiz_timezone }} 기준 매일 {{ formatRotationHour(form.rotation_hour) }}에 퀴즈 날짜가 바뀌어요.</template>
          </span>
        </div>
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
