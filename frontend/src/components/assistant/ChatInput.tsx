"use client";

import { SendHorizonal } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";

export function ChatInput({
  onSend,
  disabled,
}: {
  onSend: (message: string) => void;
  disabled: boolean;
}) {
  const [value, setValue] = useState("");

  const submit = () => {
    const message = value.trim();
    if (!message || disabled) return;
    setValue("");
    onSend(message);
  };

  return (
    <div className="flex items-end gap-2 rounded-xl border border-border bg-card p-2">
      <textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            submit();
          }
        }}
        rows={1}
        placeholder="우리 가게에 대해 물어보세요 (예: 최근 4주 문제가 뭐야?)"
        className="max-h-32 flex-1 resize-none bg-transparent px-2 py-1.5 text-sm outline-none"
      />
      <Button size="icon" onClick={submit} disabled={disabled || !value.trim()} aria-label="전송">
        <SendHorizonal className="h-4 w-4" />
      </Button>
    </div>
  );
}
