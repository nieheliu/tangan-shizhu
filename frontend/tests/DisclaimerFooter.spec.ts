import { mount } from "@vue/test-utils";
import { describe, expect, it } from "vitest";

import DisclaimerFooter from "../src/components/DisclaimerFooter.vue";

describe("DisclaimerFooter", () => {
  it("shows the diet disclaimer", () => {
    const wrapper = mount(DisclaimerFooter);
    expect(wrapper.text()).toContain("本系统仅供饮食参考，不能替代医生诊疗建议");
  });
});
