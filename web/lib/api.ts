import type { CompletePayload, HistoryEntry, ProgressEvent, RunOptions } from "./types";

export type SSEHandlers = {
  onStart?: () => void;
  onProgress: (event: ProgressEvent) => void;
  onComplete: (payload: CompletePayload) => void;
  onError: (message: string) => void;
  onStageNote?: (stageId: string, text: string) => void;
};

/**
 * Parse and dispatch a single SSE frame (already split on blank lines).
 * Handles multi-line data values per the SSE spec (joined with "\n").
 */
function dispatchFrame(frame: string, handlers: SSEHandlers): void {
  let eventType = "";
  const dataLines: string[] = [];

  for (const line of frame.split("\n")) {
    if (line.startsWith("event:")) {
      eventType = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      // Trim exactly one leading space per SSE spec
      dataLines.push(line.slice(5).replace(/^ /, ""));
    }
    // "id:" and "retry:" fields are intentionally ignored
  }

  if (!eventType || dataLines.length === 0) return;

  const rawData = dataLines.join("\n");

  try {
    const parsed = JSON.parse(rawData);

    switch (eventType) {
      case "start":
        handlers.onStart?.();
        break;
      case "progress":
        handlers.onProgress(parsed as ProgressEvent);
        break;
      case "complete":
        handlers.onComplete(parsed as CompletePayload);
        break;
      case "error":
        handlers.onError(
          typeof parsed?.message === "string" ? parsed.message : "Unknown error"
        );
        break;
      case "stage_note":
        if (typeof parsed?.stage_id === "string" && typeof parsed?.text === "string") {
          handlers.onStageNote?.(parsed.stage_id, parsed.text);
        }
        break;
      default:
        // Unknown event type — ignore silently
        break;
    }
  } catch (e) {
    if (process.env.NODE_ENV === "development") {
      console.warn("[SSE] JSON parse failed for frame:", { frame, error: e });
    }
  }
}

export async function streamChat(
  message: string,
  options: RunOptions,
  handlers: SSEHandlers,
  signal?: AbortSignal,
  history?: HistoryEntry[]
): Promise<void> {
  let res: Response;
  try {
    res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, ...options, history: history ?? [] }),
      signal,
    });
  } catch (e) {
    if ((e as Error).name !== "AbortError") {
      handlers.onError(`Network error: ${(e as Error).message}`);
    }
    return;
  }

  if (!res.ok || !res.body) {
    handlers.onError(`HTTP ${res.status}: ${res.statusText}`);
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  // Buffer is always kept in LF-normalized form.
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();

    if (value) {
      // Normalize CRLF → LF immediately so split logic is uniform.
      const chunk = decoder.decode(value, { stream: !done });
      buffer += chunk.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
    }

    // Split on blank lines. If not done, keep the trailing incomplete frame
    // in the buffer for the next iteration. If done, process everything.
    const frames = buffer.split("\n\n");

    if (!done) {
      buffer = frames.pop() ?? "";
    } else {
      buffer = "";
    }

    for (const frame of frames) {
      const trimmed = frame.trim();
      if (trimmed) dispatchFrame(trimmed, handlers);
    }

    if (done) break;
  }
}
