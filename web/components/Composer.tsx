"use client";

import { forwardRef, useImperativeHandle, useRef } from "react";
import { Send } from "lucide-react";
import type { RunOptions } from "@/lib/types";

interface Props {
  options: RunOptions;
  onOptionsChange: (o: RunOptions) => void;
  onSubmit: (message: string) => void;
  onClear?: () => void;
  clearLabel?: string;
  disabled: boolean;
  variant?: "hero" | "dock";
}

export interface ComposerHandle {
  setValue(text: string): void;
}

const SOURCE_OPTIONS = [3, 4, 6, 8, 10];

const Composer = forwardRef<ComposerHandle, Props>(function Composer(
  {
    options,
    onOptionsChange,
    onSubmit,
    onClear,
    clearLabel = "Clear",
    disabled,
    variant = "dock",
  },
  ref
) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useImperativeHandle(ref, () => ({
    setValue(text: string) {
      if (textareaRef.current) {
        textareaRef.current.value = text;
        textareaRef.current.focus();
        textareaRef.current.style.height = "auto";
        textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`;
      }
    },
  }));

  function handleKey(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  function submit() {
    const text = textareaRef.current?.value.trim() ?? "";
    if (!text || disabled) return;
    textareaRef.current!.value = "";
    textareaRef.current!.style.height = "auto";
    onSubmit(text);
  }

  function toggle(key: keyof RunOptions) {
    onOptionsChange({ ...options, [key]: !options[key] });
  }

  const isHero = variant === "hero";

  return (
    <div
      className={
        isHero
          ? "bg-surface rounded-xl border border-border/60 shadow-sm"
          : "border-t border-border bg-surface"
      }
    >
      <div className={isHero ? "px-4 pt-4 pb-2" : "px-4 pt-3 pb-1"}>
        <textarea
          ref={textareaRef}
          rows={isHero ? 2 : 1}
          disabled={disabled}
          onKeyDown={handleKey}
          placeholder={
            isHero
              ? "Ask about any US political event…"
              : "Ask about US political events, candidates, legislation…"
          }
          className="w-full resize-none bg-transparent text-sm text-text placeholder-muted/45 outline-none leading-relaxed"
          style={{ maxHeight: "7rem", overflowY: "auto" }}
          onChange={(e) => {
            e.target.style.height = "auto";
            e.target.style.height = `${e.target.scrollHeight}px`;
          }}
        />
      </div>

      <div className="px-4 pb-3 flex items-center gap-2 flex-wrap">
        {/* Mode chips */}
        {(
          [
            ["fast_mode", "Fast"],
            ["no_search", "No search"],
          ] as [keyof RunOptions, string][]
        ).map(([key, label]) => (
          <button
            key={key}
            type="button"
            onClick={() => toggle(key)}
            className={`text-xs px-2.5 py-1 rounded-full border transition-colors ${
              options[key]
                ? "border-accent/60 text-accent/90 bg-accent/10"
                : "border-border text-muted/55 hover:text-text hover:border-muted/50"
            }`}
          >
            {label}
          </button>
        ))}

        <select
          value={options.max_hits}
          onChange={(e) =>
            onOptionsChange({ ...options, max_hits: Number(e.target.value) })
          }
          className="text-xs bg-transparent border border-border text-muted/55 rounded-full px-2.5 py-1 outline-none hover:border-muted/50 hover:text-text cursor-pointer transition-colors"
        >
          {SOURCE_OPTIONS.map((n) => (
            <option key={n} value={n} className="bg-surface">
              {n} sources
            </option>
          ))}
        </select>

        <div className="flex-1" />

        {/* Clear / New — dock only */}
        {!isHero && onClear && (
          <button
            type="button"
            onClick={onClear}
            disabled={disabled}
            className="text-xs text-muted/45 hover:text-text/70 transition-colors disabled:opacity-30"
          >
            {clearLabel}
          </button>
        )}

        {/* Submit */}
        <button
          type="button"
          onClick={submit}
          disabled={disabled}
          className="flex items-center gap-1.5 text-sm px-3.5 py-1.5 rounded-lg bg-accent/20 border border-accent/30 text-accent hover:bg-accent/30 transition-colors disabled:opacity-40"
        >
          {disabled ? (
            <span className="text-xs font-medium">Running…</span>
          ) : (
            <>
              <Send size={12} strokeWidth={2} />
              <span className="text-xs font-medium">{isHero ? "Ask" : "Send"}</span>
            </>
          )}
        </button>
      </div>
    </div>
  );
});

export default Composer;
