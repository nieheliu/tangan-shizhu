export function statusLabel(status: string) {
  if (status === "expiring") {
    return "临期";
  }
  if (status === "expired") {
    return "已过期";
  }
  if (status === "ok") {
    return "正常";
  }
  return "未填到期日";
}

export function statusType(status: string) {
  if (status === "expiring") {
    return "warning" as const;
  }
  if (status === "expired") {
    return "danger" as const;
  }
  if (status === "ok") {
    return "success" as const;
  }
  return "info" as const;
}
