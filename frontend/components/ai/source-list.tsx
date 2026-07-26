"use client";

import { FileText, Tag } from "lucide-react";

export interface PolicySource {
  title: string;
  category: string;
  filename?: string | null;
}

interface SourceListProps {
  sources: PolicySource[];
}

export function SourceList({ sources }: SourceListProps) {
  if (!sources || sources.length === 0) return null;

  return (
    <div className="mt-3 space-y-1.5">
      <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
        Sources
      </p>
      {sources.map((src, i) => (
        <div
          key={i}
          className="flex items-start gap-2 rounded-lg bg-indigo-500/10 border border-indigo-400/20 px-3 py-2"
        >
          <FileText className="mt-0.5 h-3.5 w-3.5 shrink-0 text-indigo-400" />
          <div className="min-w-0">
            <p className="truncate text-xs font-medium text-indigo-300">
              {src.title}
            </p>
            <div className="mt-0.5 flex items-center gap-1.5">
              <Tag className="h-2.5 w-2.5 text-slate-500" />
              <span className="text-[10px] text-slate-500">{src.category}</span>
              {src.filename && (
                <>
                  <span className="text-slate-600">·</span>
                  <span className="text-[10px] text-slate-600 truncate">
                    {src.filename}
                  </span>
                </>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
