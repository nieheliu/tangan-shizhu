import { ref } from "vue";
import { defineStore } from "pinia";

const TOKEN_KEY = "tangan.token";
const USERNAME_KEY = "tangan.username";

export const useUserStore = defineStore("user", () => {
  const token = ref(localStorage.getItem(TOKEN_KEY) ?? "");
  const username = ref(localStorage.getItem(USERNAME_KEY) ?? "");

  function setSession(accessToken: string, name: string) {
    token.value = accessToken;
    username.value = name;
    localStorage.setItem(TOKEN_KEY, accessToken);
    localStorage.setItem(USERNAME_KEY, name);
  }

  function logout() {
    token.value = "";
    username.value = "";
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USERNAME_KEY);
  }

  return { token, username, setSession, logout };
});
