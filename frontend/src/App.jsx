import React, { useState, useEffect } from 'react';
import { MessageSquare, LayoutDashboard } from 'lucide-react';
import BuyerChatView from './components/BuyerChatView';
import MerchantDashboardView from './components/MerchantDashboardView';
import { fetchProducts } from './api';

export default function App() {
  const [activeTab, setActiveTab] = useState('chat'); // 'chat' | 'merchant'
  const [products, setProducts] = useState([]);

  useEffect(() => {
    fetchProducts()
      .then((data) => setProducts(data))
      .catch((err) => console.error('Failed to load products:', err));
  }, []);

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 flex flex-col font-sans">
      {/* Top Header */}
      <header className="border-b border-zinc-800 bg-zinc-950 sticky top-0 z-50">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
          {/* Small Project Title */}
          <div className="flex items-center space-x-2">
            <span className="text-base font-bold text-white tracking-tight">
              AgenticPay
            </span>
          </div>

          {/* Simple View Toggle Tabs */}
          <div className="flex items-center space-x-1 bg-zinc-900 p-1 rounded-lg border border-zinc-800">
            <button
              onClick={() => setActiveTab('chat')}
              className={`flex items-center space-x-2 px-3 py-1.5 rounded-md text-xs font-medium transition-colors cursor-pointer ${
                activeTab === 'chat'
                  ? 'bg-blue-600 text-white font-semibold'
                  : 'text-zinc-400 hover:text-zinc-200'
              }`}
            >
              <MessageSquare className="w-3.5 h-3.5" />
              <span>Buyer Chat</span>
            </button>

            <button
              onClick={() => setActiveTab('merchant')}
              className={`flex items-center space-x-2 px-3 py-1.5 rounded-md text-xs font-medium transition-colors cursor-pointer ${
                activeTab === 'merchant'
                  ? 'bg-blue-600 text-white font-semibold'
                  : 'text-zinc-400 hover:text-zinc-200'
              }`}
            >
              <LayoutDashboard className="w-3.5 h-3.5" />
              <span>Merchant Audit Dashboard</span>
            </button>
          </div>
        </div>
      </header>

      {/* Main View Area */}
      <main className="flex-1">
        {activeTab === 'chat' ? (
          <BuyerChatView products={products} />
        ) : (
          <MerchantDashboardView />
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-zinc-900 py-2.5 text-center text-xs text-zinc-600 bg-zinc-950">
        AgenticPay — AI Commerce with Bounded Gating & Audit Trail
      </footer>
    </div>
  );
}

