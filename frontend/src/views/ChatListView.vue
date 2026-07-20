<script setup>
import { computed, onMounted, ref } from "vue";

import api from "../api";
import { getDefaultProfileImage } from "../assets/profiles/index.js";
import waitingImage from "../assets/mani_waiting.webp";

const rooms = ref([]);
const errorMessage = ref("");
const isLoading = ref(false);
const caredForRooms = computed(() => rooms.value.filter((room) => room.relationship_label === "내가 챙겨줄 사람"));
const caringForMeRooms = computed(() => rooms.value.filter((room) => room.relationship_label === "나를 챙겨주는 마니또"));

async function loadRooms() {
  errorMessage.value = "";
  isLoading.value = true;
  try {
    const response = await api.get("/chat/rooms/");
    rooms.value = response.data.rooms;
  } catch (error) {
    errorMessage.value =
      error.response?.data?.detail || "채팅방 목록을 불러오지 못했습니다.";
  } finally {
    isLoading.value = false;
  }
}

onMounted(loadRooms);
</script>

<template>
  <section class="p-5 pb-10">
    <div class="flex items-start justify-between gap-3">
      <div>
        <p class="text-sm font-bold text-amber-500">두근두근 익명 대화</p>
        <h1 class="mt-1 text-2xl font-extrabold text-slate-800">마니또 채팅</h1>
      </div>
      <button
        type="button"
        class="rounded-xl bg-white px-3 py-2 text-sm font-bold text-slate-600 shadow-sm ring-1 ring-slate-100 disabled:opacity-50"
        :disabled="isLoading"
        @click="loadRooms"
      >
        새로고침
      </button>
    </div>

    <p v-if="isLoading && !rooms.length" class="py-16 text-center text-sm text-slate-500">채팅방을 불러오고 있어요...</p>

    <div v-else-if="rooms.length" class="mt-7 space-y-7">
      <div v-for="group in [{ title: '내가 챙겨줄 사람', rooms: caredForRooms }, { title: '나를 챙겨주는 마니또', rooms: caringForMeRooms }]" :key="group.title">
        <h2 class="text-base font-bold text-slate-800">{{ group.title }}</h2>
        <div class="mt-3 space-y-3">
          <RouterLink
            v-for="room in group.rooms"
            :key="room.room_id"
            :to="{ name: 'chat-room', params: { roomId: room.room_id } }"
            class="block rounded-2xl bg-white p-4 shadow-sm ring-1 ring-slate-100 transition hover:ring-amber-200"
          >
            <div class="flex items-center gap-3">
              <img
                v-if="!room.counterpart_claimed"
                :src="waitingImage"
                alt="기다리고 있는 마니"
                class="h-12 w-12 rounded-full object-cover object-top"
              />
              <img
                v-else-if="room.counterpart_profile_image_url"
                :src="room.counterpart_profile_image_url"
                alt="상대방 익명 프로필"
                class="h-12 w-12 rounded-full object-cover"
              />
              <img
                v-else
                :src="getDefaultProfileImage(room.counterpart_avatar_key)"
                alt="상대방 익명 프로필"
                class="h-12 w-12 rounded-full object-contain"
              />

              <div class="min-w-0 flex-1">
                <p class="font-bold text-slate-800">{{ room.counterpart_name || room.relationship_label }}</p>
                <p v-if="room.counterpart_claimed" class="mt-1 truncate text-sm text-slate-500">{{ room.counterpart_nickname }}</p>
                <p v-else class="mt-1 text-sm font-medium text-amber-600">상대방이 아직 확인하지 않았어요</p>
              </div>

              <div class="flex shrink-0 flex-col items-end gap-2">
                <span class="text-xs font-semibold text-slate-400">{{ room.team_code }}</span>
                <span v-if="room.unread_count" class="min-w-5 rounded-full bg-rose-500 px-1.5 py-0.5 text-center text-xs font-bold text-white">{{ room.unread_count }}</span>
              </div>
            </div>
          </RouterLink>
          <p v-if="!group.rooms.length" class="rounded-xl bg-slate-100 px-4 py-3 text-sm text-slate-500">아직 연결된 채팅방이 없어요.</p>
        </div>
      </div>
    </div>

    <div v-else-if="!isLoading" class="mt-10 text-center">
      <img :src="waitingImage" alt="기다리고 있는 마니" class="mx-auto w-40" />
      <p class="mt-2 text-sm leading-6 text-slate-500">참여 중인 채팅방이 없어요.<br />팀에서 본인 확인을 마치면 대화를 시작할 수 있어요.</p>
    </div>
    <p v-if="errorMessage" class="mt-4 text-sm text-red-600" role="alert">{{ errorMessage }}</p>
  </section>
</template>
