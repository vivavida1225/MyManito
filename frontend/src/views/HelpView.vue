<script setup>
import { ref } from "vue";

import introducingImage from "../assets/mani_introducing.webp";

const activeGuide = ref("participant");

const participantSteps = [
  {
    title: "카카오톡으로 로그인하기",
    description: "로그인 과정에서 ‘카카오톡 메시지 전송’ 에 동의하면 카카오톡의 '나와의 채팅' 내에서 마이마니또의 알림을 받아볼 수 있어요.",
  },
  {
    title: "팀 코드와 규칙 확인하기",
    description: "초대받은 팀 코드를 입력하고, 게임 규칙을 읽은 뒤 동의하고 입장해요.",
  },
  {
    title: "내 이름을 정확히 확인하기",
    description: "카카오 닉네임과 같은 이름은 추천 카드로 먼저 보여요. 그래도 반드시 한 번 더 확인해 주세요. 다른 사람의 이름을 선택하면 게임 진행이 꼬일 수 있어요.",
  },
  {
    title: "내가 챙겨줄 사람과 익명 프로필 설정하기",
    description: "배정 결과에서는 내가 챙겨줄 사람만 확인할 수 있어요. 채팅 전에는 실명, 이니셜, 소속처럼 나를 유추할 수 있는 표현을 피해 익명 닉네임과 프로필을 정해 주세요.",
  },
  {
    title: "두 개의 익명 채팅방 이용하기",
    description: "‘내가 챙겨줄 사람’과 ‘나를 챙겨주는 마니또’ 방에서 각각 대화할 수 있어요. 채팅 목록의 팀 코드와 최근 메시지를 확인해 원하는 방으로 들어가세요.",
  },
  {
    title: "게임 종료 후 결과 확인하기",
    description: "관리자가 게임을 종료하면 결과 공개 방식에 따라 내 마니또와 내가 챙겨준 사람이 공개돼요. 종료된 채팅방과 대화는 7일 동안만 유지됩니다.",
  },
  {
    title: "익명 리더보드 즐기기",
    description: "채팅, 채팅 내 좋아요, 서비스 접속으로 개인 점수를 올릴 수 있어요. 내 점수는 팀 대시보드에서 확인할 수 있고, 다른 참가자의 정확한 점수는 결과 공개 뒤에만 보여요. 오늘 마니또에게 고마운 일이 있었다면 좋아요를 ",
    emphasis: "꼭!",
    descriptionAfter: " 눌러봐요.",
  },
];

const adminSteps = [
  {
    title: "팀 만들기",
    description: "공백 없는 팀 코드와 참가자 명단을 입력해요. 팀 코드는 단체명이나 구호 등 여러분 모두를 표현할 수 있는 단어로 해 주세요. 동명이인은 ‘김민수A’, ‘김민수B’처럼 구분해 등록해 주세요.",
  },
  {
    title: "규칙·종료 예정일·공개 방식 정하기",
    description: "팀 규칙과 종료 예정일을 정하고, 종료 뒤 자동 공개할지 외부 행사 후 관리자가 공개할지 선택해요. 진행 중인 팀에서는 종료 예정일과 공개 방식을 변경할 수 있어요.",
  },
  {
    title: "팀 코드 공유하기",
    description: "팀 생성 뒤 표시되는 팀 코드를 카카오톡, 디스코드, 단체 채팅방 등으로 팀원에게 전달해 주세요.",
  },
  {
    title: "참여 확인 현황 살피기",
    description: "관리자 대시보드에서 참여 진행률과 아직 입장하지 않은 참가자를 보고 참여를 독려할 수 있어요. 진행 중에는 관리자도 다른 사람의 배정 결과를 볼 수 없어요.",
  },
  {
    title: "잘못된 본인 확인 바로잡기",
    description: "참가자가 다른 사람의 이름으로 입장했다면, 확인 완료 참여자 목록에서 연결 해제를 눌러 다시 본인 확인하도록 안내해 주세요.",
  },
  {
    title: "게임 종료와 결과 공개",
    description: "게임 종료는 팀 코드를 다시 입력해야 실행돼요. 자동 공개 방식은 바로 모든 참가자에게 결과를 공개하고, 외부 공개 방식은 관리자만 전체 배정표를 확인한 뒤 이후에 ‘참가자에게 공개하기’를 눌러요.",
  },
];
</script>

<template>
  <section class="p-5 pb-10">
    <img :src="introducingImage" alt="마이마니또 이용 가이드" class="mx-auto w-72 max-w-full object-contain" />

    <div class="mt-6 grid grid-cols-2 gap-2 rounded-2xl bg-slate-100 p-1.5" role="tablist" aria-label="이용자 유형 선택">
      <button
        type="button"
        class="rounded-xl px-3 py-3 text-sm font-bold transition"
        :class="activeGuide === 'participant' ? 'bg-white text-amber-700 shadow-sm' : 'text-slate-500'"
        role="tab"
        :aria-selected="activeGuide === 'participant'"
        @click="activeGuide = 'participant'"
      >
        참여자 가이드
      </button>
      <button
        type="button"
        class="rounded-xl px-3 py-3 text-sm font-bold transition"
        :class="activeGuide === 'admin' ? 'bg-white text-amber-700 shadow-sm' : 'text-slate-500'"
        role="tab"
        :aria-selected="activeGuide === 'admin'"
        @click="activeGuide = 'admin'"
      >
        팀 관리자 가이드
      </button>
    </div>

    <div class="mt-6">
      <div v-if="activeGuide === 'participant'">
        <p class="text-sm font-bold text-sky-600">참여자 흐름</p>
        <h2 class="mt-1 text-xl font-extrabold text-slate-800">초대받은 팀에서 설렘을 시작해요</h2>
        <ol class="mt-4 space-y-3">
          <li v-for="(step, index) in participantSteps" :key="step.title" class="flex gap-3 rounded-2xl bg-white p-4 shadow-sm ring-1 ring-slate-100">
            <span class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-amber-100 text-sm font-extrabold text-amber-800">{{ index + 1 }}</span>
            <div>
              <h3 class="font-bold text-slate-800">{{ step.title }}</h3>
              <p class="mt-1 text-sm leading-6 text-slate-600">
                {{ step.description }}<span v-if="step.emphasis" class="inline-flex -translate-y-px rounded-full bg-rose-100 px-1.5 py-0.5 text-xs font-extrabold text-rose-600 ring-1 ring-rose-200">{{ step.emphasis }}</span>{{ step.descriptionAfter }}
              </p>
            </div>
          </li>
        </ol>
      </div>

      <div v-else>
        <p class="text-sm font-bold text-violet-600">팀 관리자 흐름</p>
        <h2 class="mt-1 text-xl font-extrabold text-slate-800">공정한 게임을 안전하게 운영해요</h2>
        <ol class="mt-4 space-y-3">
          <li v-for="(step, index) in adminSteps" :key="step.title" class="flex gap-3 rounded-2xl bg-white p-4 shadow-sm ring-1 ring-slate-100">
            <span class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-violet-100 text-sm font-extrabold text-violet-700">{{ index + 1 }}</span>
            <div>
              <h3 class="font-bold text-slate-800">{{ step.title }}</h3>
              <p class="mt-1 text-sm leading-6 text-slate-600">{{ step.description }}</p>
            </div>
          </li>
        </ol>
      </div>
    </div>
  </section>
</template>
