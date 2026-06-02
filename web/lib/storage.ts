import type { AssistantMessage, ChatMessage, ChatSession } from "./types";

const STORAGE_KEY = "revere_chats";
export const MAX_LOCAL_CHATS = 30;

function isValidSession(s: unknown): s is ChatSession {
  return (
    s !== null &&
    typeof s === "object" &&
    typeof (s as ChatSession).id === "string" &&
    typeof (s as ChatSession).title === "string" &&
    Array.isArray((s as ChatSession).messages)
  );
}

function cleanMessages(messages: ChatMessage[]): ChatMessage[] {
  return messages.map(m => {
    if (m.role === "assistant" && (m as AssistantMessage).status === "running") {
      return {
        ...m,
        status: "error" as const,
        error: "This run was interrupted before completion.",
        errorKind: "interrupted" as const,
      } as AssistantMessage;
    }
    return m;
  });
}

export function loadChats(): ChatSession[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter(isValidSession)
      .map(c => ({ ...c, messages: cleanMessages(c.messages) }));
  } catch {
    return [];
  }
}

export function saveChats(chats: ChatSession[]): void {
  try {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify(chats.slice(0, MAX_LOCAL_CHATS))
    );
  } catch {
    // Storage full or unavailable — silently fail
  }
}

export function createChatTitle(firstUserMessage: string): string {
  const clean = firstUserMessage.trim().replace(/\s+/g, " ");
  return clean.length > 52 ? clean.slice(0, 51) + "…" : clean;
}
