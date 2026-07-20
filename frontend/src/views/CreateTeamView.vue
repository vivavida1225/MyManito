<script setup>
import { computed, reactive, ref } from "vue";
import { useRouter } from "vue-router";

import api from "../api";
import messagingImage from "../assets/mani_messaging.webp";
import { useAuthStore } from "../stores/auth";

const router = useRouter();
const auth = useAuthStore();
const isSubmitting = ref(false);
const errorMessage = ref("");
const createdTeamCode = ref("");
const showShareNotice = ref(false);
const DEFAULT_RULES = `1) 마지막 날 전까지 내가 챙겨줄 마니또가 누구인지 누구에게도 말하거나 밝히지 않기!
2) 혹시 마니또가 누구인지 알아차려도 모른 척 넘어가기!
3) 게임 기간 동안 마니또를 최소 3번 이상 챙겨주기! (칭찬하기, 몰래 간식 주기 등)
4) ❗️필수 미션: 마니또와 말 놓기!❗️`;

const form = reactive({
  code: "",
  participantNames: "",
  rules: "",
  reciprocalRatio: 20,
  isParticipating: false,
  plannedEndDate: "",
  revealMode: "AUTO",
});

const browserTimeZone = Intl.DateTimeFormat().resolvedOptions().timeZone || "Asia/Seoul";

const myNickname = computed(() => auth.kakaoProfile?.nickname || "");
const parsedNames = computed(() =>
  form.participantNames.split(/[,\s]+/).filter(Boolean),
);
const participantCount = computed(() => parsedNames.value.length);

function writeParticipantNames(names) {
  form.participantNames = names.join("\n");
}

function handleParticipationChange() {
  const nickname = myNickname.value;
  if (!nickname) {
    form.isParticipating = false;
    errorMessage.value = "카카오 닉네임을 확인할 수 없습니다. 다시 로그인해 주세요.";
    return;
  }

  const names = parsedNames.value;
  const containsMyName = names.includes(nickname);

  if (form.isParticipating && !containsMyName) {
    if (window.confirm("명단에 본인의 이름이 없습니다. 추가할까요?")) {
      writeParticipantNames([...names, nickname]);
    } else {
      form.isParticipating = false;
    }
  }

  if (!form.isParticipating && containsMyName) {
    if (window.confirm("명단에서 본인의 이름을 제외할까요?")) {
      writeParticipantNames(names.filter((name) => name !== nickname));
    } else {
      form.isParticipating = true;
    }
  }
}

function applyDefaultRules() {
  if (form.rules && form.rules !== DEFAULT_RULES && !window.confirm("작성 중인 규칙을 기본 규칙으로 바꿀까요?")) {
    return;
  }
  form.rules = DEFAULT_RULES;
}

async function createTeam() {
  errorMessage.value = "";

  if (!form.code || /\s/.test(form.code)) {
    errorMessage.value = "팀 코드는 공백 없이 입력해 주세요.";
    return;
  }
  if (participantCount.value < 2) {
    errorMessage.value = "참여자는 최소 2명 이상이어야 합니다.";
    return;
  }
  if (!window.confirm(`총 ${participantCount.value}명이 맞습니까?`)) {
    return;
  }

  isSubmitting.value = true;
  try {
    const response = await api.post("/teams/", {
      code: form.code,
      participant_names: form.participantNames,
      rules: form.rules,
      reciprocal_ratio: Number(form.reciprocalRatio),
      is_participating: form.isParticipating,
      planned_end_date: form.plannedEndDate || null,
      planned_end_timezone: form.plannedEndDate ? browserTimeZone : "",
      reveal_mode: form.revealMode,
    });
    createdTeamCode.value = response.data.code;
    showShareNotice.value = true;
  } catch (error) {
    const details = error.response?.data;
    errorMessage.value =
      details?.detail ||
      details?.code?.[0] ||
      details?.participant_names?.[0] ||
      details?.reciprocal_ratio?.[0] ||
      "팀을 만들지 못했습니다. 입력 내용을 확인해 주세요.";
  } finally {
    isSubmitting.value = false;
  }
}

async function goToDashboard() {
  showShareNotice.value = false;
  await router.push({ name: "dashboard" });
}
</script>

<template>
  <section class="p-5 pb-10">
    <div class="flex items-center justify-between gap-4">
      <div>
        <p class="text-sm font-semibold text-amber-500">새로운 설렘 만들기</p>
        <h1 class="mt-1 text-2xl font-extrabold text-slate-800">새 팀 만들기</h1>
        <p class="mt-2 text-sm text-slate-500">우리 같이 즐거운 추억을 만들어가요.</p>
      </div>
      <img :src="messagingImage" alt="메시지를 보내는 다람쥐 마니" class="w-24 shrink-0" />
    </div>

    <form class="mt-7 space-y-5" @submit.prevent="createTeam">
      <label class="block">
        <span class="text-sm font-medium text-slate-700">팀 코드</span>
        <input
          v-model.trim="form.code"
          required
          maxlength="100"
          class="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-3 outline-none transition focus:border-amber-400 focus:ring-4 focus:ring-amber-100"
          placeholder="단체명, 우리만의 구호 등을 공백 없이 적어주세요"
        />
      </label>

      <label class="block">
        <span class="text-sm font-medium text-slate-700">참여자 명단</span>
        <textarea
          v-model="form.participantNames"
          required
          rows="7"
          class="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-3 outline-none transition focus:border-amber-400 focus:ring-4 focus:ring-amber-100"
          placeholder="쉼표, 공백 또는 줄바꿈으로 구분해 입력하세요."
        />
        <span class="mt-1 block text-xs text-slate-500">현재 {{ participantCount }}명</span>
      </label>

      <label class="flex cursor-pointer items-center gap-3 rounded-xl bg-amber-50 p-4 text-sm font-medium text-slate-700">
        <input
          v-model="form.isParticipating"
          type="checkbox"
          @change="handleParticipationChange"
        />
        나도 게임에 참여하기
      </label>

      <label class="block">
        <span class="flex items-center gap-1 text-sm font-medium text-slate-700">
          상호 지목 허용 비율 (%)
          <span
            class="inline-flex h-4 w-4 cursor-help items-center justify-center rounded-full border border-slate-400 text-[10px] text-slate-500"
            title="서로가 서로를 챙기는 쌍이 전체 참여자에서 차지할 수 있는 최대 비율입니다."
            aria-label="상호 지목은 서로가 서로를 챙기는 배정입니다."
          >
            ?
          </span>
        </span>
        <input
          v-model.number="form.reciprocalRatio"
          required
          min="0"
          max="100"
          type="number"
          aria-describedby="reciprocal-ratio-help"
          class="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-3 outline-none transition focus:border-amber-400 focus:ring-4 focus:ring-amber-100"
        />
        <span id="reciprocal-ratio-help" class="mt-1 block text-xs leading-5 text-slate-500">
          서로가 서로를 챙기는 쌍의 최대 비율이에요. 0%는 상호 지목 없음, 100%는 제한 없음이며 2명 팀은 100%가 필요해요.
        </span>
      </label>

      <div class="block">
        <span class="flex items-center justify-between gap-3">
          <label for="team-rules" class="text-sm font-medium text-slate-700">게임 규칙</label>
          <button
            type="button"
            class="rounded-lg border border-amber-300 bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-800 transition hover:bg-amber-100"
            @click="applyDefaultRules"
          >
            기본 규칙 입력
          </button>
        </span>
        <textarea
          id="team-rules"
          v-model="form.rules"
          aria-describedby="rules-help"
          rows="4"
          class="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-3 outline-none transition focus:border-amber-400 focus:ring-4 focus:ring-amber-100"
          placeholder="참여자에게 보여줄 규칙을 작성하세요."
        />
        <span id="rules-help" class="mt-1 block text-xs leading-5 text-slate-500">
          이 규칙은 팀 참여자가 입장 전 확인하는 내용이에요. 기본 규칙을 불러온 뒤 팀 상황에 맞게 자유롭게 수정할 수 있어요.
        </span>
      </div>

      <label class="block">
        <span class="text-sm font-medium text-slate-700">게임 종료 예정일 (선택)</span>
        <input
          v-model="form.plannedEndDate"
          type="date"
          class="mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-3 outline-none transition focus:border-amber-400 focus:ring-4 focus:ring-amber-100"
        />
        <span class="mt-1 block text-xs text-slate-500">
          해당 날짜 00:00부터 D-Day!로 표시돼요. 실제 게임은 관리자 종료 버튼으로만 종료할 수 있어요.
        </span>
      </label>

      <fieldset class="rounded-xl border border-slate-200 p-4">
        <legend class="px-1 text-sm font-medium text-slate-700">게임 종료 후 결과 공개 방식</legend>
        <label class="mt-2 flex cursor-pointer gap-3 rounded-lg p-2 hover:bg-slate-50">
          <input v-model="form.revealMode" value="AUTO" type="radio" />
          <span>
            <span class="block text-sm font-semibold text-slate-800">참가자에게 자동 공개</span>
            <span class="mt-1 block text-xs leading-5 text-slate-500">
              게임 종료 후 모든 참가자가 앱에서 자신의 마니또 결과를 동시에 확인합니다.
            </span>
          </span>
        </label>
        <label class="mt-2 flex cursor-pointer gap-3 rounded-lg p-2 hover:bg-slate-50">
          <input v-model="form.revealMode" value="ADMIN" type="radio" />
          <span>
            <span class="block text-sm font-semibold text-slate-800">관리자가 외부에서 공개</span>
            <span class="mt-1 block text-xs leading-5 text-slate-500">
              종료 후 전체 배정표는 관리자만 확인하며, 행사·발표 등 플랫폼 외부 방식으로 결과를 공개합니다.
            </span>
          </span>
        </label>
      </fieldset>

      <p v-if="errorMessage" class="text-sm text-red-600">{{ errorMessage }}</p>
      <button
        class="w-full rounded-2xl bg-amber-400 px-4 py-4 font-bold text-amber-950 shadow-sm transition hover:bg-amber-300 focus:outline-none focus:ring-4 focus:ring-amber-200 disabled:opacity-50"
        type="submit"
        :disabled="isSubmitting"
      >
        {{ isSubmitting ? "팀 생성 중..." : "팀 만들기" }}
      </button>
    </form>

    <div
      v-if="showShareNotice"
      class="fixed inset-0 z-50 flex items-end bg-slate-950/45 p-4 sm:items-center"
      role="dialog"
      aria-modal="true"
      aria-labelledby="share-team-title"
    >
      <div class="mx-auto w-full max-w-md rounded-3xl bg-white p-6 text-center shadow-2xl">
        <img :src="messagingImage" alt="메시지를 보내는 다람쥐 마니" class="mx-auto w-40" />
        <p class="mt-3 text-sm font-bold text-amber-500">팀 만들기 완료!</p>
        <h2 id="share-team-title" class="mt-1 text-2xl font-extrabold text-slate-800">
          팀원들에게 초대해 보세요
        </h2>
        <p class="mt-4 text-sm leading-6 text-slate-600">
          이제 팀 코드 <strong class="rounded-lg bg-amber-100 px-2 py-1 text-amber-900">{{ createdTeamCode }}</strong>를
          카카오톡, 디스코드 등으로 팀원들에게 공유하세요!
        </p>
        <button
          type="button"
          class="mt-6 w-full rounded-2xl bg-amber-400 px-4 py-3.5 font-bold text-amber-950 transition hover:bg-amber-300"
          @click="goToDashboard"
        >
          대시보드로 이동
        </button>
      </div>
    </div>
  </section>
</template>
