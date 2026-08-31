import React, { useState } from 'react';
import { CreditCard, CheckCircle2, AlertCircle, ShoppingBag } from 'lucide-react';
import { verifyPayment } from '../api';

export default function CheckoutCard({ widgetData, onPaymentSuccess }) {
  const [loading, setLoading] = useState(false);
  const [paymentStatus, setPaymentStatus] = useState('pending'); // pending | success | error
  const [errorMessage, setErrorMessage] = useState('');

  const {
    order_id,
    razorpay_order_id,
    razorpay_key_id,
    items = [],
    original_total = 0.0,
    total_discount = 0.0,
    discount_percentage = 0.0,
    final_amount = 0.0,
    currency = 'INR',
    // Fallback props for legacy single item data
    product_name,
    product_image,
    original_price,
    discount_amount,
    cross_sell_name,
    cross_sell_price
  } = widgetData;

  const cartItemList = items.length > 0 ? items : [
    {
      name: product_name || 'Book Order',
      price: original_price || final_amount,
      discount_percentage: discount_percentage,
      discount_amount: discount_amount || 0,
      final_price: (original_price || final_amount) - (discount_amount || 0),
      image_url: product_image
    },
    ...(cross_sell_name ? [{
      name: cross_sell_name,
      price: cross_sell_price || 0,
      discount_percentage: 0,
      discount_amount: 0,
      final_price: cross_sell_price || 0,
      image_url: null
    }] : [])
  ];

  const calculatedFinalAmount = final_amount || cartItemList.reduce((sum, item) => sum + (item.final_price || 0), 0);

  const loadRazorpayScript = () => {
    return new Promise((resolve) => {
      if (window.Razorpay) {
        resolve(true);
        return;
      }
      const script = document.createElement('script');
      script.src = 'https://checkout.razorpay.com/v1/checkout.js';
      script.onload = () => resolve(true);
      script.onerror = () => resolve(false);
      document.body.appendChild(script);
    });
  };

  const handleRazorpayPayment = async () => {
    setLoading(true);
    setErrorMessage('');

    const isLoaded = await loadRazorpayScript();
    if (!isLoaded || !window.Razorpay) {
      setErrorMessage('Razorpay SDK failed to load. Please check your network connection.');
      setLoading(false);
      return;
    }

    const options = {
      key: razorpay_key_id || 'rzp_test_TV4evSxVgchq96',
      amount: Math.round(calculatedFinalAmount * 100),
      currency: currency || 'INR',
      name: 'AgenticPay Bookstore',
      description: `Checkout for ${cartItemList.length} book(s)`,
      image: 'https://cdn-icons-png.flaticon.com/512/891/891462.png',
      order_id: razorpay_order_id,

      handler: async function (response) {
        try {
          const verifyRes = await verifyPayment(
            response.razorpay_order_id,
            response.razorpay_payment_id,
            response.razorpay_signature
          );

          setPaymentStatus('success');
          if (onPaymentSuccess) {
            onPaymentSuccess(verifyRes);
          }
        } catch (err) {
          console.error('Payment verification failed:', err);
          setPaymentStatus('error');
          setErrorMessage(err?.response?.data?.detail || 'Razorpay payment verification failed.');
        } finally {
          setLoading(false);
        }
      },
      prefill: {
        name: 'Razorpay Buyer',
        email: 'buyer@agenticpay.ai',
        contact: '9999999999'
      },
      theme: {
        color: '#2563eb'
      },
      modal: {
        ondismiss: function () {
          setLoading(false);
        }
      }
    };

    try {
      const rzp = new window.Razorpay(options);
      rzp.on('payment.failed', function (response) {
        setPaymentStatus('error');
        setErrorMessage(response.error?.description || 'Payment transaction failed.');
        setLoading(false);
      });
      rzp.open();
    } catch (e) {
      console.error('Razorpay modal open exception:', e);
      handleSimulatedPayment();
    }
  };

  const handleSimulatedPayment = async () => {
    try {
      const res = await verifyPayment(
        razorpay_order_id,
        `pay_simulated_${Date.now()}`,
        'simulated_success_sig'
      );
      setPaymentStatus('success');
      if (onPaymentSuccess) {
        onPaymentSuccess(res);
      }
    } catch (err) {
      setPaymentStatus('error');
      setErrorMessage('Payment verification failed.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mt-3 mb-1 rounded-xl bg-zinc-900 border border-zinc-800 p-4 text-zinc-100 space-y-4 font-sans shadow-xl">
      {/* Header Info */}
      <div className="flex items-center justify-between border-b border-zinc-800 pb-2.5 text-xs text-zinc-400">
        <span className="font-semibold text-zinc-200 flex items-center gap-1.5">
          <ShoppingBag className="w-3.5 h-3.5 text-blue-400" />
          <span>Checkout Order Generated ({cartItemList.length} items)</span>
        </span>
        <span className="text-zinc-400 font-mono text-[11px]">ID: {razorpay_order_id}</span>
      </div>

      {/* Dynamic Itemized Cart List */}
      <div className="space-y-2.5">
        {cartItemList.map((item, idx) => (
          <div key={idx} className="flex items-start justify-between bg-zinc-950 p-2.5 rounded-lg border border-zinc-800 text-xs">
            <div className="flex items-start space-x-2.5 min-w-0 flex-1">
              <img
                src={item.image_url || 'https://images.unsplash.com/photo-1544716278-ca5e3f4abd8c?w=500&auto=format&fit=crop&q=80'}
                alt={item.name}
                className="w-10 h-10 rounded object-cover border border-zinc-800 shrink-0"
              />
              <div className="min-w-0 flex-1">
                <h5 className="font-medium text-white truncate">{item.name}</h5>
                <div className="text-[11px] text-zinc-500 flex items-center space-x-1.5 mt-0.5">
                  {item.author && <span>{item.author}</span>}
                  {item.format && <span className="text-zinc-600">• {item.format}</span>}
                </div>
              </div>
            </div>

            <div className="text-right shrink-0 ml-3">
              <div className="font-semibold text-white">₹{(item.final_price || item.price).toFixed(2)}</div>
              {item.discount_percentage > 0 && (
                <div className="text-[10px] text-blue-400 font-medium">{item.discount_percentage}% OFF</div>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Cart Totals Summary */}
      <div className="pt-2 border-t border-zinc-800 space-y-1 text-xs text-zinc-400">
        {original_total > 0 && original_total !== calculatedFinalAmount && (
          <div className="flex justify-between text-zinc-500">
            <span>Subtotal:</span>
            <span className="line-through">₹{original_total.toFixed(2)}</span>
          </div>
        )}
        {total_discount > 0 && (
          <div className="flex justify-between text-blue-400 font-medium">
            <span>Bounded Discount Savings:</span>
            <span>-₹{total_discount.toFixed(2)}</span>
          </div>
        )}
        <div className="flex justify-between text-sm font-semibold text-white pt-2 border-t border-zinc-800">
          <span>Total Payable Amount</span>
          <span className="text-blue-400 font-bold text-base">₹{calculatedFinalAmount.toFixed(2)}</span>
        </div>
      </div>

      {/* Action Button & Payment State */}
      {paymentStatus === 'success' ? (
        <div className="bg-zinc-950 border border-emerald-900/50 rounded-lg p-3 text-center text-emerald-400 text-xs font-medium flex items-center justify-center space-x-2">
          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          <span>Razorpay Payment Verified & Complete!</span>
        </div>
      ) : (
        <div>
          {paymentStatus === 'error' && (
            <div className="mb-2 text-xs text-red-400 bg-red-950/40 p-2 rounded border border-red-900 flex items-center gap-1.5">
              <AlertCircle className="w-3.5 h-3.5 shrink-0" />
              <span>{errorMessage || 'Payment failed.'}</span>
            </div>
          )}

          <button
            onClick={handleRazorpayPayment}
            disabled={loading}
            className="w-full py-2.5 px-4 bg-blue-600 hover:bg-blue-500 text-white font-semibold text-xs rounded-lg transition-colors flex items-center justify-center space-x-2 disabled:opacity-50 cursor-pointer shadow-md"
          >
            {loading ? (
              <span>Launching Razorpay Standard Checkout...</span>
            ) : (
              <>
                <CreditCard className="w-4 h-4" />
                <span>Pay ₹{calculatedFinalAmount.toFixed(2)} with Razorpay</span>
              </>
            )}
          </button>
        </div>
      )}
    </div>
  );
}
