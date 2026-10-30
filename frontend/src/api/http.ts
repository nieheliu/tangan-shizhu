import axios from "axios";

import { useUserStore } from "../stores/user";

const http = axios.create({
  timeout: 8000,
});

http.interceptors.request.use((config) => {
  const token = localStorage.getItem("tangan.token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

http.interceptors.response.use(
  (response) => response,
  (error: unknown) => {
    if (axios.isAxiosError(error) && error.response?.status === 401) {
      const url = error.config?.url ?? "";
      const onAuthForm = url.includes("/auth/login") || url.includes("/auth/register");
      if (!onAuthForm) {
        useUserStore().logout();
        void import("../router").then(({ default: appRouter }) => {
          if (appRouter.currentRoute.value.path !== "/login") {
            const redirect = appRouter.currentRoute.value.fullPath;
            void appRouter.push({ path: "/login", query: { redirect } });
          }
        });
      }
    }
    return Promise.reject(error);
  },
);

export default http;
