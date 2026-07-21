import { createRouter, createWebHistory } from "vue-router";

import { pinia } from "../stores";
import { useAuthStore } from "../stores/auth";

const REDIRECT_PATH_KEY = "redirectPath";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      name: "home",
      component: () => import("../views/HomeView.vue"),
      meta: { guestOnly: true },
    },
    {
      path: "/auth/kakao/callback",
      name: "kakao-callback",
      component: () => import("../views/KakaoCallbackView.vue"),
    },
    {
      path: "/dashboard",
      name: "dashboard",
      component: () => import("../views/DashboardView.vue"),
      meta: { requiresAuth: true },
    },
    {
      path: "/notifications",
      name: "notifications",
      component: () => import("../views/NotificationsView.vue"),
      meta: { requiresAuth: true },
    },
    {
      path: "/settings/notifications",
      name: "notification-settings",
      component: () => import("../views/NotificationSettingsView.vue"),
      meta: { requiresAuth: true },
    },
    {
      path: "/help",
      name: "help",
      component: () => import("../views/HelpView.vue"),
      meta: { requiresAuth: true },
    },
    {
      path: "/teams/create",
      name: "team-create",
      component: () => import("../views/CreateTeamView.vue"),
      meta: { requiresAuth: true },
    },
    {
      path: "/teams/join",
      name: "team-join",
      component: () => import("../views/JoinTeamView.vue"),
      meta: { requiresAuth: true },
    },
    {
      path: "/teams/:teamCode",
      name: "team-home",
      component: () => import("../views/TeamHomeView.vue"),
      meta: { requiresAuth: true },
      props: true,
    },
    {
      path: "/teams/:teamCode/claim",
      name: "participant-claim",
      component: () => import("../views/ParticipantClaimView.vue"),
      meta: { requiresAuth: true },
      props: true,
    },
    {
      path: "/teams/:teamCode/leaderboard",
      name: "team-leaderboard",
      component: () => import("../views/LeaderboardView.vue"),
      meta: { requiresAuth: true },
      props: true,
    },
    {
      path: "/teams/:teamCode/assignment",
      name: "assignment-result",
      component: () => import("../views/AssignmentResultView.vue"),
      meta: { requiresAuth: true },
      props: true,
    },
    {
      path: "/chat",
      name: "chat-list",
      component: () => import("../views/ChatListView.vue"),
      meta: { requiresAuth: true },
    },
    {
      path: "/chat/:roomId",
      name: "chat-room",
      component: () => import("../views/ChatRoomView.vue"),
      meta: { requiresAuth: true },
      props: true,
    },
    {
      path: "/feedback/:threadId",
      name: "feedback-room",
      component: () => import("../views/ChatRoomView.vue"),
      meta: { requiresAuth: true },
      props: (route) => ({ roomId: route.params.threadId, isFeedback: true }),
    },
    {
      path: "/teams/:teamCode/chat",
      redirect: { name: "chat-list" },
    },
    {
      path: "/teams/:teamCode/reveal",
      name: "team-reveal",
      component: () => import("../views/ResultView.vue"),
      meta: { requiresAuth: true },
      props: true,
    },
    {
      path: "/teams/:teamCode/admin",
      name: "team-admin-dashboard",
      component: () => import("../views/AdminDashboardView.vue"),
      meta: { requiresAuth: true },
      props: true,
    },
    {
      path: "/:pathMatch(.*)*",
      redirect: { name: "home" },
    },
  ],
});

router.beforeEach((to) => {
  const auth = useAuthStore(pinia);
  auth.initialize();

  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    localStorage.setItem(REDIRECT_PATH_KEY, to.fullPath);
    return {
      name: "home",
    };
  }

  if (to.meta.guestOnly && auth.isAuthenticated) {
    return { name: "dashboard" };
  }
});

export default router;
