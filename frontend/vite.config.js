import { defineConfig, loadEnv } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig(({ command, mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  if (command === "build" && !env.VITE_IOS_WEB_PUSH_VAPID_PUBLIC_KEY) {
    throw new Error("VITE_IOS_WEB_PUSH_VAPID_PUBLIC_KEY must be set for a production build.");
  }

  return {
    plugins: [vue()],
    server: {
      proxy: {
        "/api": {
          target: "http://localhost:8000",
          changeOrigin: true,
        },
        "/media": {
          target: "http://localhost:8000",
          changeOrigin: true,
        },
        "/ws": {
          target: "ws://localhost:8000",
          ws: true,
        },
      },
    },
  };
});
