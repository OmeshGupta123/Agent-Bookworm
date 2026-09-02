import React, { useState, useEffect } from 'react';
import { ShieldCheck, RefreshCw, ChevronDown, ChevronUp, Lock, AlertTriangle, Eye, Layers, XCircle, Trash2 } from 'lucide-react';
import { fetchAuditLogs, clearAuditLogs } from '../api';

const NAVIGATION_SECTIONS = [
  { id: 'ALL', label: 'AI Financial Audit Trail', icon: Layers },
  { id: 'PAYMENT_VERIFIED', label: 'Verified Payments', icon: ShieldCheck },
  { id: 'PAYMENT_FAILED', label: 'Failed Payments', icon: XCircle },
  { id: 'CHECKOUT_BLOCKED', label: 'Gated Cap Blocks', icon: Lock },
  { id: 'STOCK_CHECK_FAILED', label: 'Stock Exceptions', icon: AlertTriangle }
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
      setLogs(data || []);
    } catch (err) {
      console.error('Failed to load audit logs:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleClearLogs = async () => {
    setLoading(true);
    try {
      await clearAuditLogs();
      setLogs([]);
    } catch (err) {
      console.error('Failed to clear audit trail:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let isMounted = true;
    fetchAuditLogs()
      .then((data) => {
        if (isMounted) {
          setLogs(data || []);
          setLoading(false);
        }
      })
      .catch((err) => {
        console.error('Failed to load audit logs:', err);
        if (isMounted) setLoading(false);
      });
    return () => {
      isMounted = false;
    };
  }, []);

  const toggleExpand = (id) => {
    setExpandedLogId(expandedLogId === id ? null : id);
  };

  // Only showcase the 4 specified financial & safety actions:
  // Verified Payments, Failed Payments, Gated Cap Blocks, Stock Exceptions — nothing else
  const financialLogs = logs.filter((log) =>
    ['PAYMENT_VERIFIED', 'PAYMENT_FAILED', 'CHECKOUT_BLOCKED', 'STOCK_CHECK_FAILED'].includes(log.action_type)
  );

  const filteredLogs = financialLogs.filter((log) => {
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
                  ? financialLogs.length
                  : financialLogs.filter((l) => l.action_type === sec.id).length;

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

          {/* Bounded AI Safeguards Summary */}
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 text-xs text-zinc-400 space-y-2">
            <div className="flex items-center space-x-2 text-white font-semibold">
              <ShieldCheck className="w-4 h-4 text-blue-400" />
              <span>Bounded AI Safeguards</span>
            </div>
            <p className="text-[11px] leading-relaxed text-zinc-400">
              15% Max Discount Cap strictly enforced in backend. Explainable financial audit traces stored persistently.
            </p>
          </div>
        </aside>

        {/* Right Main Panel - Audit Feed Only */}
        <main className="lg:col-span-9 space-y-6">

          {/* Header & Refresh */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-zinc-900 border border-zinc-800 p-4 rounded-xl">
            <div>
              <h2 className="text-lg font-bold text-white tracking-tight">Merchant Audit Dashboard</h2>
              <p className="text-xs text-zinc-400">
                Enterprise AI Financial Audit Trail & Safety Exception Monitoring
              </p>
            </div>

            <div className="flex items-center space-x-2 self-start sm:self-auto">
              <button
                onClick={handleClearLogs}
                disabled={loading || logs.length === 0}
                className="flex items-center space-x-1.5 bg-zinc-800/80 hover:bg-red-950/50 hover:text-red-300 text-zinc-300 text-xs font-semibold px-3 py-2 rounded-lg border border-zinc-700/80 hover:border-red-800/60 transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
                title="Clear audit trail for a fresh start"
              >
                <Trash2 className="w-3.5 h-3.5" />
                <span>Clear Trail</span>
              </button>

              <button
                onClick={loadAuditLogs}
                className="flex items-center space-x-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-semibold px-3 py-2 rounded-lg border border-zinc-700 transition-colors cursor-pointer"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
                <span>Refresh Trail</span>
              </button>
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

                  // Parse clean JSON metadata if present
                  let meta = null;
                  if (log.log_metadata) {
                    try {
                      meta = typeof log.log_metadata === 'string' ? JSON.parse(log.log_metadata) : log.log_metadata;
                    } catch {
                      meta = null;
                    }
                  }

                  // Fallback metadata values
                  const statusLabel = meta?.status || (
                    log.action_type === 'PAYMENT_VERIFIED' ? 'Verified' :
                    log.action_type === 'CHECKOUT_BLOCKED' ? 'Blocked' :
                    log.action_type === 'PAYMENT_FAILED' ? 'Failed' : 'Stock Exception'
                  );

                  const itemsList = meta?.purchased_items || ["Book Order"];
                  const orderIdStr = meta?.order_id || null;
                  const paymentIdStr = meta?.payment_id || null;
                  const failureReason = meta?.failure_reason || (
                    log.action_type === 'CHECKOUT_BLOCKED' ? 'Requested discount exceeds maximum allowed cap of 15%.' :
                    log.action_type === 'STOCK_CHECK_FAILED' ? 'Requested item is out of stock.' :
                    log.action_type === 'PAYMENT_FAILED' ? (log.ai_reasoning || 'Payment transaction failed or user cancelled checkout.') : null
                  );

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
                            <span className={`px-2 py-0.5 rounded font-mono text-[10px] font-semibold border ${
                              log.action_type === 'PAYMENT_VERIFIED'
                                ? 'bg-emerald-950/80 text-emerald-300 border-emerald-800/60'
                                : log.action_type === 'CHECKOUT_BLOCKED'
                                ? 'bg-red-950/80 text-red-300 border-red-800/60'
                                : log.action_type === 'PAYMENT_FAILED'
                                ? 'bg-rose-950/80 text-rose-300 border-rose-800/60'
                                : log.action_type === 'STOCK_CHECK_FAILED'
                                ? 'bg-amber-950/80 text-amber-300 border-amber-800/60'
                                : 'bg-blue-950/80 text-blue-300 border-blue-800/60'
                            }`}>
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
                          <span className="font-semibold text-white font-mono text-sm">
                            {log.amount_involved > 0 ? `₹${log.amount_involved.toFixed(2)}` : '—'}
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

                      {/* Clean Transaction Summary Expanded View */}
                      {isExpanded && (
                        <div className="p-4 bg-zinc-950 border-t border-zinc-800 text-xs space-y-4 font-sans">
                          <div className="flex items-center justify-between text-zinc-400 border-b border-zinc-800 pb-2">
                            <div className="flex items-center space-x-1.5 text-blue-400 font-semibold">
                              <Eye className="w-4 h-4" />
                              <span>Clean Transaction Summary</span>
                            </div>
                            <span className="text-[11px] font-mono text-zinc-500">
                              Recorded: {new Date(log.timestamp).toLocaleString()}
                            </span>
                          </div>

                          {/* Transaction Summary Card */}
                          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 space-y-3">
                            <div className="flex items-center justify-between">
                              <span className="text-zinc-400 text-xs font-medium">Status:</span>
                              <span className={`px-2.5 py-0.5 rounded-full text-xs font-semibold ${
                                statusLabel === 'Verified' ? 'bg-emerald-900/60 text-emerald-300 border border-emerald-700/50' :
                                statusLabel === 'Blocked' ? 'bg-red-900/60 text-red-300 border border-red-700/50' :
                                statusLabel === 'Failed' ? 'bg-rose-900/60 text-rose-300 border border-rose-700/50' :
                                statusLabel === 'Stock Exception' ? 'bg-amber-900/60 text-amber-300 border border-amber-700/50' :
                                'bg-blue-900/60 text-blue-300 border border-blue-700/50'
                              }`}>
                                {statusLabel}
                              </span>
                            </div>

                            <div className="flex items-start justify-between border-t border-zinc-800/80 pt-2.5">
                              <span className="text-zinc-400 text-xs font-medium">Products:</span>
                              <div className="text-right space-y-1">
                                {itemsList.map((item, idx) => (
                                  <div key={idx} className="text-white font-medium text-xs">
                                    • {item}
                                  </div>
                                ))}
                              </div>
                            </div>

                            <div className="flex items-center justify-between border-t border-zinc-800/80 pt-2.5">
                              <span className="text-zinc-400 text-xs font-medium">Amount:</span>
                              <span className="text-white font-bold font-mono text-sm">
                                {log.amount_involved > 0 ? `₹${log.amount_involved.toFixed(2)}` : '—'}
                              </span>
                            </div>

                            {orderIdStr && (
                              <div className="flex items-center justify-between border-t border-zinc-800/80 pt-2.5">
                                <span className="text-zinc-400 text-xs font-medium">Order ID:</span>
                                <span className="text-zinc-300 font-mono text-xs font-semibold">{orderIdStr}</span>
                              </div>
                            )}

                            {paymentIdStr && (
                              <div className="flex items-center justify-between border-t border-zinc-800/80 pt-2.5">
                                <span className="text-zinc-400 text-xs font-medium">Transaction ID:</span>
                                <span className="text-emerald-400 font-mono text-xs font-semibold">{paymentIdStr}</span>
                              </div>
                            )}

                            {failureReason && (
                              <div className="border-t border-zinc-800/80 pt-2.5 space-y-1">
                                <span className="text-zinc-400 text-xs font-medium block">Reason:</span>
                                <p className="text-rose-400 bg-rose-950/40 border border-rose-900/40 p-2.5 rounded-lg text-xs leading-relaxed">
                                  {failureReason}
                                </p>
                              </div>
                            )}
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
