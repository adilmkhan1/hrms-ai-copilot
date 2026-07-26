"use client";

import { Clock, CheckCircle2, XCircle, FileText, Database, Zap, HelpCircle } from "lucide-react";

export interface AIActivityItem {
  id: number;
  message: string;
  intent: string | null;
  tool_name: string | null;
  action_status: string | null;
  created_at: string | null;
}

interface AIActivityFeedProps {
  items: AIActivityItem[];
  isLoading: boolean;
}

const INTENT_META: Record<string, { label: string; icon: React.ElementType; color: string }> = {
  POLICY_QA:  { label: "Policy Q&A",   icon: FileText,    color: "text-indigo-400 bg-indigo-400/10" },
  SQL_QUERY:  { label: "Data Query",   icon: Database,    color: "text-emerald-400 bg-emerald-400/10" },
  HR_ACTION:  { label: "HR Action",    icon: Zap,         color: "text-amber-400 bg-amber-400/10" },
  UNKNOWN:    { label: "Unknown",      icon: HelpCircle,  color: "text-slate-400 bg-slate-400/10" },
};

function formatRelativeTime(isoStr: string | null): string {
  if (!isoStr) return "—";
  const diff = Date.now() - new Date(isoStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export function AIActivityFeed({ items, isLoading }: AIActivityFeedProps) {
  if (isLoading) {
    return (
      <div className="space-y-3 p-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="animate-pulse rounded-xl bg-white/5 h-16 border border-white/5" />
        ))}
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full min-h-[300px] gap-3 text-center px-8">
        <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-slate-500/10 ring-1 ring-slate-500/20">
          <Clock className="h-7 w-7 text-slate-500" />
        </div>
        <div>
          <p className="text-base font-medium text-slate-300">No activity yet</p>
          <p className="mt-1 text-sm text-slate-500">
            Your AI interactions will appear here after you use the other tabs.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-2 p-4 overflow-y-auto">
      {items.map((item) => {
        const meta = INTENT_META[item.intent ?? "UNKNOWN"] ?? INTENT_META["UNKNOWN"];
        const Icon = meta.icon;
        const isSuccess = item.action_status === "SUCCESS";
        const isError = item.action_status === "ERROR";

        return (
          <div
            key={item.id}
            className="flex items-start gap-3 rounded-xl border border-white/5 bg-white/[0.03] px-4 py-3 hover:bg-white/5 transition"
          >
            {/* Intent icon */}
            <div className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg ${meta.color}`}>
              <Icon className="h-3.5 w-3.5" />
            </div>

            {/* Content */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                  {meta.label}
                </span>
                <div className="flex items-center gap-1.5 shrink-0">
                  {item.action_status && (
                    isSuccess ? (
                      <CheckCircle2 className="h-3 w-3 text-emerald-400" />
                    ) : isError ? (
                      <XCircle className="h-3 w-3 text-red-400" />
                    ) : null
                  )}
                  <span className="text-[10px] text-slate-600">
                    {formatRelativeTime(item.created_at)}
                  </span>
                </div>
              </div>
              <p className="mt-0.5 truncate text-sm text-slate-300" title={item.message}>
                {item.message}
              </p>
              {item.tool_name && (
                <p className="mt-0.5 text-[10px] text-slate-600">
                  via {item.tool_name.replace(/_/g, " ")}
                </p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
