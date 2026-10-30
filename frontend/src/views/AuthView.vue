<template>
  <div class="auth-page">
    <el-card class="auth-card">
      <h1>{{ isRegister ? "注册" : "登录" }}</h1>
      <p class="hint">演示账号 demo，密码 demo12345</p>
      <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" />
      <el-form label-position="top" @submit.prevent="submit">
        <el-form-item label="用户名">
          <el-input v-model="username" autocomplete="username" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="password" type="password" show-password autocomplete="current-password" />
        </el-form-item>
        <el-button type="primary" native-type="submit" :loading="submitting" class="submit">
          {{ isRegister ? "注册并登录" : "登录" }}
        </el-button>
      </el-form>
      <router-link :to="isRegister ? '/login' : '/register'">
        {{ isRegister ? "已有账号，去登录" : "没有账号，去注册" }}
      </router-link>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import axios from "axios";
import { computed, ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import { fetchMe, login, register } from "../api/auth";
import { useUserStore } from "../stores/user";

const route = useRoute();
const router = useRouter();
const user = useUserStore();

const username = ref("");
const password = ref("");
const error = ref("");
const submitting = ref(false);
const isRegister = computed(() => route.path === "/register");

function safeRedirect(value: unknown) {
  if (typeof value === "string" && value.startsWith("/") && !value.startsWith("//")) {
    return value;
  }
  return "/";
}

function messageFrom(caught: unknown) {
  if (axios.isAxiosError(caught)) {
    const detail = caught.response?.data?.detail;
    if (typeof detail === "string") {
      return detail;
    }
  }
  return isRegister.value ? "注册失败" : "登录失败";
}

async function submit() {
  error.value = "";
  submitting.value = true;
  try {
    if (isRegister.value) {
      await register(username.value, password.value);
    }
    const accessToken = await login(username.value, password.value);
    user.setSession(accessToken, username.value);
    const me = await fetchMe();
    user.setSession(accessToken, me.username);
    await router.push(safeRedirect(route.query.redirect));
  } catch (caught) {
    error.value = messageFrom(caught);
  } finally {
    submitting.value = false;
  }
}
</script>

<style scoped>
.auth-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}

.auth-card {
  width: 360px;
}

h1 {
  margin: 0 0 8px;
  color: #1f6b3a;
}

.hint {
  margin: 0 0 16px;
  color: #5c6b62;
  font-size: 13px;
}

.submit {
  width: 100%;
  margin-bottom: 12px;
}
</style>
