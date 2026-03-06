const API_BASE = import.meta.env.VITE_API_URL || "/api";

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

  if (!resp.ok) {
    throw new Error(`Chat request failed: ${resp.status}`);
  }

  const reader = resp.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    for (const line of lines) {
      if (line.startsWith("data: ")) {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        let parsed: any;
        try {
          parsed = JSON.parse(line.slice(6));
        } catch {
          console.warn("[streamChat] Failed to parse SSE line:", line);
          continue;
        }
        if (parsed.type === "error") {
          throw new Error(parsed.text || "Stream error");
        }
        yield parsed;
      }
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
