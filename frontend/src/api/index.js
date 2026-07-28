import axios from "axios";

import { pinia } from "../stores";
import { useAuthStore } from "../stores/auth";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "/api",
  headers: {
    "Content-Type": "application/json",
  },
});

let refreshPromise = null;

api.interceptors.request.use((config) => {
  const auth = useAuthStore(pinia);
  auth.initialize();

  if (!config.skipAuthRefresh && auth.accessToken) {
    config.headers.Authorization = `Bearer ${auth.accessToken}`;
  }

  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    const auth = useAuthStore(pinia);

    if (
      error.response?.status !== 401 ||
      !originalRequest ||
      originalRequest._retry ||
      originalRequest.skipAuthRefresh
    ) {
      return Promise.reject(error);
    }

    if (!auth.refreshToken) {
      auth.logoutAndRedirect();
      return Promise.reject(error);
    }

    originalRequest._retry = true;
    refreshPromise ||= api
      .post(
        "/accounts/token/refresh/",
        { refresh: auth.refreshToken },
        { skipAuthRefresh: true },
      )
      .then((response) => {
        auth.updateAccessToken(response.data.access);
        return response.data.access;
      })
      .finally(() => {
        refreshPromise = null;
      });

    try {
      const accessToken = await refreshPromise;
      originalRequest.headers.Authorization = `Bearer ${accessToken}`;
      return api(originalRequest);
    } catch (refreshError) {
      auth.logoutAndRedirect();
      return Promise.reject(refreshError);
    }
  },
);

export default api;
