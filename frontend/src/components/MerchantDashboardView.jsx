import React, { useState, useEffect } from 'react';
import { ShieldCheck, RefreshCw, ChevronDown, ChevronUp, DollarSign, Lock, AlertTriangle, Eye, Layers, ShoppingBag } from 'lucide-react';
import { fetchAuditLogs } from '../api';

const NAVIGATION_SECTIONS = [
  { id: 'ALL', label: 'AI Financial Audit Trail', icon: Layers },
  { id: 'CHECKOUT_GENERATED', label: 'Checkouts Generated', icon: ShoppingBag },
  { id: 'CHECKOUT_BLOCKED', label: 'Gated Cap Blocks', icon: Lock },
  { id: 'STOCK_CHECK_FAILED', label: 'Stock Exceptions', icon: AlertTriangle },
  { id: 'PAYMENT_VERIFIED', label: 'Verified Payments', icon: ShieldCheck }
];

export default function MerchantDashboardView() {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expandedLogId, setExpandedLogId] = useState(null);
  const [activeSection, setActiveSection] = useState('ALL');

  const loadAuditLogs = async () => {
    setLoading(true);
    try {
      const data = await fetchAuditLogs();
      setLogs(data);
    } catch (err) {
      console.error('Failed to load audit logs:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAuditLogs();
  }, []);

  const toggleExpand = (id) => {
    setExpandedLogId(expandedLogId === id ? null : id);
  };

  // Exact 4 Enterprise KPI Metrics calculation
  const totalAICheckouts = logs.filter((l) => l.action_type === 'CHECKOUT_GENERATED' || l.action_type === 'PAYMENT_VERIFIED').length;
  const totalCartVolume = logs
    .filter((l) => l.action_type === 'PAYMENT_VERIFIED' || l.action_type === 'CHECKOUT_GENERATED')
    .reduce((sum, l) => sum + (l.amount_involved || 0), 0);
  const totalGatedBlocks = logs.filter((l) => l.action_type === 'CHECKOUT_BLOCKED').length;
  const totalStockExceptions = logs.filter((l) => l.action_type === 'STOCK_CHECK_FAILED').length;

  const filteredLogs = logs.filter((log) => {
    if (activeSection === 'ALL') return true;
    return log.action_type === activeSection;
  });

  return (
    <div className="max-w-7xl mx-auto px-4 py-6 text-zinc-100 font-sans">
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">

        {/* Left Sidebar Navigation */}
        <aside className="lg:col-span-3 space-y-4">
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
            <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-3 px-2">
              Financial Audit Sections
            </h3>
            <nav className="space-y-1">
              {NAVIGATION_SECTIONS.map((sec) => {
                const Icon = sec.icon;
                const isActive = activeSection === sec.id;
                const count = sec.id === 'ALL'
                  ? logs.length
                  : logs.filter((l) => l.action_type === sec.id).length;

                return (
                  <button
                    key={sec.id}
                    onClick={() => setActiveSection(sec.id)}
                    className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-xs font-medium transition-colors cursor-pointer ${
                      isActive
                        ? 'bg-blue-600 text-white font-semibold'
                        : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/60'
                    }`}
                  >
                    <div className="flex items-center space-x-2">
                      <Icon className="w-4 h-4" />
                      <span>{sec.label}</span>
                    </div>
                    <span
                      className={`text-[10px] px-1.5 py-0.5 rounded font-mono ${
                        isActive ? 'bg-blue-700 text-white' : 'bg-zinc-800 text-zinc-400'
                      }`}
                    >
                      {count}
                    </span>
                  </button>
                );
              })}
            </nav>
          </div>

          {/* Quick Gating Rule Status */}
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 text-xs text-zinc-400 space-y-2">
            <div className="flex items-center space-x-2 text-white font-semibold">
              <ShieldCheck className="w-4 h-4 text-blue-400" />
              <span>Bounded AI Safeguards</span>
            </div>
            <p className="text-[11px] leading-relaxed text-zinc-400">
              15% Max Discount Cap strictly enforced in backend. Explainable financial audit traces stored in PostgreSQL.
            </p>
          </div>
        </aside>

        {/* Right Main Info Area */}
        <main className="lg:col-span-9 space-y-6">

          {/* Header & Refresh */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-zinc-900 border border-zinc-800 p-4 rounded-xl">
            <div>
              <h2 className="text-lg font-bold text-white tracking-tight">Merchant Audit Dashboard</h2>
              <p className="text-xs text-zinc-400">
                Enterprise AI Financial Audit Trail & Safety Exception Monitoring
              </p>
            </div>

            <button
              onClick={loadAuditLogs}
              className="flex items-center space-x-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-semibold px-3 py-2 rounded-lg border border-zinc-700 transition-colors cursor-pointer self-start sm:self-auto"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
              <span>Refresh Trail</span>
            </button>
          </div>

          {/* Clean Top KPI Cards (Exactly 4 Cards) */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {/* KPI 1: Total AI Checkouts */}
            <div className="bg-zinc-900 border border-zinc-800 p-4 rounded-xl">
              <span className="text-[11px] font-medium text-zinc-400 block">Total AI Checkouts</span>
              <p className="text-2xl font-bold text-white mt-1">{totalAICheckouts}</p>
              <span className="text-[10px] text-zinc-500">Successful Orders</span>
            </div>

            {/* KPI 2: Total Cart Volume */}
            <div className="bg-zinc-900 border border-zinc-800 p-4 rounded-xl">
              <span className="text-[11px] font-medium text-zinc-400 block">Total Cart Volume</span>
              <p className="text-2xl font-bold text-white mt-1">${totalCartVolume.toFixed(2)}</p>
              <span className="text-[10px] text-zinc-500">Verified & Generated</span>
            </div>

            {/* KPI 3: Gated Blocks */}
            <div className="bg-zinc-900 border border-zinc-800 p-4 rounded-xl">
              <span className="text-[11px] font-medium text-zinc-400 block">Gated Blocks</span>
              <p className="text-2xl font-bold text-white mt-1">{totalGatedBlocks}</p>
              <span className="text-[10px] text-zinc-500">&gt;15% Cap Rejections</span>
            </div>

            {/* KPI 4: Stock Exceptions */}
            <div className="bg-zinc-900 border border-zinc-800 p-4 rounded-xl">
              <span className="text-[11px] font-medium text-zinc-400 block">Stock Exceptions</span>
              <p className="text-2xl font-bold text-white mt-1">{totalStockExceptions}</p>
              <span className="text-[10px] text-zinc-500">Out-of-Stock Pivots</span>
            </div>
          </div>

          {/* AI Financial Audit Trail Table Stream */}
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden shadow-lg">
            <div className="px-4 py-3 border-b border-zinc-800 flex items-center justify-between text-xs text-zinc-400 font-medium">
              <span className="font-semibold text-white">AI Financial Audit Trail</span>
              <span>{filteredLogs.length} Entries</span>
            </div>

            <div className="divide-y divide-zinc-800">
              {loading ? (
                <div className="p-8 text-center text-xs text-zinc-400 flex flex-col items-center justify-center space-y-2">
                  <RefreshCw className="w-5 h-5 animate-spin text-blue-500" />
                  <span>Loading audit trail from database...</span>
                </div>
              ) : filteredLogs.length === 0 ? (
                <div className="p-8 text-center text-xs text-zinc-500">
                  No financial events recorded yet. Complete checkouts or trigger discount gating in Buyer Chat to generate audit records!
                </div>
              ) : (
                filteredLogs.map((log) => {
                  const isExpanded = expandedLogId === log.id;

                  return (
                    <div key={log.id} className="transition-colors hover:bg-zinc-800/40">
                      {/* Table Row Content */}
                      <div
                        onClick={() => toggleExpand(log.id)}
                        className="p-4 flex items-start justify-between cursor-pointer space-x-3 text-xs"
                      >
                        <div className="space-y-1 flex-1 min-w-0">
                          <div className="flex items-center space-x-2">
                            <span className="font-mono text-zinc-400 font-semibold">#{log.id}</span>
                            <span className="bg-zinc-800 text-zinc-200 border border-zinc-700 px-2 py-0.5 rounded font-mono text-[10px]">
                              {log.action_type}
                            </span>
                            <span className="text-zinc-500 text-[11px]">
                              {new Date(log.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                            </span>
                          </div>

                          <p className="text-zinc-300 truncate font-sans text-sm">
                            {log.ai_reasoning}
                          </p>
                        </div>

                        <div className="flex items-center space-x-3 shrink-0">
                          <span className="font-semibold text-white">
                            {log.amount_involved > 0 ? `$${log.amount_involved.toFixed(2)}` : '—'}
                          </span>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              toggleExpand(log.id);
                            }}
                            className="p-1 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition-colors cursor-pointer"
                          >
                            {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                          </button>
                        </div>
                      </div>

                      {/* Expandable Decision Trace */}
                      {isExpanded && (
                        <div className="p-4 bg-zinc-950 border-t border-zinc-800 text-xs space-y-3">
                          <div className="flex items-center justify-between text-zinc-400 border-b border-zinc-800 pb-2">
                            <div className="flex items-center space-x-1.5 text-blue-400 font-semibold">
                              <Eye className="w-4 h-4" />
                              <span>Explainable AI Decision Audit Trace</span>
                            </div>
                            <span className="text-[11px] font-mono text-zinc-500">
                              Timestamp: {new Date(log.timestamp).toLocaleString()}
                            </span>
                          </div>

                          <div>
                            <span className="text-zinc-500 block text-[11px] mb-1 font-medium">Explainable Reasoning & Rule Evaluation:</span>
                            <div className="p-3 bg-zinc-900 rounded border border-zinc-800 text-zinc-200 font-mono text-xs leading-relaxed">
                              {log.ai_reasoning}
                            </div>
                          </div>

                          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1 font-mono text-[11px]">
                            <div className="bg-zinc-900 p-2 rounded border border-zinc-800">
                              <span className="text-zinc-500 block">Action Code:</span>
                              <span className="text-zinc-200 font-semibold">{log.action_type}</span>
                            </div>
                            <div className="bg-zinc-900 p-2 rounded border border-zinc-800">
                              <span className="text-zinc-500 block">Log ID:</span>
                              <span className="text-zinc-200 font-semibold">#{log.id}</span>
                            </div>
                            <div className="bg-zinc-900 p-2 rounded border border-zinc-800">
                              <span className="text-zinc-500 block">Amount Involved:</span>
                              <span className="text-blue-400 font-semibold">${log.amount_involved.toFixed(2)}</span>
                            </div>
                            <div className="bg-zinc-900 p-2 rounded border border-zinc-800">
                              <span className="text-zinc-500 block">Rule Status:</span>
                              <span className="text-emerald-400 font-semibold">Enforced & Logged</span>
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          </div>

        </main>
      </div>
    </div>
  );
}
