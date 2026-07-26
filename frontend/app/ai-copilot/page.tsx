"use client";

import { useState, useCallback, useEffect } from "react";
import { Bot, FileText, Database, Zap, History, BookOpen, Shield, RefreshCw } from "lucide-react";
import { ChatPanel, ChatMessage } from "@/components/ai/chat-panel";
import { SourceList, PolicySource } from "@/components/ai/source-list";
import { SQLResultTable } from "@/components/ai/sql-result-table";
import { ActionResultCard } from "@/components/ai/action-result-card";
import { AIActivityFeed, AIActivityItem } from "@/components/ai/activity-feed";
import { chatPolicy, chatSQL, chatActions, getMyAIActivity } from "@/lib/api";

type Tab = "policy" | "sql" | "actions" | "activity";

const TABS: {
  id: Tab;
  label: string;
  icon: React.ElementType;
  description: string;
  placeholder?: string;
}[] = [
  {
    id: "policy",
    label: "Ask HR Policy",
    icon: FileText,
    description: "Ask about leave entitlements, WFH rules, benefits, and all HR policies.",
    placeholder: "e.g. What is the sick leave policy? Can I work from home?",
  },
  {
    id: "sql",
    label: "People & Projects",
    icon: Database,
    description: "Look up employees, project assignments, skills, and team data.",
    placeholder: "e.g. Who is assigned to ongoing projects? Which employees know Python?",
  },
  {
    id: "actions",
    label: "Automate HR Task",
    icon: Zap,
    description: "Apply for leave, create tickets, approve requests, and more — just by typing.",
    placeholder: "e.g. Apply sick leave for tomorrow. Create a ticket for VPN issue.",
  },
  {
    id: "activity",
    label: "Recent Activity",
    icon: History,
    description: "Your recent AI interactions across all assistants.",
  },
];

function generateId() {
  return Math.random().toString(36).slice(2, 9);
}

const SAMPLES: Record<string, string[]> = {
  policy: [
    "What is the sick leave policy?",
    "Can I work from home?",
    "How many casual leaves do I get?",
    "What happens if I am late?",
  ],
  sql: [
    "Which projects are ongoing?",
    "Show employees with Python skills",
    "Who are my team members?",
    "Show my current project assignments",
  ],
  actions: [
    "Check my leave balance",
    "Apply casual leave for tomorrow",
    "Create a high-priority IT ticket for VPN issue",
    "Show my recent tickets",
  ],
};

export default function AICopilotPage() {
  const [activeTab, setActiveTab] = useState<Tab>("policy");
  const [messagesByTab, setMessagesByTab] = useState<Record<string, ChatMessage[]>>({
    policy: [],
    sql: [],
    actions: [],
  });
  const [loadingByTab, setLoadingByTab] = useState<Record<string, boolean>>({
    policy: false,
    sql: false,
    actions: false,
  });

  // Activity tab state
  const [activityItems, setActivityItems] = useState<AIActivityItem[]>([]);
  const [activityLoading, setActivityLoading] = useState(false);

  const fetchActivity = useCallback(async () => {
    setActivityLoading(true);
    try {
      const data = await getMyAIActivity(20, 0);
      setActivityItems(data.items ?? []);
    } catch {
      setActivityItems([]);
    } finally {
      setActivityLoading(false);
    }
  }, []);

  // Auto-fetch activity when tab opens
  useEffect(() => {
    if (activeTab === "activity") {
      fetchActivity();
    }
  }, [activeTab, fetchActivity]);

  const addMessage = useCallback((tab: string, message: ChatMessage) => {
    setMessagesByTab((prev) => ({
      ...prev,
      [tab]: [...(prev[tab] ?? []), message],
    }));
  }, []);

  const handleSend = useCallback(
    async (tab: string, message: string) => {
      addMessage(tab, {
        id: generateId(),
        role: "user",
        content: message,
        timestamp: new Date(),
      });

      setLoadingByTab((prev) => ({ ...prev, [tab]: true }));

      try {
        if (tab === "policy") {
          const res = await chatPolicy(message);
          const data = res.data;
          addMessage(tab, {
            id: generateId(),
            role: "assistant",
            content: data.answer,
            timestamp: new Date(),
            extra: <SourceList sources={data.sources as PolicySource[]} />,
          });
        } else if (tab === "sql") {
          const res = await chatSQL(message);
          const data = res.data;
          addMessage(tab, {
            id: generateId(),
            role: "assistant",
            content: data.answer,
            timestamp: new Date(),
            extra: (
              <SQLResultTable
                rows={data.rows as Record<string, unknown>[]}
                sql={data.sql}
              />
            ),
          });
        } else if (tab === "actions") {
          const res = await chatActions(message);
          const data = res.data;
          addMessage(tab, {
            id: generateId(),
            role: "assistant",
            content: data.result,
            timestamp: new Date(),
            extra: (
              <ActionResultCard
                intent={data.intent}
                success={data.success}
                data={data.data}
              />
            ),
          });
        }
      } catch (err: unknown) {
        const errorMsg =
          err instanceof Error ? err.message : "Something went wrong. Please try again.";
        addMessage(tab, {
          id: generateId(),
          role: "assistant",
          content: `⚠️ ${errorMsg}`,
          timestamp: new Date(),
        });
      } finally {
        setLoadingByTab((prev) => ({ ...prev, [tab]: false }));
      }
    },
    [addMessage]
  );

  const activeTabInfo = TABS.find((t) => t.id === activeTab)!;
  const messages = messagesByTab[activeTab] ?? [];
  const isLoading = loadingByTab[activeTab] ?? false;

  return (
    <div className="flex h-[calc(100vh-64px)] flex-col bg-gradient-to-b from-[#0f1b33] to-[#081121]">
      {/* Header */}
      <div className="border-b border-white/10 px-6 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-500/20 ring-1 ring-indigo-400/30">
            <Bot className="h-5 w-5 text-indigo-400" />
          </div>
          <div>
            <h1 className="text-lg font-semibold text-white">AI HR Copilot</h1>
            <p className="text-xs text-slate-400">
              Powered by GPT-4o · Role-aware · Secure
            </p>
          </div>
          <div className="ml-auto flex items-center gap-1.5 rounded-full bg-emerald-500/10 px-3 py-1 text-xs text-emerald-400 ring-1 ring-emerald-500/20">
            <Shield className="h-3 w-3" />
            RBAC Enforced
          </div>
        </div>
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* Left sidebar — tabs */}
        <div className="hidden w-64 shrink-0 flex-col border-r border-white/10 md:flex">
          <nav className="space-y-1 p-3">
            {TABS.map((tab) => (
              <button
                key={tab.id}
                id={`tab-${tab.id}`}
                onClick={() => setActiveTab(tab.id)}
                className={`flex w-full items-start gap-3 rounded-xl px-3 py-2.5 text-left text-sm transition ${
                  activeTab === tab.id
                    ? "bg-gradient-to-r from-indigo-500/20 to-transparent text-white ring-1 ring-indigo-400/20"
                    : "text-slate-400 hover:bg-white/5 hover:text-white"
                }`}
              >
                <tab.icon className="mt-0.5 h-4 w-4 shrink-0" />
                <div>
                  <p className="font-medium leading-tight">{tab.label}</p>
                  <p className="mt-0.5 text-[11px] leading-tight opacity-60">
                    {tab.description}
                  </p>
                </div>
              </button>
            ))}
          </nav>

          {/* Sample questions (only for chat tabs) */}
          {activeTab !== "activity" && SAMPLES[activeTab] && (
            <div className="border-t border-white/10 p-3">
              <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                Try these
              </p>
              <div className="space-y-1">
                {SAMPLES[activeTab].map((q, i) => (
                  <button
                    key={i}
                    onClick={() => handleSend(activeTab, q)}
                    disabled={isLoading}
                    className="w-full rounded-lg px-2.5 py-1.5 text-left text-[11px] text-slate-400 transition hover:bg-white/5 hover:text-white disabled:opacity-40"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Disclaimer */}
          <div className="mt-auto border-t border-white/10 p-3">
            <div className="flex items-start gap-2 rounded-lg bg-amber-500/10 px-2.5 py-2 text-[10px] text-amber-400">
              <BookOpen className="mt-0.5 h-3 w-3 shrink-0" />
              <span>
                AI answers are grounded in your company's HR policies and data.
                Always verify critical decisions with HR.
              </span>
            </div>
          </div>
        </div>

        {/* Main content area */}
        <div className="flex flex-1 flex-col overflow-hidden">
          {/* Mobile tab switcher */}
          <div className="flex border-b border-white/10 md:hidden overflow-x-auto">
            {TABS.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex shrink-0 items-center justify-center gap-1.5 px-3 py-3 text-xs font-medium transition ${
                  activeTab === tab.id
                    ? "border-b-2 border-indigo-500 text-indigo-400"
                    : "text-slate-500"
                }`}
              >
                <tab.icon className="h-3.5 w-3.5" />
                {tab.label}
              </button>
            ))}
          </div>

          {/* Activity tab content */}
          {activeTab === "activity" ? (
            <div className="flex flex-1 flex-col overflow-hidden">
              {/* Activity header */}
              <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
                <div>
                  <p className="text-sm font-medium text-white">Recent AI Interactions</p>
                  <p className="text-xs text-slate-500">
                    Your last {activityItems.length} AI requests across all assistants
                  </p>
                </div>
                <button
                  onClick={fetchActivity}
                  disabled={activityLoading}
                  id="activity-refresh"
                  className="flex items-center gap-1.5 rounded-lg border border-white/10 px-3 py-1.5 text-xs text-slate-400 transition hover:bg-white/5 hover:text-white disabled:opacity-40"
                >
                  <RefreshCw className={`h-3 w-3 ${activityLoading ? "animate-spin" : ""}`} />
                  Refresh
                </button>
              </div>
              <div className="flex-1 overflow-y-auto">
                <AIActivityFeed items={activityItems} isLoading={activityLoading} />
              </div>
            </div>
          ) : (
            /* Chat tab content */
            <ChatPanel
              key={activeTab}
              placeholder={activeTabInfo.placeholder}
              onSend={(msg) => handleSend(activeTab, msg)}
              messages={messages}
              isLoading={isLoading}
              emptyState={
                <div className="flex flex-col items-center justify-center h-full min-h-[300px] gap-4 text-center px-8">
                  <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-indigo-500/10 ring-1 ring-indigo-400/20">
                    <activeTabInfo.icon className="h-8 w-8 text-indigo-400" />
                  </div>
                  <div>
                    <h3 className="text-lg font-semibold text-white">{activeTabInfo.label}</h3>
                    <p className="mt-1.5 text-sm text-slate-400 max-w-sm">
                      {activeTabInfo.description}
                    </p>
                  </div>
                  {SAMPLES[activeTab] && (
                    <div className="flex flex-wrap justify-center gap-2 mt-2">
                      {SAMPLES[activeTab].map((q, i) => (
                        <button
                          key={i}
                          onClick={() => handleSend(activeTab, q)}
                          className="rounded-full border border-white/10 px-3 py-1.5 text-xs text-slate-300 transition hover:border-indigo-400/30 hover:bg-indigo-500/10 hover:text-white"
                        >
                          {q}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              }
            />
          )}
        </div>
      </div>
    </div>
  );
}
