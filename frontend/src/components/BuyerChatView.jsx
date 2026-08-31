import React, { useState, useEffect, useRef } from 'react';
import { Send, User, Bot, Info, ShoppingCart } from 'lucide-react';
import { sendChatMessage } from '../api';
import CheckoutCard from './CheckoutCard';

const DEMO_PROMPTS = [
  "Recommend 3 good Self-Growth books.",
  "I like Stephen King. What else has he written?",
  "Can I get a 20% discount on Atomic Habits?",
  "I want to buy The Prince 1st Edition Signed"
];

export default function BuyerChatView({ products }) {
  const [messages, setMessages] = useState([
    {
      id: 'init-1',
      role: 'assistant',
      content: "Hello! Welcome to AgenticPay Bookstore. I am your AI Commerce Assistant for our 200-book collection. I can negotiate bounded discounts (up to 15%), recommend companion reads, manage your shopping cart, and generate instant Razorpay checkouts directly in this chat. How can I help you today?",
      actionType: null,
      widget: null
    }
  ]);

  const [cart, setCart] = useState([]);
  const [inputText, setInputText] = useState('');
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading]);

  const handleSend = async (messageToSend) => {
    const text = messageToSend || inputText;
    if (!text.trim() || loading) return;

    const userMsg = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: text
    };

    setMessages((prev) => [...prev, userMsg]);
    setInputText('');
    setLoading(true);

    try {
      const historyPayload = messages.map((m) => ({
        role: m.role,
        content: m.content
      }));

      const response = await sendChatMessage(text, historyPayload, cart);

      if (response.cart) {
        setCart(response.cart);
      }

      const aiMsg = {
        id: `ai-${Date.now()}`,
        role: 'assistant',
        content: response.reply,
        actionType: response.action_type,
        widget: response.checkout_widget
      };

      setMessages((prev) => [...prev, aiMsg]);
    } catch (err) {
      console.error('Chat error:', err);
      const errorMsg = {
        id: `err-${Date.now()}`,
        role: 'assistant',
        content: "Sorry, I encountered a connection issue with the backend server. Please make sure the API server is running."
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setLoading(false);
    }
  };

  const handlePaymentSuccess = (verifyResponse) => {
    // 1. Empty shopping cart state
    setCart([]);

    // 2. Append system confirmation message to chat thread
    const successMsg = {
      id: `sys-paid-${Date.now()}`,
      role: 'assistant',
      content: "Payment verified successfully! Thank you for your purchase. Your order has been logged in our database and the Merchant Audit Dashboard.",
      actionType: 'PAYMENT_VERIFIED',
      widget: null
    };

    setMessages((prev) => [...prev, successMsg]);
  };

  const cartTotal = cart.reduce((sum, item) => sum + (item.final_price || 0), 0);

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)] max-w-3xl mx-auto px-4 py-4 font-sans text-zinc-100">
      {/* Small Chat Header / Banner */}
      <div className="flex items-center justify-between border-b border-zinc-800/80 pb-3 mb-3 text-xs text-zinc-400">
        <div className="flex items-center space-x-2">
          <span className="font-semibold text-white">AgenticPay Bookstore</span>
          <span className="text-zinc-500">•</span>
          <span className="text-zinc-400">AI Commerce Assistant</span>
        </div>
        
        <div className="flex items-center space-x-3">
          {/* Active Cart Counter */}
          <div className="flex items-center space-x-1.5 bg-zinc-900 border border-zinc-800 px-2.5 py-1 rounded-lg text-zinc-200">
            <ShoppingCart className="w-3.5 h-3.5 text-blue-400" />
            <span className="font-mono text-[11px]">
              Cart ({cart.length}) ${cartTotal.toFixed(2)}
            </span>
          </div>
          <div className="text-zinc-500 font-mono text-[11px] hidden sm:block">
            15% Discount Cap Active
          </div>
        </div>
      </div>

      {/* Chat Messages Feed */}
      <div className="flex-1 overflow-y-auto pr-2 space-y-4">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div className={`flex items-start max-w-2xl space-x-3 ${msg.role === 'user' ? 'flex-row-reverse space-x-reverse' : ''}`}>
              {/* Avatar */}
              <div
                className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 text-xs font-semibold ${
                  msg.role === 'user'
                    ? 'bg-blue-600 text-white'
                    : 'bg-zinc-800 text-zinc-300 border border-zinc-700'
                }`}
              >
                {msg.role === 'user' ? <User className="w-3.5 h-3.5" /> : <Bot className="w-3.5 h-3.5" />}
              </div>

              {/* Message Content */}
              <div className="space-y-2">
                <div
                  className={`p-3.5 rounded-2xl text-xs sm:text-sm leading-relaxed ${
                    msg.role === 'user'
                      ? 'bg-blue-600 text-white rounded-tr-none'
                      : 'bg-zinc-900 border border-zinc-800 text-zinc-100 rounded-tl-none'
                  }`}
                >
                  <p className="whitespace-pre-wrap">{msg.content}</p>

                  {msg.actionType === 'GRACEFUL_FAILURE' && (
                    <div className="mt-2 text-xs bg-zinc-950 text-amber-400 p-2 rounded-lg border border-amber-900/50 flex items-center gap-1.5">
                      <Info className="w-3.5 h-3.5 shrink-0" />
                      <span>Item out-of-stock. Stock exception audit logged.</span>
                    </div>
                  )}

                  {msg.actionType === 'PAYMENT_VERIFIED' && (
                    <div className="mt-2 text-xs bg-emerald-950/60 text-emerald-400 p-2 rounded-lg border border-emerald-900/50 flex items-center gap-1.5 font-medium">
                      <Info className="w-3.5 h-3.5 shrink-0 text-emerald-400" />
                      <span>Razorpay payment signature verified & logged to Merchant Audit Trail.</span>
                    </div>
                  )}
                </div>

                {/* Embedded Razorpay Checkout Widget */}
                {msg.widget && (
                  <CheckoutCard
                    widgetData={msg.widget}
                    onPaymentSuccess={handlePaymentSuccess}
                  />
                )}
              </div>
            </div>
          </div>
        ))}

        {/* Small Animation When AI Thinking */}
        {loading && (
          <div className="flex justify-start">
            <div className="flex items-center space-x-2 bg-zinc-900 border border-zinc-800 px-3 py-2 rounded-xl text-xs text-zinc-400">
              <span className="text-zinc-400 font-medium">Thinking</span>
              <div className="flex space-x-1 items-center">
                <span className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-pulse-dot-1"></span>
                <span className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-pulse-dot-2"></span>
                <span className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-pulse-dot-3"></span>
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Suggested Prompts */}
      <div className="py-2">
        <div className="flex flex-wrap gap-1.5">
          {DEMO_PROMPTS.map((promptText, idx) => (
            <button
              key={idx}
              onClick={() => handleSend(promptText)}
              disabled={loading}
              className="text-xs bg-zinc-900 hover:bg-zinc-800 text-zinc-300 border border-zinc-800 px-3 py-1.5 rounded-lg transition-colors cursor-pointer disabled:opacity-50"
            >
              "{promptText}"
            </button>
          ))}
        </div>
      </div>

      {/* Input Form */}
      <div className="mt-1">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
          className="flex items-center bg-zinc-900 border border-zinc-800 rounded-xl p-1.5 focus-within:border-zinc-700 transition-colors"
        >
          <input
            type="text"
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            placeholder="Ask a question, add/remove books, or type 'checkout'..."
            className="flex-1 bg-transparent border-none text-xs sm:text-sm text-zinc-100 placeholder-zinc-500 focus:outline-none px-3 py-1"
            disabled={loading}
          />
          <button
            type="submit"
            disabled={!inputText.trim() || loading}
            className="p-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg transition-colors disabled:opacity-40 cursor-pointer"
          >
            <Send className="w-3.5 h-3.5" />
          </button>
        </form>
      </div>
    </div>
  );
}
