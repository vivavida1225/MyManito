<script setup>
import thinkingImage from "../assets/mani_thinking.webp";

defineProps({
  isLoading: {
    type: Boolean,
    default: false,
  },
  name: {
    type: String,
    required: true,
  },
});

defineEmits(["cancel", "confirm"]);
</script>

<template>
  <div
    class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/45 p-5"
    role="dialog"
    aria-modal="true"
    aria-labelledby="claim-confirm-title"
  >
    <div class="w-full max-w-sm rounded-3xl bg-white p-6 text-center shadow-2xl">
      <img :src="thinkingImage" alt="생각에 잠긴 다람쥐 마니" class="mx-auto w-36" />
      <p class="mt-2 text-sm font-bold text-amber-500">잠깐만요!</p>
      <h2 id="claim-confirm-title" class="mt-1 text-xl font-extrabold text-slate-800">이름을 다시 확인해 주세요</h2>
      <p class="mt-4 text-sm leading-6 text-slate-600">
        정말 <strong class="font-extrabold text-slate-900">{{ name }}</strong> 님이 맞으신가요?<br />
        타인의 이름을 선택하면 게임이 꼬여요!
      </p>
      <div class="mt-6 grid grid-cols-2 gap-3">
        <button
          type="button"
          class="min-h-12 rounded-xl border border-slate-200 px-4 py-3 text-sm font-bold text-slate-600 transition hover:bg-slate-50 disabled:opacity-50"
          :disabled="isLoading"
          @click="$emit('cancel')"
        >
          다시 선택할게요
        </button>
        <button
          type="button"
          class="min-h-12 rounded-xl bg-rose-500 px-4 py-3 text-sm font-bold text-white transition hover:bg-rose-600 disabled:opacity-50"
          :disabled="isLoading"
          @click="$emit('confirm')"
        >
          네, 맞아요
        </button>
      </div>
    </div>
  </div>
</template>
