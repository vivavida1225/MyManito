<script setup>
import { computed, onMounted, onUnmounted, ref } from "vue";

import api from "../api";

const props = defineProps({ teamCode: { type: String, required: true } });

const quiz = ref(null);
const referenceAnswer = ref("");
const solutionDraft = ref("");
const evaluationScore = ref(3);
const isEvaluationEditing = ref(true);
const errorMessage = ref("");
const statusMessage = ref("");
const isLoading = ref(false);
const isSaving = ref(false);

const hasCurrentTask = computed(() => Boolean(
  quiz.value?.reference_task || quiz.value?.solve_task || quiz.value?.evaluation_task,
));

function formatDateTime(value) {
  if (!value) return "";
  return new Intl.DateTimeFormat("ko-KR", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function settlementLabel(kind) {
  return {
    REFERENCE_MISSING: "기준 답안 미입력 · 이번 회차 휴식",
    SOLUTION_MISSING: "풀이 미제출",
    EVALUATED: "평가 완료",
    EVALUATION_MISSING: "평가 미완료 · 자동 2점",
  }[kind] || kind;
}

async function loadQuiz() {
  isLoading.value = true;
  errorMessage.value = "";
  try {
    const response = await api.get(`/teams/${props.teamCode}/quiz/`);
    quiz.value = response.data;
    referenceAnswer.value = quiz.value.reference_task?.answer || "";
    solutionDraft.value = quiz.value.solve_task?.draft || "";
    const savedEvaluationScore = quiz.value.evaluation_task?.score;
    evaluationScore.value = savedEvaluationScore ?? 3;
    isEvaluationEditing.value = savedEvaluationScore == null;
  } catch (error) {
    errorMessage.value = error.response?.data?.detail || "비밀 퀴즈를 불러오지 못했습니다.";
  } finally {
    isLoading.value = false;
  }
}

async function confirmReference() {
  const task = quiz.value?.reference_task;
  if (!task || !referenceAnswer.value.trim()) {
    errorMessage.value = "기준 답안을 입력해 주세요.";
    return;
  }
  if (!window.confirm("정말 이 답안으로 확정할까요? 확정 후에는 바꿀 수 없습니다.")) return;
  isSaving.value = true;
  errorMessage.value = "";
  try {
    await api.post(
      `/teams/${props.teamCode}/quiz/items/${task.item_id}/reference-answer/confirm/`,
      { answer: referenceAnswer.value },
    );
    statusMessage.value = "기준 답안을 확정했어요.";
    await loadQuiz();
  } catch (error) {
    errorMessage.value = error.response?.data?.detail || "기준 답안을 확정하지 못했습니다.";
  } finally {
    isSaving.value = false;
  }
}

async function saveDraft() {
  const task = quiz.value?.solve_task;
  if (!task) return;
  isSaving.value = true;
  errorMessage.value = "";
  try {
    const response = await api.put(
      `/teams/${props.teamCode}/quiz/items/${task.item_id}/solution-draft/`,
      { answer: solutionDraft.value },
    );
    solutionDraft.value = response.data.draft || "";
    statusMessage.value = solutionDraft.value
      ? "마지막 유효 답안을 임시 저장했어요."
      : "저장된 풀이 답안이 아직 없어요.";
  } catch (error) {
    errorMessage.value = error.response?.data?.detail || "풀이 답안을 저장하지 못했습니다.";
  } finally {
    isSaving.value = false;
  }
}

async function confirmEvaluation() {
  const task = quiz.value?.evaluation_task;
  if (!task) return;
  if (task.score != null && !isEvaluationEditing.value) {
    isEvaluationEditing.value = true;
    statusMessage.value = "평가 점수를 수정할 수 있어요.";
    return;
  }
  isSaving.value = true;
  errorMessage.value = "";
  try {
    await api.post(
      `/teams/${props.teamCode}/quiz/items/${task.item_id}/evaluation/confirm/`,
      { score: evaluationScore.value },
    );
    statusMessage.value = "평가 점수를 저장했어요. 마감 전까지 수정할 수 있어요.";
    await loadQuiz();
  } catch (error) {
    errorMessage.value = error.response?.data?.detail || "평가를 확정하지 못했습니다.";
  } finally {
    isSaving.value = false;
  }
}

function handleQuizChanged(event) {
  if (!event.detail?.team_code || event.detail.team_code === props.teamCode) loadQuiz();
}

onMounted(() => {
  loadQuiz();
  window.addEventListener("realtime-quiz-changed", handleQuizChanged);
});
onUnmounted(() => window.removeEventListener("realtime-quiz-changed", handleQuizChanged));
</script>

<template>
  <section class="p-5 pb-12">
    <div class="flex items-start justify-between gap-3">
      <div>
        <p class="text-sm font-bold text-amber-500">{{ teamCode }}</p>
        <h1 class="mt-1 text-2xl font-extrabold text-slate-800">비밀 퀴즈</h1>
      </div>
      <button class="rounded-xl bg-white px-3 py-2 text-sm font-bold text-slate-600 shadow-sm" :disabled="isLoading" @click="loadQuiz">새로고침</button>
    </div>

    <p v-if="statusMessage" class="mt-4 rounded-xl bg-emerald-50 p-3 text-sm font-bold text-emerald-700" role="status">{{ statusMessage }}</p>
    <p v-if="errorMessage" class="mt-4 rounded-xl bg-red-50 p-3 text-sm text-red-700" role="alert">{{ errorMessage }}</p>
    <p v-if="isLoading && !quiz" class="py-16 text-center text-sm text-slate-500">퀴즈를 준비하고 있어요...</p>

    <div v-else-if="quiz" class="mt-6 space-y-5">
      <article v-if="quiz.reference_task" class="rounded-3xl bg-amber-50 p-5 shadow-sm ring-1 ring-amber-200">
        <p class="text-sm font-extrabold text-amber-700">{{ quiz.reference_task.question_kind === "COMMON" ? "공통 퀴즈!" : "랜덤 퀴즈!" }}</p>
        <h2 class="mt-2 text-lg font-extrabold leading-7 text-slate-800">이번 회차에 내가 입력할 기준 답안</h2>
        <p v-if="quiz.reference_task.decision_pending" class="mt-3 rounded-xl bg-white/80 p-3 text-sm font-bold text-orange-700">관리자의 회차 진행 결정을 기다리고 있어요. 답안은 미리 확정할 수 있습니다.</p>
        <p class="mt-4 rounded-2xl bg-white p-4 text-sm font-bold leading-6 text-slate-700">{{ quiz.reference_task.question }}</p>
        <textarea v-model="referenceAnswer" rows="4" :disabled="quiz.reference_task.confirmed" class="mt-3 w-full rounded-2xl border border-amber-200 bg-white p-4 text-sm leading-6 outline-none focus:ring-4 focus:ring-amber-100 disabled:bg-slate-100" placeholder="나에 관한 기준 답안을 입력해 주세요." />
        <p class="mt-2 text-xs text-slate-500">입력 마감 {{ formatDateTime(quiz.reference_task.ends_at) }}</p>
        <button v-if="!quiz.reference_task.confirmed" class="mt-4 min-h-12 w-full rounded-xl bg-amber-400 px-4 py-3 font-extrabold text-amber-950 disabled:opacity-50" :disabled="isSaving || !referenceAnswer.trim()" @click="confirmReference">정답 확정</button>
        <p v-else class="mt-4 text-center text-sm font-extrabold text-emerald-700">확정 완료 · 이 답안은 변경할 수 없어요.</p>
      </article>

      <article v-if="quiz.solve_task" class="rounded-3xl bg-sky-50 p-5 shadow-sm ring-1 ring-sky-200">
        <p class="text-sm font-extrabold text-sky-700">{{ quiz.solve_task.question_kind === "COMMON" ? "공통 퀴즈!" : "랜덤 퀴즈!" }}</p>
        <h2 class="mt-2 text-lg font-extrabold text-slate-800">{{ quiz.solve_task.target_name }} 님에 관해 풀 퀴즈</h2>
        <p class="mt-4 rounded-2xl bg-white p-4 text-sm font-bold leading-6 text-slate-700">{{ quiz.solve_task.question }}</p>
        <textarea v-model="solutionDraft" rows="4" class="mt-3 w-full rounded-2xl border border-sky-200 bg-white p-4 text-sm leading-6 outline-none focus:ring-4 focus:ring-sky-100" placeholder="정답이라고 생각하는 내용을 적어 주세요." />
        <p class="mt-2 text-xs leading-5 text-slate-500">마감 {{ formatDateTime(quiz.solve_task.ends_at) }}</p>
        <button class="mt-4 min-h-12 w-full rounded-xl bg-sky-500 px-4 py-3 font-extrabold text-white disabled:opacity-50" :disabled="isSaving" @click="saveDraft">임시 저장</button>
      </article>

      <article v-if="quiz.evaluation_task" class="rounded-3xl bg-violet-50 p-5 shadow-sm ring-1 ring-violet-200">
        <p class="text-sm font-extrabold text-violet-700">나를 챙기는 마니또의 답안</p>
        <h2 class="mt-2 text-lg font-extrabold text-slate-800">직전 회차 답안 평가</h2>
        <dl class="mt-4 space-y-3 text-sm">
          <div class="rounded-2xl bg-white p-4"><dt class="font-bold text-slate-500">질문</dt><dd class="mt-1 font-bold leading-6 text-slate-800">{{ quiz.evaluation_task.question }}</dd></div>
          <div class="rounded-2xl bg-white p-4"><dt class="font-bold text-slate-500">내 기준 답안</dt><dd class="mt-1 leading-6 text-slate-800">{{ quiz.evaluation_task.reference_answer }}</dd></div>
          <div class="rounded-2xl bg-white p-4"><dt class="font-bold text-slate-500">마니또의 풀이</dt><dd class="mt-1 leading-6 text-slate-800">{{ quiz.evaluation_task.solution_answer }}</dd></div>
        </dl>
        <fieldset class="mt-4">
          <legend class="text-sm font-extrabold text-slate-700">평가점수</legend>
          <div class="relative mt-3 px-1" role="radiogroup" aria-label="평가점수 선택">
            <div class="absolute left-[10%] right-[10%] top-5 h-1 -translate-y-1/2 rounded-full bg-violet-200" aria-hidden="true"></div>
            <div class="relative grid grid-cols-5">
              <label v-for="score in 5" :key="score" class="flex cursor-pointer justify-center" :aria-label="`${score}점`">
                <input v-model.number="evaluationScore" class="peer sr-only" type="radio" name="evaluation-score" :value="score" :disabled="!isEvaluationEditing || isSaving" />
                <span class="flex h-10 w-10 items-center justify-center rounded-full border-2 border-violet-200 bg-white text-sm font-extrabold text-slate-600 transition peer-checked:border-violet-600 peer-checked:bg-violet-600 peer-checked:text-white peer-focus-visible:ring-4 peer-focus-visible:ring-violet-200 peer-disabled:cursor-not-allowed peer-disabled:opacity-70">
                  {{ score }}
                </span>
              </label>
            </div>
          </div>
        </fieldset>
        <p v-if="quiz.evaluation_task.score != null && !isEvaluationEditing" class="mt-2 text-xs font-bold text-violet-700">{{ quiz.evaluation_task.score }}점 저장됨 · 마감 전까지 수정할 수 있어요.</p>
        <p class="mt-2 text-xs text-slate-500">평가 마감 {{ formatDateTime(quiz.evaluation_task.ends_at) }}</p>
        <button class="mt-4 min-h-12 w-full rounded-xl bg-violet-600 px-4 py-3 font-extrabold text-white disabled:opacity-50" :disabled="isSaving" @click="confirmEvaluation">
          {{ quiz.evaluation_task.score != null && !isEvaluationEditing ? "평가 수정" : "평가 저장" }}
        </button>
      </article>

      <div v-if="!hasCurrentTask" class="rounded-3xl bg-white p-6 text-center shadow-sm ring-1 ring-slate-100">
        <p class="text-3xl" aria-hidden="true">🌙</p>
        <h2 class="mt-3 text-lg font-extrabold text-slate-800">지금은 할 퀴즈가 없어요</h2>
        <p class="mt-2 text-sm leading-6 text-slate-500">새 회차가 시작되거나 평가할 답안이 생기면 알림으로 알려 드릴게요.</p>
      </div>

      <section>
        <h2 class="text-lg font-extrabold text-slate-800">내 회차별 결과</h2>
        <div v-if="quiz.history.length" class="mt-3 space-y-3">
          <article v-for="result in quiz.history" :key="result.item_id" class="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-slate-100">
            <div class="flex items-center justify-between gap-3"><p class="font-extrabold text-slate-800">{{ result.round_sequence }}회차</p><span class="rounded-full bg-slate-100 px-2 py-1 text-xs font-bold text-slate-600">{{ result.raw_score }}점 / {{ result.settlement_kind === "REFERENCE_MISSING" ? "점수율 제외" : "5점" }}</span></div>
            <p class="mt-3 text-sm font-bold leading-6 text-slate-700">{{ result.question }}</p>
            <p class="mt-2 text-xs font-bold text-violet-700">{{ settlementLabel(result.settlement_kind) }}</p>
            <p v-if="result.reference_answer" class="mt-2 text-sm text-slate-600">기준 답안: {{ result.reference_answer }}</p>
            <p v-if="result.solution_answer" class="mt-1 text-sm text-slate-600">내 풀이: {{ result.solution_answer }}</p>
          </article>
        </div>
        <p v-else class="mt-3 rounded-2xl bg-slate-50 p-4 text-sm text-slate-500">아직 정산된 퀴즈 결과가 없습니다.</p>
      </section>
    </div>
  </section>
</template>
