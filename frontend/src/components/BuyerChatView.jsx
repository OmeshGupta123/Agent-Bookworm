import React, { useState, useEffect, useRef } from 'react';
import { Send, User, Bot, Info, ShoppingCart, Trash2, CreditCard, ArrowRight, X } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { sendChatMessage } from '../api';
import CheckoutCard from './CheckoutCard';

const DEMO_PROMPTS = [
  "Recommend 3 good Self-Growth books.",
  "I like Stephen King. What else has he written?",
  "Can I get a 20% discount on Atomic Habits?",
  "I want to buy The Prince 1st Edition Signed"
];

// Sub-component: Dynamic Action Chips returned directly from the backend API
function DynamicActionChips({ actions, onSend, disabled }) {
  if (!actions || actions.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-2 pt-2">
      {actions.map((actionText, idx) => {
        const isCheckout = actionText.toLowerCase().includes('checkout');
        return (
          <button
            key={idx}
            onClick={() => onSend(actionText)}
            disabled={disabled}
            className={`text-xs px-3 py-1.5 rounded-lg border font-medium flex items-center space-x-1.5 transition-all cursor-pointer disabled:opacity-50 shadow-sm ${
              isCheckout
                ? 'bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-300 border-emerald-500/40'
                : 'bg-blue-600/20 hover:bg-blue-600/30 text-blue-300 border-blue-500/40'
            }`}
          >
            {isCheckout ? <CreditCard className="w-3.5 h-3.5" /> : <ArrowRight className="w-3.5 h-3.5" />}
            <span>{actionText}</span>
          </button>
        );
      })}
    </div>
  );
}

export default function BuyerChatView({ products }) {
  const [messages, setMessages] = useState([
    {
      id: 'init-1',
      role: 'assistant',
      content: "Hello! Welcome to Agent Bookworm Bookstore. I am your AI Commerce Assistant for our 200-book collection. I can negotiate bounded discounts (up to 15%), recommend companion reads, manage your shopping cart, and generate instant Razorpay checkouts directly in this chat. How can I help you today?",
      actionType: null,
      widget: null,
      suggestedActions: ["Recommend 3 good Self-Growth books."]
    }
  ]);

  const [cart, setCart] = useState([]);
  const [inputText, setInputText] = useState('');
  const [loading, setLoading] = useState(false);
  const [isCartOpen, setIsCartOpen] = useState(false);

  const messagesEndRef = useRef(null);
  const cartPopoverRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading]);

  // Outside Click Listener to automatically close Cart Popover
  useEffect(() => {
    function handleClickOutside(event) {
      if (cartPopoverRef.current && !cartPopoverRef.current.contains(event.target)) {
        setIsCartOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, []);

  const handleSend = async (messageToSend) => {
    const text = messageToSend || inputText;
    if (!text.trim() || loading) return;

    setIsCartOpen(false);

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
        widget: response.checkout_widget,
        suggestedActions: response.suggested_actions || []
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
    setCart([]);
    setIsCartOpen(false);
    const successMsg = {
      id: `sys-paid-${Date.now()}`,
      role: 'assistant',
      content: "Payment verified successfully! Thank you for your purchase. Your order has been logged in our database and the Merchant Audit Dashboard.",
      actionType: 'PAYMENT_VERIFIED',
      widget: null,
      suggestedActions: []
    };

    setMessages((prev) => [...prev, successMsg]);
  };

  const handleRemoveCartItem = (bookName) => {
    if (!bookName) return;
    setIsCartOpen(false);
    handleSend(`remove ${bookName}`);
  };

  const cartTotal = cart.reduce((sum, item) => sum + ((item.final_price !== undefined ? item.final_price : (item.price || 0)) * (item.quantity || 1)), 0);

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)] max-w-3xl mx-auto px-4 py-4 font-sans text-zinc-100">
      {/* Top Header Banner */}
      <div className="flex items-center justify-between border-b border-zinc-800/80 pb-3 mb-3 text-xs text-zinc-400">
        <div className="flex items-center space-x-2">
          <span className="font-semibold text-white">Agent Bookworm Bookstore</span>
          <span className="text-zinc-500">•</span>
          <span className="text-zinc-400">AI Commerce Assistant</span>
        </div>
        
        <div className="flex items-center space-x-3">
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

              {/* Message Content & Dynamic Action Chips */}
              <div className="space-y-2 flex-1">
                <div
                  className={`p-3.5 rounded-2xl text-xs sm:text-sm leading-relaxed ${
                    msg.role === 'user'
                      ? 'bg-blue-600 text-white rounded-tr-none'
                      : 'bg-zinc-900 border border-zinc-800 text-zinc-100 rounded-tl-none'
                  }`}
                >
                  {/* Clean Formatted Markdown Rendering */}
                  <div className="prose prose-invert prose-xs max-w-none text-zinc-100 font-sans">
                    <ReactMarkdown
                      components={{
                        p: ({ node, ...props }) => <p className="mb-1.5 last:mb-0 leading-relaxed" {...props} />,
                        strong: ({ node, ...props }) => <strong className="font-semibold text-white" {...props} />,
                        em: ({ node, ...props }) => <em className="italic text-zinc-200" {...props} />,
                        ul: ({ node, ...props }) => <ul className="list-disc pl-4 space-y-1 my-1.5" {...props} />,
                        li: ({ node, ...props }) => <li className="text-zinc-200" {...props} />
                      }}
                    >
                      {msg.content}
                    </ReactMarkdown>
                  </div>

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

                {/* Render Dynamic Backend Action Chips below assistant messages */}
                {msg.role === 'assistant' && !msg.widget && (
                  <DynamicActionChips
                    actions={msg.suggestedActions}
                    onSend={handleSend}
                    disabled={loading}
                  />
                )}

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

      {/* Suggested Demo Scenario Chips */}
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

      {/* Input Form Bar with Left-Aligned Cart Icon & Smooth Popover */}
      <div className="relative" ref={cartPopoverRef}>

        {/* Smooth Cart Popover Overlay */}
        {isCartOpen && (
          <div className="absolute bottom-full left-0 mb-3 w-80 bg-zinc-900 border border-zinc-800 rounded-2xl shadow-2xl p-4 text-zinc-100 font-sans z-50 transition-all duration-200 ease-in-out transform origin-bottom-left animate-in fade-in slide-in-from-bottom-2">
            <div className="flex items-center justify-between border-b border-zinc-800 pb-2.5 mb-2.5">
              <div className="flex items-center space-x-2 font-semibold text-xs text-white">
                <ShoppingCart className="w-4 h-4 text-blue-400" />
                <span>Your Shopping Cart ({cart.length})</span>
              </div>
              <button
                type="button"
                onClick={() => setIsCartOpen(false)}
                className="text-zinc-400 hover:text-white p-1 rounded-md hover:bg-zinc-800 transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {cart.length === 0 ? (
              <div className="py-6 text-center text-xs text-zinc-500">
                Your cart is currently empty. Ask for a book recommendation to add items!
              </div>
            ) : (
              <div className="space-y-3">
                <div className="max-h-48 overflow-y-auto space-y-2 pr-1">
                  {cart.map((item, idx) => (
                    <div key={idx} className="flex items-start justify-between bg-zinc-950 p-2 rounded-lg border border-zinc-800 text-xs">
                      <div className="min-w-0 flex-1 pr-2">
                        <div className="font-medium text-white truncate">{item.name}</div>
                        <div className="text-[10px] text-zinc-500 flex items-center space-x-1.5 mt-0.5">
                          <span>₹{(item.final_price || item.price).toFixed(2)}</span>
                          {item.discount_percentage > 0 && (
                            <span className="text-blue-400 font-mono">({item.discount_percentage}% OFF)</span>
                          )}
                        </div>
                      </div>

                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleRemoveCartItem(item.name);
                        }}
                        title="Remove item"
                        className="p-1 text-zinc-500 hover:text-red-400 hover:bg-zinc-800 rounded transition-colors cursor-pointer shrink-0 mt-0.5"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  ))}
                </div>

                <div className="pt-2 border-t border-zinc-800 flex items-center justify-between text-xs">
                  <span className="text-zinc-400">Total Amount:</span>
                  <span className="font-bold text-white font-mono text-sm">₹{cartTotal.toFixed(2)}</span>
                </div>

                <button
                  type="button"
                  onClick={() => handleSend("checkout now")}
                  className="w-full py-2 bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold rounded-xl transition-colors flex items-center justify-center space-x-1.5 shadow-md cursor-pointer"
                >
                  <CreditCard className="w-3.5 h-3.5" />
                  <span>Proceed to Checkout</span>
                </button>
              </div>
            )}
          </div>
        )}

        {/* Input Form with Left-side Cart Icon */}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
          className="flex items-center bg-zinc-900 border border-zinc-800 rounded-xl p-1.5 focus-within:border-zinc-700 transition-colors shadow-lg"
        >
          <button
            type="button"
            onClick={() => setIsCartOpen(!isCartOpen)}
            className="relative p-2 text-zinc-400 hover:text-white bg-zinc-800/80 hover:bg-zinc-800 rounded-lg transition-colors cursor-pointer mr-1.5"
            title="View Shopping Cart"
          >
            <ShoppingCart className="w-4 h-4 text-blue-400" />
            {cart.length > 0 && (
              <span className="absolute -top-1 -right-1 bg-blue-600 text-white font-mono text-[9px] font-bold w-4 h-4 rounded-full flex items-center justify-center border border-zinc-900">
                {cart.length}
              </span>
            )}
          </button>

          <input
            type="text"
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            placeholder="Ask a question, request books, or type 'checkout'..."
            className="flex-1 bg-transparent border-none text-xs sm:text-sm text-zinc-100 placeholder-zinc-500 focus:outline-none px-2 py-1"
            disabled={loading}
          />
          <button
            type="submit"
            disabled={!inputText.trim() || loading}
            className="p-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg transition-colors disabled:opacity-40 cursor-pointer shadow-sm ml-1"
          >
            <Send className="w-3.5 h-3.5" />
          </button>
        </form>
      </div>
    </div>
  );
}
