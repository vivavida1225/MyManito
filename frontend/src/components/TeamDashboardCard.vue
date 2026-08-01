<script setup>
defineProps({
  team: {
    type: Object,
    required: true,
  },
});
</script>

<template>
  <RouterLink
    :to="{ name: 'team-home', params: { teamCode: team.code } }"
    class="block rounded-2xl border border-amber-100 bg-white p-4 shadow-sm transition hover:border-amber-300 focus:outline-none focus:ring-4 focus:ring-amber-100"
  >
    <div class="flex items-start justify-between gap-3">
      <div>
        <p class="text-xs font-semibold text-amber-600">{{ team.is_owner ? `팀 코드 · ${team.code}` : "참여 중인 마니또 팀" }}</p>
        <p class="mt-1 font-bold text-slate-800">{{ team.is_owner ? "내가 만든 마니또 팀" : team.code }}</p>
      </div>
      <span class="rounded-full bg-amber-100 px-2 py-1 text-xs font-bold text-amber-700">
        {{ team.countdown?.remaining || "종료일 미설정" }}
      </span>
    </div>
    <div class="mt-3 flex gap-2 text-xs text-slate-500">
      <span>{{ team.claim_status === "CLAIMED" ? "본인 확인 완료" : "본인 확인 필요" }}</span>
      <span v-if="team.unread_count">· 새 메시지 {{ team.unread_count }}</span>
    </div>
  </RouterLink>
</template>
