<script setup>
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";

import api from "../api";
import JoinTeamView from "./JoinTeamView.vue";

const props = defineProps({
  teamCode: {
    type: String,
    required: true,
  },
});

const router = useRouter();
const isChecking = ref(true);
const errorMessage = ref("");

onMounted(async () => {
  try {
    const response = await api.get(`/teams/${encodeURIComponent(props.teamCode)}/my-assignment/`);
    if (response.data.is_claimed) {
      await router.replace({ name: "team-home", params: { teamCode: props.teamCode } });
      return;
    }
  } catch (error) {
    errorMessage.value = error.response?.data?.detail || "본인 확인 상태를 불러오지 못했습니다.";
  } finally {
    isChecking.value = false;
  }
});
</script>

<template>
  <p v-if="isChecking" class="p-5 py-16 text-center text-sm text-slate-500">본인 확인 상태를 불러오고 있어요...</p>
  <p v-else-if="errorMessage" class="m-5 rounded-2xl bg-red-50 p-4 text-sm text-red-700" role="alert">{{ errorMessage }}</p>
  <JoinTeamView v-else :initial-team-code="teamCode" auto-start />
</template>
