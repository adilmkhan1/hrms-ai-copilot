"use client";

import { CheckCircle2, XCircle, AlertTriangle, Loader2 } from "lucide-react";
import { useState } from "react";

interface HITLConfirmationProps {
  confirmationMessage: string;
  actionIntent: string | null;
  threadId: string;
  onConfirm: (threadId: string, confirmed: boolean) => Promise<void>;
}

export function HITLConfirmation({
  confirmationMessage,
  actionIntent,
  threadId,
  onConfirm,
}: HITLConfirmationProps) {
  const [loading, setLoading] = useState<"confirm" | "cancel" | null>(null);

  const handle = async (confirmed: boolean) => {
    setLoading(confirmed ? "confirm" : "cancel");
    try {
      await onConfirm(threadId, confirmed);
    } finally {
      setLoading(null);
    }
  };

  const intentLabel: Record<string, string> = {
    approve_leave: "Approve Leave",
    reject_leave: "Reject Leave",
    create_announcement: "Post Announcement",
    assign_to_project: "Assign to Project",
  };

  const label = intentLabel[actionIntent ?? ""] ?? "Confirm Action";

  return (
    <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 p-4 space-y-3">
      {/* Header */}
      <div className="flex items-center gap-2">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-amber-500/15">
          <AlertTriangle className="h-4 w-4 text-amber-400" />
        </div>
        <div>
          <p className="text-xs font-semibold text-amber-400 uppercase tracking-wider">
            Human Confirmation Required
          </p>
          <p className="text-[10px] text-slate-500">{label} · LangGraph HITL</p>
        </div>
      </div>

      {/* Confirmation message (supports markdown-like **bold**) */}
      <div className="rounded-lg bg-white/[0.03] border border-white/5 px-3 py-2.5">
        <p className="text-sm text-slate-300 whitespace-pre-wrap leading-relaxed">
          {confirmationMessage.replace(/\*\*(.*?)\*\*/g, (_, t) => t)}
        </p>
      </div>

      {/* Thread ID badge */}
      <p className="text-[9px] text-slate-600 font-mono truncate">
        graph thread: {threadId}
      </p>

      {/* Action buttons */}
      <div className="flex gap-2 pt-1">
        <button
          id="hitl-confirm"
          onClick={() => handle(true)}
          disabled={loading !== null}
          className="flex flex-1 items-center justify-center gap-2 rounded-lg bg-emerald-500/15 border border-emerald-500/20 px-4 py-2 text-sm font-medium text-emerald-400 transition hover:bg-emerald-500/25 disabled:opacity-50"
        >
          {loading === "confirm" ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <CheckCircle2 className="h-3.5 w-3.5" />
          )}
          Confirm
        </button>
        <button
          id="hitl-cancel"
          onClick={() => handle(false)}
          disabled={loading !== null}
          className="flex flex-1 items-center justify-center gap-2 rounded-lg bg-red-500/10 border border-red-500/20 px-4 py-2 text-sm font-medium text-red-400 transition hover:bg-red-500/20 disabled:opacity-50"
        >
          {loading === "cancel" ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <XCircle className="h-3.5 w-3.5" />
          )}
          Cancel
        </button>
      </div>
    </div>
  );
}
