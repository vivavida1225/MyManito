import { defineStore } from "pinia";

const STORAGE_KEY = "mymanito.auth";

export const useAuthStore = defineStore("auth", {
  state: () => ({
    // Django가 발급한 서비스 인증 토큰이다. 카카오 토큰은 서버에서만 보관한다.
    accessToken: null,
    // 짧은 access 토큰을 재발급받기 위한 서비스 refresh 토큰이다.
    refreshToken: null,
    // 카카오 로그인에서 받은 사용자 표시 정보다.
    kakaoProfile: null,
    isInitialized: false,
  }),

  getters: {
    isAuthenticated: (state) => Boolean(state.accessToken),
  },

  actions: {
    initialize() {
      if (this.isInitialized) {
        return;
      }

      const savedAuth = localStorage.getItem(STORAGE_KEY) ?? sessionStorage.getItem(STORAGE_KEY);

      if (savedAuth) {
        try {
          const { accessToken, refreshToken, kakaoProfile } = JSON.parse(savedAuth);
          this.accessToken = accessToken ?? null;
          this.refreshToken = refreshToken ?? null;
          this.kakaoProfile = kakaoProfile ?? null;
          this.persist();
          sessionStorage.removeItem(STORAGE_KEY);
        } catch {
          localStorage.removeItem(STORAGE_KEY);
          sessionStorage.removeItem(STORAGE_KEY);
        }
      }

      this.isInitialized = true;
    },

    setAuthenticatedUser({ accessToken, refreshToken, kakaoProfile }) {
      if (!accessToken || !refreshToken) {
        throw new Error("서비스 access 및 refresh 토큰이 필요합니다.");
      }

      this.accessToken = accessToken;
      this.refreshToken = refreshToken;
      this.kakaoProfile = kakaoProfile;
      this.isInitialized = true;

      this.persist();
    },

    updateAccessToken(accessToken) {
      if (!accessToken) {
        throw new Error("서비스 인증 토큰이 필요합니다.");
      }
      this.accessToken = accessToken;
      this.persist();
    },

    persist() {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          accessToken: this.accessToken,
          refreshToken: this.refreshToken,
          kakaoProfile: this.kakaoProfile,
        }),
      );
    },

    logout() {
      this.accessToken = null;
      this.refreshToken = null;
      this.kakaoProfile = null;
      this.isInitialized = true;
      localStorage.removeItem(STORAGE_KEY);
      sessionStorage.removeItem(STORAGE_KEY);
    },
  },
});
