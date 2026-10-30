import { createRouter, createWebHistory, type RouteRecordRaw, type Router } from "vue-router";

import { useUserStore } from "../stores/user";
import HomeView from "../views/HomeView.vue";
import AuthView from "../views/AuthView.vue";
import PlaceholderView from "../views/PlaceholderView.vue";
import ProfileView from "../views/ProfileView.vue";
import FridgeView from "../views/FridgeView.vue";

export const routes: RouteRecordRaw[] = [
  { path: "/login", component: AuthView, meta: { title: "登录", public: true } },
  { path: "/register", component: AuthView, meta: { title: "注册", public: true } },
  { path: "/", name: "home", component: HomeView, meta: { title: "首页" } },
  { path: "/profile", component: ProfileView, meta: { title: "健康档案" } },
  { path: "/fridge", component: FridgeView, meta: { title: "我的冰箱" } },
  { path: "/recommend", component: PlaceholderView, meta: { title: "今日推荐" } },
  { path: "/report", component: PlaceholderView, meta: { title: "营养报告" } },
  { path: "/shopping", component: PlaceholderView, meta: { title: "购物清单" } },
  { path: "/chat", component: PlaceholderView, meta: { title: "问答" } },
  { path: "/graph", component: PlaceholderView, meta: { title: "知识图谱" } },
];

export function attachAuthGuard(router: Router) {
  router.beforeEach((to) => {
    if (to.meta.public) {
      return true;
    }
    if (useUserStore().token) {
      return true;
    }
    return { path: "/login", query: { redirect: to.fullPath } };
  });
}

const router = createRouter({
  history: createWebHistory(),
  routes,
});

attachAuthGuard(router);

export default router;
