import { flushPromises, mount } from "@vue/test-utils";
import ElementPlus from "element-plus";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { createRouter, createMemoryHistory } from "vue-router";

import { fetchSession, fetchSessions, streamChat } from "../src/api/chat";
import ChatView from "../src/views/ChatView.vue";

vi.mock("../src/api/chat", () => ({
  fetchSessions: vi.fn(),
  fetchSession: vi.fn(),
  streamChat: vi.fn(),
}));

async function mountPage() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: "/chat", component: ChatView }, { path: "/login", component: ChatView }],
  });
  await router.push("/chat");
  return mount(ChatView, {
    global: { plugins: [ElementPlus, createPinia(), router] },
  });
}

describe("chat page", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.mocked(fetchSessions).mockReset();
    vi.mocked(fetchSession).mockReset();
    vi.mocked(streamChat).mockReset();
    vi.mocked(fetchSessions).mockResolvedValue({ data: [] } as never);
  });

  it("streams a knowledge answer with citations and the disclaimer", async () => {
    vi.mocked(streamChat).mockImplementation(async (_message, _session, handlers) => {
      handlers.onToken("西瓜可适量。");
      handlers.onToken("本系统仅供饮食参考，不能替代医生诊疗建议。");
      handlers.onSources([{ chunk_id: "g1", source: "指南.pdf", page: 13 }]);
      handlers.onDone(4, "knowledge");
    });
    const wrapper = await mountPage();
    await flushPromises();
    await wrapper.get("input").setValue("糖尿病能吃西瓜吗");
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    expect(wrapper.text()).toContain("西瓜可适量");
    expect(wrapper.text()).toContain("本系统仅供饮食参考，不能替代医生诊疗建议。");
    expect(wrapper.text()).toContain("指南.pdf 第 13 页");
    expect(vi.mocked(streamChat)).toHaveBeenCalledWith("糖尿病能吃西瓜吗", null, expect.anything());
  });

  it("shows the medical intercept without waiting for a model", async () => {
    vi.mocked(streamChat).mockImplementation(async (_message, _session, handlers) => {
      handlers.onToken("这个问题涉及用药、诊断或急症，请就医或咨询医生、营养师。");
      handlers.onDone(5, "blocked");
    });
    const wrapper = await mountPage();
    await flushPromises();
    await wrapper.get("input").setValue("我胸口疼怎么办");
    await wrapper.get("form").trigger("submit");
    await flushPromises();
    expect(wrapper.text()).toContain("请就医");
  });
});
