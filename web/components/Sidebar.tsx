"use client";

import { MessageSquare, PanelLeftClose, PanelLeftOpen, Plus, Trash2 } from "lucide-react";
import type { ChatSession } from "@/lib/types";

function formatTimestamp(ts: number): string {
  const diff = Date.now() - ts;
  if (diff < 60_000) return "just now";
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`;
  return new Date(ts).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function ChatItem({
  chat,
  active,
  onSelect,
  onDelete,
}: {
  chat: ChatSession;
  active: boolean;
  onSelect: () => void;
  onDelete: () => void;
}) {
  return (
    <div
      className={`group relative flex items-stretch rounded-md transition-colors ${
        active ? "bg-accent/10" : "hover:bg-border/25"
      }`}
    >
      <button
        type="button"
        onClick={onSelect}
        className="flex-1 flex flex-col px-2.5 py-2 min-w-0 text-left"
      >
        <span
          className={`text-[12px] leading-snug truncate ${
            active ? "text-text/90 font-medium" : "text-text/60"
          }`}
        >
          {chat.title}
        </span>
        <span className="text-[10px] text-muted/40 mt-0.5">
          {formatTimestamp(chat.updatedAt)}
        </span>
      </button>
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          onDelete();
        }}
        className="opacity-0 group-hover:opacity-100 flex items-center px-2 text-muted/25 hover:text-red-400 hover:bg-red-900/15 rounded-r-md transition-all"
        aria-label="Delete chat"
      >
        <Trash2 size={11} />
      </button>
    </div>
  );
}

interface SidebarProps {
  chats: ChatSession[];
  activeChatId: string | null;
  open: boolean;
  onToggle: () => void;
  onNewChat: () => void;
  onSelectChat: (id: string) => void;
  onDeleteChat: (id: string) => void;
}

export default function Sidebar({
  chats,
  activeChatId,
  open,
  onToggle,
  onNewChat,
  onSelectChat,
  onDeleteChat,
}: SidebarProps) {
  return (
    <div
      className={`flex flex-col flex-shrink-0 bg-surface border-r border-border overflow-hidden transition-all duration-200 ${
        open ? "w-64" : "w-14"
      }`}
    >
      {/* Header: toggle + app name */}
      <div className="flex items-center gap-2 px-3 py-3.5 border-b border-border/40 flex-shrink-0">
        <button
          type="button"
          onClick={onToggle}
          className="p-1.5 rounded-md text-muted/50 hover:text-text hover:bg-border/40 transition-colors flex-shrink-0"
          aria-label={open ? "Collapse sidebar" : "Expand sidebar"}
        >
          {open ? <PanelLeftClose size={15} /> : <PanelLeftOpen size={15} />}
        </button>
        {open && (
          <span className="text-sm font-semibold text-text/85 tracking-tight truncate">
            Revere
          </span>
        )}
      </div>

      {/* New chat button */}
      <div className="px-2 pt-2 pb-1 flex-shrink-0">
        <button
          type="button"
          onClick={onNewChat}
          className={`flex items-center gap-2 w-full rounded-md px-2 py-2 text-muted/60 hover:text-text hover:bg-border/30 transition-colors ${
            !open ? "justify-center" : ""
          }`}
          title="New chat"
        >
          <Plus size={14} className="flex-shrink-0" />
          {open && <span className="text-xs">New chat</span>}
        </button>
      </div>

      {/* Divider */}
      {open && <div className="mx-3 border-t border-border/30" />}

      {/* Chat list */}
      <div className="flex-1 overflow-y-auto px-2 py-1.5 space-y-0.5">
        {open ? (
          chats.length === 0 ? (
            <p className="text-[11px] text-muted/30 px-2.5 py-3 italic">No chats yet.</p>
          ) : (
            chats.map((chat) => (
              <ChatItem
                key={chat.id}
                chat={chat}
                active={chat.id === activeChatId}
                onSelect={() => onSelectChat(chat.id)}
                onDelete={() => onDeleteChat(chat.id)}
              />
            ))
          )
        ) : (
          chats.slice(0, 14).map((chat) => (
            <button
              key={chat.id}
              type="button"
              onClick={() => onSelectChat(chat.id)}
              title={chat.title}
              className={`w-full flex justify-center py-2 rounded-md transition-colors ${
                chat.id === activeChatId
                  ? "bg-accent/10 text-accent/60"
                  : "text-muted/35 hover:bg-border/25 hover:text-muted"
              }`}
            >
              <MessageSquare size={13} />
            </button>
          ))
        )}
      </div>
    </div>
  );
}
