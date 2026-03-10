const API_BASE = import.meta.env.VITE_API_URL || "/api";

export function remoteLog(level: "info" | "error" | "warn", message: string, data?: unknown) {
  console.log(`[remote:${level}]`, message, data);
  fetch(`${API_BASE}/log`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ level, message, data: data ? JSON.stringify(data) : undefined }),
  }).catch(() => {});
}

export async function fetchConfig() {
  try {
    const resp = await fetch(`${API_BASE}/config`);
    if (!resp.ok) throw new Error(`Config fetch failed: ${resp.status}`);
    return resp.json();
  } catch (err) {
    console.error("[fetchConfig] Failed to load config:", err);
    throw err;
  }
}

export interface StartExpertResponse {
  start_link: string;
  expert_name: string;
  status: string;
}

export async function startExpert(
  userId: number,
  expertId: string,
  message?: string,
): Promise<StartExpertResponse> {
  const resp = await fetch(`${API_BASE}/start-expert`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: userId,
      expert_id: expertId,
      message: message || undefined,
    }),
  });
  if (!resp.ok) throw new Error(`start-expert failed: ${resp.status}`);
  return resp.json();
}

export async function submitPhone(
  phone: string,
  source: string,
  userId: number,
) {
  const resp = await fetch(`${API_BASE}/phone`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ phone, source, user_id: userId }),
  });
  return resp.json();
}
