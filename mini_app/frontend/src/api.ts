const API_BASE = import.meta.env.VITE_API_URL || "/api";

export async function fetchConfig() {
  try {
    const resp = await fetch(`${API_BASE}/config`);
    return resp.json();
  } catch (err) {
    console.error("[fetchConfig] Failed to load config:", err);
    throw err;
  }
}

export async function* streamChat(
  message: string,
  userId: number,
  expertId?: string,
) {
  const resp = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      user_id: userId,
      expert_id: expertId,
    }),
  });

  const reader = resp.body!.getReader();
  const decoder = new TextDecoder();

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    const text = decoder.decode(value);
    const lines = text.split("\n").filter((l) => l.startsWith("data: "));
    for (const line of lines) {
      yield JSON.parse(line.slice(6));
    }
  }
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
