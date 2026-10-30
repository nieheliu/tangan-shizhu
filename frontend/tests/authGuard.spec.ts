import { createPinia, setActivePinia } from "pinia";
import { createMemoryHistory, createRouter } from "vue-router";
import { beforeEach, describe, expect, it } from "vitest";

import { attachAuthGuard, routes } from "../src/router";
import { useUserStore } from "../src/stores/user";

const guardedPaths = [
  "/",
  "/profile",
  "/fridge",
  "/recommend",
  "/recipe/1",
  "/report",
  "/shopping",
  "/chat",
  "/graph",
];

describe("auth guard", () => {
  beforeEach(() => {
    localStorage.clear();
    setActivePinia(createPinia());
  });

  it("sends every private page to login when there is no token", async () => {
    const router = createRouter({ history: createMemoryHistory(), routes });
    attachAuthGuard(router);

    for (const path of guardedPaths) {
      await router.push(path);
      expect(router.currentRoute.value.path).toBe("/login");
      expect(router.currentRoute.value.query.redirect).toBe(path);
    }
  });

  it("allows login and register without a token", async () => {
    const router = createRouter({ history: createMemoryHistory(), routes });
    attachAuthGuard(router);

    await router.push("/login");
    expect(router.currentRoute.value.path).toBe("/login");
    await router.push("/register");
    expect(router.currentRoute.value.path).toBe("/register");
  });

  it("allows a signed-in user to open a private page", async () => {
    const router = createRouter({ history: createMemoryHistory(), routes });
    attachAuthGuard(router);
    useUserStore().setSession("token", "demo");

    await router.push("/profile");
    expect(router.currentRoute.value.path).toBe("/profile");
  });
});
