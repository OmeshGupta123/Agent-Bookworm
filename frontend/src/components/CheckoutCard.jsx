import React, { useState, useRef } from 'react';
import { CreditCard, CheckCircle2, AlertCircle, ShoppingBag, ShieldCheck, Tag, XCircle } from 'lucide-react';
import { verifyPayment, reportPaymentFailure } from '../api';

export default function CheckoutCard({ widgetData, onPaymentSuccess }) {
  const [loading, setLoading] = useState(false);
  const [paymentStatus, setPaymentStatus] = useState('idle'); // 'idle' | 'success' | 'error'
  const [errorMessage, setErrorMessage] = useState('');
  const hasLoggedFailure = useRef(false);

  if (!widgetData) return null;

  const {
    order_id,
    razorpay_order_id,
    razorpay_key_id,
    items,
    original_total,
    total_discount,
    discount_percentage,
    final_amount,
    currency
  } = widgetData;

  const cartItemList = items && items.length > 0 ? items : [
    { name: "Atomic Habits", final_price: final_amount, price: original_total, discount_percentage: discount_percentage }
  ];

  const calculatedOriginalTotal = original_total !== undefined && original_total !== null
    ? original_total
    : cartItemList.reduce((sum, i) => sum + (i.price || i.final_price || 0) * (i.quantity || 1), 0);

  const calculatedFinalAmount = final_amount !== undefined && final_amount !== null
    ? final_amount
    : cartItemList.reduce((sum, i) => sum + (i.final_price || i.price || 0) * (i.quantity || 1), 0);

  const calculatedTotalDiscount = total_discount !== undefined && total_discount !== null
    ? total_discount
    : Math.max(0, calculatedOriginalTotal - calculatedFinalAmount);
  const itemNames = cartItemList.map((i) => i.name);

  const logFailure = async (reason) => {
    if (!hasLoggedFailure.current) {
      hasLoggedFailure.current = true;
      try {
        await reportPaymentFailure(razorpay_order_id, reason, itemNames);
      } catch (err) {
        console.error('Failed to report payment failure:', err);
      }
    }
  };

  const handleSimulateFailure = async () => {
    setLoading(true);
    setPaymentStatus('error');
    const reason = "Payment declined: Insufficient funds / Simulated card decline.";
    setErrorMessage(reason);
    await logFailure(reason);
    setLoading(false);
  };

  const handleOpenRazorpay = () => {
    setLoading(true);
    setPaymentStatus('idle');
    setErrorMessage('');
    hasLoggedFailure.current = false;

    if (!razorpay_key_id) {
      setLoading(false);
      setPaymentStatus('error');
      const reason = 'Razorpay test keys are not configured. No payment was attempted.';
      setErrorMessage(reason);
      logFailure(reason);
      return;
    }

    if (typeof window.Razorpay === 'undefined') {
      setLoading(false);
      setPaymentStatus('error');
      const reason = 'The Razorpay checkout script did not load. Please refresh and try again.';
      setErrorMessage(reason);
      logFailure(reason);
      return;
    }

    const options = {
      key: razorpay_key_id,
      amount: Math.round(calculatedFinalAmount * 100),
      currency: currency || 'INR',
      name: 'Agent Bookworm Bookstore',
      description: `Checkout for ${cartItemList.length} book(s)`,
      image: 'https://cdn-icons-png.flaticon.com/512/891/891462.png',
      order_id: razorpay_order_id,

      handler: async function (response) {
        try {
          const verifyRes = await verifyPayment(
            response.razorpay_order_id,
            response.razorpay_payment_id,
            response.razorpay_signature,
            itemNames
          );

          setPaymentStatus('success');
          if (onPaymentSuccess) {
            onPaymentSuccess(verifyRes);
          }
        } catch (err) {
          console.error('Payment verification failed:', err);
          setPaymentStatus('error');
          const errDetail = err?.response?.data?.detail || 'Razorpay payment verification failed.';
          setErrorMessage(errDetail);
          await logFailure(errDetail);
        } finally {
          setLoading(false);
        }
      },
      prefill: {
        name: 'Razorpay Buyer',
        email: 'buyer@agentbookworm.ai',
        contact: '9999999999'
      },
      theme: {
        color: '#2563eb'
      },
      modal: {
        ondismiss: function () {
          setLoading(false);
          if (paymentStatus !== 'success') {
            logFailure("User cancelled checkout modal");
          }
        }
      }
    };

    try {
      const rzp = new window.Razorpay(options);
      rzp.on('payment.failed', function (response) {
        setPaymentStatus('error');
        const failMsg = response.error?.description || response.error?.reason || 'Payment transaction failed.';
        setErrorMessage(failMsg);
        setLoading(false);
        logFailure(failMsg);
      });
      rzp.open();
    } catch (e) {
      console.error('Razorpay modal open exception:', e);
      setLoading(false);
      setPaymentStatus('error');
      const failMsg = 'Razorpay checkout could not open. No payment was attempted.';
      setErrorMessage(failMsg);
      logFailure(failMsg);
    }
  };

  return (
    <div className="my-3 max-w-md bg-zinc-900 border border-zinc-800 rounded-2xl p-4 shadow-xl text-zinc-100 font-sans">
      {/* Header Badge */}
      <div className="flex items-center justify-between border-b border-zinc-800 pb-3 mb-3">
        <div className="flex items-center space-x-2">
          <div className="w-8 h-8 rounded-lg bg-blue-600/20 text-blue-400 flex items-center justify-center border border-blue-500/30">
            <ShoppingBag className="w-4 h-4" />
          </div>
          <div>
            <h4 className="text-xs font-bold text-white tracking-wide">Razorpay Instant Checkout</h4>
            <span className="text-[10px] text-zinc-500 font-mono">Order ID #{order_id}</span>
          </div>
        </div>

        <div className="flex items-center space-x-1 bg-emerald-950/80 text-emerald-300 border border-emerald-800/60 px-2 py-0.5 rounded-full text-[10px] font-mono font-medium">
          <ShieldCheck className="w-3 h-3 text-emerald-400" />
          <span>Gated &amp; Verified</span>
        </div>
      </div>

      {/* Cart Items Summary */}
      <div className="space-y-2 mb-3 max-h-36 overflow-y-auto pr-1">
        {cartItemList.map((item, idx) => {
          const qty = item.quantity || 1;
          const unitFinal = item.final_price || item.price || 0;
          const lineTotal = unitFinal * qty;

          return (
            <div key={idx} className="flex items-center justify-between text-xs bg-zinc-950 p-2 rounded-xl border border-zinc-800/80">
              <div className="min-w-0 flex-1 pr-2">
                <span className="font-medium text-white truncate block">{item.name}</span>
                <div className="flex items-center space-x-2 text-[10px] text-zinc-500">
                  {item.author && <span className="truncate">{item.author}</span>}
                  {qty > 1 && (
                    <span className="text-zinc-400 font-mono font-medium">Qty: {qty}</span>
                  )}
                </div>
              </div>
              <div className="text-right shrink-0 font-mono">
                <span className="font-semibold text-white">₹{lineTotal.toFixed(2)}</span>
                {qty > 1 && (
                  <span className="text-[10px] text-zinc-500 block font-normal">({qty} × ₹{unitFinal.toFixed(2)})</span>
                )}
                {item.discount_percentage > 0 && (
                  <span className="text-[10px] text-blue-400 block">({item.discount_percentage}% OFF)</span>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Financial Breakdown */}
      <div className="bg-zinc-950/60 rounded-xl p-2.5 border border-zinc-800/60 space-y-1.5 text-xs font-mono mb-4">
        <div className="flex justify-between text-zinc-400">
          <span>Catalog Total:</span>
          <span className="line-through">₹{calculatedOriginalTotal.toFixed(2)}</span>
        </div>

        {calculatedTotalDiscount > 0 && (
          <div className="flex justify-between text-blue-400">
            <span className="flex items-center space-x-1">
              <Tag className="w-3 h-3" />
              <span>Bounded Discount:</span>
            </span>
            <span>-₹{calculatedTotalDiscount.toFixed(2)}</span>
          </div>
        )}

        <div className="border-t border-zinc-800/80 pt-1.5 flex justify-between font-bold text-sm text-white">
          <span>Payable Amount:</span>
          <span className="text-emerald-400">₹{calculatedFinalAmount.toFixed(2)}</span>
        </div>
      </div>

      {/* Payment Action Button */}
      {paymentStatus === 'success' ? (
        <div className="bg-emerald-950/80 border border-emerald-800/80 rounded-xl p-3 text-center space-y-1 text-xs text-emerald-300">
          <div className="flex items-center justify-center space-x-1.5 font-bold">
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            <span>Payment Verified Successfully!</span>
          </div>
          <p className="text-[11px] text-emerald-400/80">
            Razorpay HMAC signature verified &amp; recorded in Merchant Audit Trail.
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {paymentStatus === 'error' && (
            <div className="bg-red-950/80 border border-red-800/80 rounded-xl p-2.5 flex items-start space-x-2 text-xs text-red-300">
              <AlertCircle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
              <div>
                <span className="font-semibold block">Payment Failed</span>
                <span className="text-[11px] text-red-300/80">{errorMessage}</span>
              </div>
            </div>
          )}

          <button
            onClick={handleOpenRazorpay}
            disabled={loading}
            className="w-full py-2.5 bg-blue-600 hover:bg-blue-500 text-white font-semibold text-xs rounded-xl transition-all shadow-lg flex items-center justify-center space-x-2 cursor-pointer disabled:opacity-50"
          >
            <CreditCard className="w-4 h-4" />
            <span>{loading ? 'Processing Razorpay...' : `Pay ₹${calculatedFinalAmount.toFixed(2)} with Razorpay`}</span>
          </button>

          <button
            type="button"
            onClick={handleSimulateFailure}
            disabled={loading}
            className="w-full py-1.5 bg-zinc-950 hover:bg-red-950/40 hover:text-red-300 text-zinc-400 font-medium text-[11px] rounded-lg transition-colors flex items-center justify-center space-x-1.5 border border-zinc-800/80 hover:border-red-900/50 cursor-pointer disabled:opacity-40"
          >
            <XCircle className="w-3.5 h-3.5 text-red-400" />
            <span>Simulate Payment Failure (Test Gating)</span>
          </button>
        </div>
      )}
    </div>
  );
}
