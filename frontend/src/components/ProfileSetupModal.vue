<script setup>
import { ref, watch } from "vue";

import { DEFAULT_PROFILE_OPTIONS } from "../assets/profiles/index.js";

const props = defineProps({
  initialProfile: {
    type: Object,
    default: () => ({}),
  },
  isSaving: {
    type: Boolean,
    default: false,
  },
  errorMessage: {
    type: String,
    default: "",
  },
});

const emit = defineEmits(["cancel", "save"]);
const nickname = ref("");
const avatarKey = ref("mani-0");
const avatarOptions = DEFAULT_PROFILE_OPTIONS;

function syncProfile() {
  nickname.value = props.initialProfile?.nickname || "";
  avatarKey.value = props.initialProfile?.avatar_key === "default"
    ? "mani-0"
    : props.initialProfile?.avatar_key || "mani-0";
}

function submit() {
  emit("save", {
    nickname: nickname.value.trim(),
    avatarKey: avatarKey.value,
  });
}

watch(() => props.initialProfile, syncProfile, { immediate: true, deep: true });
</script>

<template>
  <div
    class="fixed inset-0 z-50 flex items-end bg-slate-950/45 p-4 sm:items-center"
    role="dialog"
    aria-modal="true"
    aria-labelledby="profile-setup-title"
  >
    <form class="mx-auto w-full max-w-md rounded-3xl bg-white p-5 shadow-2xl" @submit.prevent="submit">
      <p class="text-sm font-bold text-amber-500">이 방에서만 사용하는 프로필</p>
      <h2 id="profile-setup-title" class="mt-1 text-xl font-extrabold text-slate-800">익명 프로필 설정</h2>
      <p class="mt-2 text-sm leading-6 text-slate-500">상대방에게만 보이는 닉네임과 사진이에요.</p>

      <label class="mt-5 block">
        <span class="text-sm font-bold text-slate-700">익명 닉네임</span>
        <input
          v-model="nickname"
          required
          maxlength="50"
          class="mt-2 w-full rounded-xl border border-slate-200 px-3 py-3 text-sm outline-none transition focus:border-amber-400 focus:ring-4 focus:ring-amber-100"
          placeholder="상대에게 보일 이름"
        />
      </label>

      <fieldset class="mt-5">
        <legend class="text-sm font-bold text-slate-700">프로필 사진</legend>
        <div class="mt-3 grid grid-cols-6 gap-2">
          <button
            v-for="avatar in avatarOptions"
            :key="avatar.key"
            type="button"
            class="rounded-full p-0.5 transition focus:outline-none focus:ring-2 focus:ring-amber-400"
            :class="avatarKey === avatar.key ? 'bg-amber-400 ring-2 ring-amber-400 ring-offset-2' : 'hover:bg-amber-100'"
            :aria-label="avatar.label"
            :aria-pressed="avatarKey === avatar.key"
            @click="avatarKey = avatar.key"
          >
            <img :src="avatar.image" :alt="avatar.label" class="h-[42px] w-[42px] rounded-full object-contain" />
          </button>
        </div>
      </fieldset>

      <p v-if="errorMessage" class="mt-3 text-sm text-red-600" role="alert">{{ errorMessage }}</p>
      <div class="mt-6 grid grid-cols-2 gap-3">
        <button
          type="button"
          class="min-h-12 rounded-xl border border-slate-200 px-4 py-3 text-sm font-bold text-slate-600 disabled:opacity-50"
          :disabled="isSaving"
          @click="$emit('cancel')"
        >
          나중에 할게요
        </button>
        <button
          type="submit"
          class="min-h-12 rounded-xl bg-amber-400 px-4 py-3 text-sm font-bold text-amber-950 disabled:opacity-50"
          :disabled="isSaving"
        >
          {{ isSaving ? "저장 중..." : "프로필 저장" }}
        </button>
      </div>
    </form>
  </div>
</template>
