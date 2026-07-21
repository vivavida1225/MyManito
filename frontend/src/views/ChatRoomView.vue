<script setup>
import { nextTick, onMounted, onUnmounted, ref } from "vue";
import { useRouter } from "vue-router";
import imageCompression from "browser-image-compression";

import api from "../api";
import celebratingImage from "../assets/mani_celebrating.webp";
import introducingOnlyImage from "../assets/mani_introducing_only.webp";
import messagingImage from "../assets/mani_messaging.webp";
import runningCardImage from "../assets/mani_running_card.webp";
import thinkingImage from "../assets/mani_thinking.webp";
import waitingImage from "../assets/mani_waiting.webp";
import { DEFAULT_PROFILE_OPTIONS } from "../assets/profiles";
import ProfileSetupModal from "../components/ProfileSetupModal.vue";

const props = defineProps({
  roomId: {
    type: String,
    required: true,
  },
  isFeedback: {
    type: Boolean,
    default: false,
  },
});

const router = useRouter();
const messages = ref([]);
const since = ref(null);
const content = ref("");
const imageFile = ref(null);
const fileInput = ref(null);
const messageList = ref(null);
const errorMessage = ref("");
const isFetching = ref(false);
const isSending = ref(false);
const isCompressing = ref(false);
const roomInfo = ref(null);
const chatProfile = ref(null);
const showProfileSetup = ref(false);
const profileError = ref("");
const isSavingProfile = ref(false);
const isEmoticonPickerOpen = ref(false);
const isLiking = ref(false);
const likeNextAvailableAt = ref(null);
const emoticons = [
  ...DEFAULT_PROFILE_OPTIONS,
  { key: "mani-celebrating", label: "축하하는 마니", image: celebratingImage },
  { key: "mani-introducing-only", label: "소개하는 마니", image: introducingOnlyImage },
  { key: "mani-messaging", label: "메시지 보내는 마니", image: messagingImage },
  { key: "mani-running-card", label: "선물 든 마니", image: runningCardImage },
  { key: "mani-thinking", label: "생각하는 마니", image: thinkingImage },
  { key: "mani-waiting", label: "기다리는 마니", image: waitingImage },
];
const emoticonImages = new Map(emoticons.map((emoticon) => [emoticon.key, emoticon.image]));
let pollingTimer;

const IMAGE_COMPRESSION_OPTIONS = {
  maxSizeMB: 1,
  maxWidthOrHeight: 1024,
  initialQuality: 0.9,
  useWebWorker: true,
};

function messageEndpoint() {
  return props.isFeedback
    ? `/chat/feedback/${props.roomId}/messages/`
    : `/chat/${props.roomId}/messages/`;
}

function appendMessages(newMessages) {
  const existingIds = new Set(messages.value.map((message) => message.id));
  messages.value = [...messages.value, ...newMessages.filter((message) => !existingIds.has(message.id))]
    .sort((left, right) => left.id - right.id);
}

async function scrollToLatest() {
  await nextTick();
  if (messageList.value) {
    messageList.value.scrollTop = messageList.value.scrollHeight;
  }
}

async function loadMessages() {
  if (isFetching.value) {
    return;
  }

  isFetching.value = true;
  try {
    const response = await api.get(messageEndpoint(), {
      params: since.value ? { since: since.value } : undefined,
    });
    roomInfo.value = response.data.room;
    appendMessages(response.data.messages);
    if (response.data.next_since) {
      since.value = response.data.next_since;
    }
    if (response.data.messages.length) {
      await scrollToLatest();
    }
  } catch (error) {
    errorMessage.value =
      error.response?.data?.detail || "메시지를 불러오지 못했습니다.";
  } finally {
    isFetching.value = false;
  }
}

async function loadProfile() {
  if (props.isFeedback) {
    return;
  }
  try {
    const response = await api.get(`/chat/${props.roomId}/profile/`);
    chatProfile.value = response.data;
    if (!response.data.my_profile?.nickname) {
      showProfileSetup.value = true;
    }
  } catch (error) {
    errorMessage.value = error.response?.data?.detail || "프로필 정보를 불러오지 못했습니다.";
  }
}

function openSettings() {
  profileError.value = "";
  showProfileSetup.value = true;
}

function likeCooldownLabel() {
  if (!likeNextAvailableAt.value) {
    return "";
  }
  const remainingHours = Math.max(1, Math.ceil((new Date(likeNextAvailableAt.value).getTime() - Date.now()) / 3_600_000));
  return `다음 좋아요는 ${remainingHours}시간 뒤에 가능해요`;
}

async function likeRoom() {
  if (props.isFeedback || isLiking.value || roomInfo.value?.team_status !== "ACTIVE") {
    return;
  }
  errorMessage.value = "";
  isLiking.value = true;
  try {
    const response = await api.post(`/chat/${props.roomId}/like/`);
    likeNextAvailableAt.value = response.data.next_available_at;
  } catch (error) {
    errorMessage.value = error.response?.data?.detail || "좋아요를 반영하지 못했습니다.";
  } finally {
    isLiking.value = false;
  }
}

async function saveProfile({ nickname, avatarKey }) {
  if (!nickname) {
    profileError.value = "익명 닉네임을 입력해 주세요.";
    return;
  }

  profileError.value = "";
  isSavingProfile.value = true;
  try {
    const response = await api.patch(`/chat/${props.roomId}/profile/`, {
      nickname,
      avatar_key: avatarKey,
    });
    chatProfile.value = {
      ...chatProfile.value,
      my_profile: response.data.my_profile,
    };
    showProfileSetup.value = false;
  } catch (error) {
    profileError.value = error.response?.data?.detail || "프로필을 저장하지 못했습니다.";
  } finally {
    isSavingProfile.value = false;
  }
}

async function selectImage(event) {
  const originalImage = event.target.files?.[0];
  if (!originalImage) {
    return;
  }

  errorMessage.value = "";
  isCompressing.value = true;
  try {
    imageFile.value = await imageCompression(originalImage, IMAGE_COMPRESSION_OPTIONS);
  } catch {
    imageFile.value = null;
    if (fileInput.value) {
      fileInput.value.value = "";
    }
    errorMessage.value = "이미지를 압축하지 못했습니다. 다른 이미지를 선택해 주세요.";
  } finally {
    isCompressing.value = false;
  }
}

function getEmoticonImage(emoticonKey) {
  return emoticonImages.get(emoticonKey) || "";
}

async function postMessage({ messageContent = "", image = null, imageName = "", emoticonKey = "" }) {
  errorMessage.value = "";
  isSending.value = true;
  try {
    const response = props.isFeedback
      ? await api.post(messageEndpoint(), { content: messageContent })
      : await api.post(messageEndpoint(), (() => {
        const formData = new FormData();
        if (messageContent) {
          formData.append("content", messageContent);
        }
        if (image) {
          formData.append("image", image, imageName || image.name || "manito-emoticon.webp");
        }
        if (emoticonKey) {
          formData.append("emoticon_key", emoticonKey);
        }
        return formData;
      })(), { headers: { "Content-Type": "multipart/form-data" } });
    appendMessages([response.data]);
    since.value = response.data.created_at;
    await scrollToLatest();
    return true;
  } catch (error) {
    errorMessage.value =
      error.response?.data?.detail || "메시지를 보내지 못했습니다.";
    return false;
  } finally {
    isSending.value = false;
  }
}

async function sendMessage() {
  if (isCompressing.value) {
    return;
  }

  const messageContent = content.value.trim();
  if (!messageContent && !imageFile.value) {
    return;
  }

  const isSent = await postMessage({
    messageContent,
    image: imageFile.value,
    imageName: imageFile.value?.name,
  });
  if (!isSent) {
    return;
  }

  content.value = "";
  imageFile.value = null;
  if (fileInput.value) {
    fileInput.value.value = "";
  }
}

async function sendEmoticon(emoticon) {
  if (isSending.value || isCompressing.value) {
    return;
  }

  if (await postMessage({ emoticonKey: emoticon.key })) {
    isEmoticonPickerOpen.value = false;
  }
}

onMounted(async () => {
  await loadMessages();
  if (!props.isFeedback) {
    await loadProfile();
  }
  pollingTimer = window.setInterval(loadMessages, 3000);
});

onUnmounted(() => {
  window.clearInterval(pollingTimer);
});
</script>

<template>
  <section class="flex h-[calc(100dvh-4rem)] flex-col overflow-hidden bg-[#f5f1ea]">
    <header class="shrink-0 flex items-center gap-3 border-b border-amber-100 bg-white px-4 py-3">
      <button type="button" class="rounded-lg p-1 text-slate-600" aria-label="채팅 목록으로 돌아가기" @click="router.back()">
        <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="m15 18-6-6 6-6" /></svg>
      </button>
      <div>
        <h1 class="font-bold text-slate-800">{{ roomInfo?.title || (isFeedback ? "개발자에게 피드백" : "익명 마니또 채팅") }}</h1>
        <p v-if="roomInfo" class="text-xs text-slate-400">{{ isFeedback ? roomInfo.subtitle : `팀 코드 ${roomInfo.team_code}` }}</p>
      </div>
      <div v-if="!isFeedback" class="ml-auto flex items-center gap-2">
        <button
          type="button"
          class="rounded-full p-2 transition disabled:opacity-40"
          :class="likeNextAvailableAt ? 'bg-rose-100 text-rose-500' : 'bg-amber-50 text-slate-600 hover:bg-rose-50 hover:text-rose-500'"
          :aria-label="likeNextAvailableAt ? '좋아요를 눌렀습니다' : '좋아요 보내기'"
          :title="likeCooldownLabel() || '좋아요 보내기'"
          :disabled="isLiking || roomInfo?.team_status !== 'ACTIVE'"
          @click="likeRoom"
        >
          <svg class="h-4 w-4" viewBox="0 0 24 24" :fill="likeNextAvailableAt ? 'currentColor' : 'none'" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M20.8 4.6a5.4 5.4 0 0 0-7.6 0L12 5.8l-1.2-1.2a5.4 5.4 0 0 0-7.6 7.6L12 21l8.8-8.8a5.4 5.4 0 0 0 0-7.6Z" /></svg>
        </button>
        <button
          type="button"
          class="rounded-full bg-amber-50 p-2 text-slate-600 hover:bg-amber-100 disabled:opacity-40"
          aria-label="내 익명 프로필 설정"
          :disabled="!chatProfile"
          @click="openSettings"
        >
          <svg class="h-4 w-4" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M19.43 12.98c.04-.32.07-.65.07-.98s-.03-.66-.08-.98l2.11-1.65a.5.5 0 0 0 .12-.64l-2-3.46a.5.5 0 0 0-.61-.22l-2.49 1a7.3 7.3 0 0 0-1.69-.98L14.5 2.42A.5.5 0 0 0 14 2h-4a.5.5 0 0 0-.49.42l-.38 2.65a7.3 7.3 0 0 0-1.69.98l-2.49-1a.5.5 0 0 0-.61.22l-2 3.46a.5.5 0 0 0 .12.64l2.11 1.65c-.05.32-.08.65-.08.98s.03.66.08.98l-2.11 1.65a.5.5 0 0 0-.12.64l2 3.46a.5.5 0 0 0 .61.22l2.49-1c.52.4 1.09.73 1.69.98l.38 2.65c.04.24.25.42.49.42h4c.24 0 .45-.18.49-.42l.38-2.65c.6-.25 1.17-.58 1.69-.98l2.49 1a.5.5 0 0 0 .61-.22l2-3.46a.5.5 0 0 0-.12-.64l-2.11-1.65ZM12 15.5A3.5 3.5 0 1 1 12 8a3.5 3.5 0 0 1 0 7.5Z" /></svg>
        </button>
      </div>
    </header>
    <p v-if="!isFeedback && likeNextAvailableAt" class="shrink-0 bg-rose-50 px-4 py-2 text-center text-xs font-medium text-rose-600">{{ likeCooldownLabel() }}</p>

    <div ref="messageList" class="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
      <p
        v-if="!isFeedback && roomInfo?.team_status === 'ENDED'"
        class="rounded-xl bg-amber-100 px-3 py-2 text-center text-xs leading-5 text-amber-900"
      >
        게임은 종료되었지만, 이 채팅방은 종료 후 7일간 유지돼요. 7일 뒤 채팅 내역과 함께 사라집니다.
      </p>
      <p v-if="!messages.length && !isFetching" class="pt-8 text-center text-sm text-slate-500">
        첫 메시지를 보내 보세요.
      </p>
      <div
        v-for="message in messages"
        :key="message.id"
        class="flex"
        :class="message.is_mine ? 'justify-end' : 'justify-start'"
      >
        <div class="max-w-[78%]">
          <p v-if="!message.is_mine" class="mb-1 text-xs font-medium text-slate-500">{{ message.sender_nickname }}</p>
          <div
            class="rounded-2xl px-3 py-2 text-sm leading-5"
            :class="message.is_mine ? 'rounded-tr-sm bg-amber-300 text-slate-900' : 'rounded-tl-sm bg-white text-slate-800 shadow-sm'"
          >
            <img
              v-if="message.image_url"
              :src="message.image_url"
              alt="첨부 이미지"
              class="mb-2 max-h-64 max-w-full rounded-lg object-contain"
            />
            <img
              v-else-if="message.emoticon_key"
              :src="getEmoticonImage(message.emoticon_key)"
              alt="이모티콘"
              class="mb-1 max-h-40 max-w-full object-contain"
            />
            <p v-if="message.content" class="whitespace-pre-wrap">{{ message.content }}</p>
          </div>
        </div>
      </div>
    </div>

    <form class="shrink-0 border-t border-slate-200 bg-white p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]" @submit.prevent="sendMessage">
      <p v-if="errorMessage" class="mb-2 text-xs text-red-600">{{ errorMessage }}</p>
      <p v-if="isCompressing" class="mb-2 text-xs text-slate-500">이미지를 압축하고 있어요...</p>
      <div id="chat-emoticon-picker" v-if="isEmoticonPickerOpen" class="mb-3 rounded-2xl border border-amber-100 bg-amber-50 p-3 shadow-sm">
        <div class="grid max-h-52 grid-cols-6 gap-2 overflow-y-auto pr-1">
          <button
            v-for="emoticon in emoticons"
            :key="emoticon.key"
            type="button"
            class="aspect-square rounded-xl bg-white p-1 shadow-sm transition hover:bg-amber-100 disabled:opacity-50"
            :aria-label="`${emoticon.label} 이모티콘 보내기`"
            :disabled="isSending || isCompressing"
            @click="sendEmoticon(emoticon)"
          >
            <img :src="emoticon.image" :alt="emoticon.label" class="h-full w-full object-contain" />
          </button>
        </div>
      </div>
      <div class="flex gap-2">
        <input
          v-if="!isFeedback"
          ref="fileInput"
          accept="image/*"
          class="sr-only"
          id="chat-image-input"
          type="file"
          :disabled="isSending || isCompressing"
          @change="selectImage"
        />
        <label
          v-if="!isFeedback"
          for="chat-image-input"
          class="flex h-11 w-11 shrink-0 cursor-pointer items-center justify-center rounded-xl border border-slate-200 text-slate-600 hover:bg-amber-50"
          :class="isSending || isCompressing ? 'pointer-events-none opacity-50' : ''"
          aria-label="이미지 첨부"
          title="이미지 첨부"
        >
          <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="8.5" cy="8.5" r="1.5" /><path d="m21 15-5-5L5 21" /></svg>
        </label>
        <button
          v-if="!isFeedback"
          type="button"
          class="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-slate-200 text-slate-600 hover:bg-amber-50"
          :aria-expanded="isEmoticonPickerOpen"
          aria-controls="chat-emoticon-picker"
          aria-label="이모티콘 선택"
          title="이모티콘 선택"
          :disabled="isSending || isCompressing"
          @click="isEmoticonPickerOpen = !isEmoticonPickerOpen"
        >
          <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M8 14s1.2 2 4 2 4-2 4-2" /><path d="M9 9h.01M15 9h.01" stroke-linecap="round" /></svg>
        </button>
        <input
          v-model="content"
          class="min-w-0 flex-1 rounded-xl border border-slate-200 px-3 py-2 text-sm outline-none focus:border-amber-400 focus:ring-2 focus:ring-amber-100"
          :placeholder="isFeedback ? '개발자에게 의견을 남겨 주세요.' : ''"
        />
        <button
          type="submit"
          class="rounded-xl bg-amber-400 px-4 py-2 text-sm font-bold text-amber-950 disabled:opacity-50"
          :disabled="isSending || isCompressing"
        >
          {{ isCompressing ? "압축 중..." : isSending ? "전송 중..." : "전송" }}
        </button>
      </div>
      <p v-if="!isFeedback && imageFile" class="mt-1 text-xs text-slate-500">{{ imageFile.name }}</p>
    </form>

    <ProfileSetupModal
      v-if="!isFeedback && showProfileSetup"
      :initial-profile="chatProfile?.my_profile"
      :is-saving="isSavingProfile"
      :error-message="profileError"
      @cancel="showProfileSetup = false"
      @save="saveProfile"
    />
  </section>
</template>
