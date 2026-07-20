<script setup>
import { onMounted, onUnmounted, ref } from "vue";
import confetti from "canvas-confetti";

import api from "../api";
import celebratingImage from "../assets/mani_celebrating.webp";
import waitingImage from "../assets/mani_waiting.webp";

const props = defineProps({
  teamCode: {
    type: String,
    required: true,
  },
});

const result = ref(null);
const errorMessage = ref("");
const isExternalReveal = ref(false);
let secondConfettiTimer;

function celebrate() {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    return;
  }

  const options = {
    particleCount: 90,
    spread: 80,
    startVelocity: 32,
    scalar: 0.85,
    origin: { y: 0.58 },
  };
  confetti({ ...options, origin: { x: 0.25, y: 0.58 } });
  secondConfettiTimer = window.setTimeout(() => {
    confetti({ ...options, origin: { x: 0.75, y: 0.58 } });
  }, 240);
}

onMounted(async () => {
  try {
    const response = await api.get(`/teams/${props.teamCode}/result/`);
    result.value = response.data;
    celebrate();
  } catch (error) {
    isExternalReveal.value = error.response?.data?.reveal_mode === "ADMIN";
    errorMessage.value = error.response?.data?.detail || "결과를 불러오지 못했습니다.";
  }
});

onUnmounted(() => window.clearTimeout(secondConfettiTimer));
</script>

<template>
  <section class="result-screen flex h-[calc(100dvh-4rem)] overflow-hidden items-center bg-gradient-to-b from-amber-100 via-rose-50 to-sky-100 p-5 text-center">
    <div v-if="result" class="w-full rounded-3xl bg-white/95 p-6 shadow-xl ring-1 ring-white sm:p-7">
      <p class="text-3xl" aria-hidden="true">🎉</p>
      <h1 class="mt-2 text-2xl font-extrabold text-slate-900">마니또 결과 공개</h1>
      <img :src="celebratingImage" alt="축하하는 마니" class="mx-auto mt-3 w-52" />

      <div class="mt-3 rounded-2xl bg-rose-50 px-4 py-5">
        <p class="text-sm font-semibold text-rose-700">나를 챙겨준 마니또는</p>
        <p class="mt-2 text-2xl font-extrabold text-rose-600"><span class="text-3xl">{{ result.cared_for_me }}</span> 님이었습니다!</p>
      </div>
      <div class="mt-3 rounded-2xl bg-amber-50 px-4 py-5">
        <p class="text-sm font-semibold text-amber-700">내가 챙겨준 사람은</p>
        <p class="mt-2 text-2xl font-extrabold text-amber-700"><span class="text-3xl">{{ result.i_cared_for }}</span> 님이었습니다!</p>
      </div>
      <p class="mt-8 text-sm leading-6 text-slate-600">
        함께해 주셔서 고마워요!
      </p>
      <RouterLink
        :to="{ name: 'dashboard' }"
        class="mt-6 inline-flex min-h-12 w-full items-center justify-center rounded-xl bg-slate-900 px-4 py-3 text-sm font-bold text-white transition hover:bg-slate-800"
      >
        메인으로 돌아가기
      </RouterLink>
    </div>
    <div v-else-if="isExternalReveal" class="w-full rounded-3xl bg-white/90 p-7 shadow-xl">
      <img :src="waitingImage" alt="기다리는 마니" class="mx-auto w-24 object-contain" />
      <h1 class="mt-4 text-2xl font-bold text-slate-900">결과 공개를 기다려 주세요</h1>
      <p class="mt-4 text-sm leading-6 text-slate-600">{{ errorMessage }}</p>
    </div>
    <p v-else-if="errorMessage" class="w-full text-sm text-red-700">{{ errorMessage }}</p>
    <p v-else class="w-full text-sm text-slate-600">결과를 준비하고 있습니다.</p>
  </section>
</template>

<style scoped>
@media (max-height: 700px) {
  .result-screen {
    align-items: flex-start;
    overflow-y: auto;
  }
}
</style>
