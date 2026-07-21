"use client";

import { useState } from "react";
import { ChevronUp, ChevronDown, Table2 } from "lucide-react";

interface SQLResultTableProps {
  rows: Record<string, unknown>[];
  sql?: string | null;
}

export function SQLResultTable({ rows, sql }: SQLResultTableProps) {
  const [showSql, setShowSql] = useState(false);

  if (!rows || rows.length === 0) return null;

  const columns = Object.keys(rows[0]);

  return (
    <div className="mt-3 space-y-2">
      <div className="flex items-center gap-2">
        <Table2 className="h-3.5 w-3.5 text-emerald-400" />
        <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
          {rows.length} Result{rows.length !== 1 ? "s" : ""}
        </span>
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-lg border border-white/10">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-white/10 bg-white/5">
              {columns.map((col) => (
                <th
                  key={col}
                  className="px-3 py-2 text-left font-semibold text-slate-400 whitespace-nowrap"
                >
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr
                key={i}
                className={`border-b border-white/5 last:border-0 ${
                  i % 2 === 0 ? "bg-transparent" : "bg-white/[0.02]"
                }`}
              >
                {columns.map((col) => (
                  <td
                    key={col}
                    className="px-3 py-2 text-slate-300 whitespace-nowrap max-w-[200px] truncate"
                    title={String(row[col] ?? "")}
                  >
                    {String(row[col] ?? "—")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* SQL toggle */}
      {sql && (
        <div>
          <button
            onClick={() => setShowSql(!showSql)}
            className="flex items-center gap-1 text-[10px] text-slate-500 hover:text-slate-300 transition"
          >
            {showSql ? (
              <ChevronUp className="h-3 w-3" />
            ) : (
              <ChevronDown className="h-3 w-3" />
            )}
            {showSql ? "Hide SQL" : "Show SQL"}
          </button>
          {showSql && (
            <pre className="mt-1.5 overflow-x-auto rounded-lg bg-black/30 p-3 text-[10px] text-emerald-300 font-mono leading-relaxed">
              {sql}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
