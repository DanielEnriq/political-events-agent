"use client";

import { forwardRef, useImperativeHandle, useRef } from "react";
import type { RunOptions } from "@/lib/types";

interface Props {
  options: RunOptions;
  onOptionsChange: (o: RunOptions) => void;
  onSubmit: (message: string) => void;
  onClear: () => void;
  disabled: boolean;
}

export interface ComposerHandle {
  setValue(text: string): void;
}

const SOURCE_OPTIONS = [3, 4, 6, 8, 10];

const Composer = forwardRef<ComposerHandle, Props>(function Composer(
  { options, onOptionsChange, onSubmit, onClear, disabled },
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
    onOptionsChange({ ...options, [key]: !options[key as keyof RunOptions] });
  }

  return (
    <div className="border-t border-border bg-surface">
      <div className="px-4 pt-3 pb-1">
        <textarea
          ref={textareaRef}
          rows={1}
          disabled={disabled}
          onKeyDown={handleKey}
          placeholder="Ask about US political events, candidates, legislation…"
          className="w-full resize-none bg-transparent text-sm text-text placeholder-muted/50 outline-none leading-relaxed"
          style={{ maxHeight: "7rem", overflowY: "auto" }}
          onChange={(e) => {
            e.target.style.height = "auto";
            e.target.style.height = `${e.target.scrollHeight}px`;
          }}
        />
      </div>
      <div className="px-4 pb-3 flex items-center gap-3 flex-wrap">
        {(
          [
            ["fast_mode", "Fast"],
            ["no_search", "No search"],
          ] as [keyof RunOptions, string][]
        ).map(([key, label]) => (
          <button
            key={key}
            onClick={() => toggle(key)}
            className={`text-xs px-2.5 py-1 rounded-full border transition-colors ${
              options[key]
                ? "border-accent/60 text-accent bg-accent/10"
                : "border-border text-muted hover:text-text hover:border-muted"
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
          className="text-xs bg-surface border border-border text-muted rounded px-2 py-1 outline-none hover:border-muted cursor-pointer"
        >
          {SOURCE_OPTIONS.map((n) => (
            <option key={n} value={n}>
              {n} sources
            </option>
          ))}
        </select>

        <div className="flex-1" />

        <button
          onClick={onClear}
          disabled={disabled}
          className="text-xs text-muted hover:text-text transition-colors disabled:opacity-40"
        >
          Clear
        </button>
        <button
          onClick={submit}
          disabled={disabled}
          className="text-sm px-4 py-1.5 rounded-lg bg-accent/20 border border-accent/30 text-accent hover:bg-accent/30 transition-colors disabled:opacity-40 font-medium"
        >
          {disabled ? "Running…" : "Send"}
        </button>
      </div>
    </div>
  );
});

export default Composer;
