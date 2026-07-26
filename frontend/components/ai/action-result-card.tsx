"use client";

import { CheckCircle2, XCircle, AlertCircle } from "lucide-react";

interface ActionResultCardProps {
  intent: string;
  success: boolean;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  data?: any;
}

export function ActionResultCard({
  intent,
  success,
  data,
}: ActionResultCardProps) {
  const icon = success ? (
    <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
  ) : intent === "unknown" ? (
    <AlertCircle className="h-4 w-4 text-amber-400 shrink-0" />
  ) : (
    <XCircle className="h-4 w-4 text-red-400 shrink-0" />
  );

  const badgeColor = success
    ? "bg-emerald-500/10 text-emerald-300 border-emerald-500/20"
    : intent === "unknown"
      ? "bg-amber-500/10 text-amber-300 border-amber-500/20"
      : "bg-red-500/10 text-red-300 border-red-500/20";

  const intentLabel = intent
    .replace(/_/g, " ")
    .replace(/\b\w/g, (l) => l.toUpperCase());

  return (
    <div className={`mt-3 flex items-start gap-2 rounded-lg border px-3 py-2 ${badgeColor}`}>
      {icon}
      <div className="min-w-0">
        <p className="text-[11px] font-semibold">{intentLabel}</p>
        {success && data && (
          <p className="mt-0.5 text-[10px] opacity-75">
            Action completed successfully
          </p>
        )}
      </div>
    </div>
  );
}
