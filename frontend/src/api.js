import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
const API_BASE = API_BASE_URL.endsWith('/api') ? API_BASE_URL : `${API_BASE_URL.replace(/\/$/, '')}/api`;


export const fetchProducts = async () => {
  const res = await axios.get(`${API_BASE}/products`);
  return res.data;
};

export const sendChatMessage = async (message, conversationHistory = [], cart = []) => {
  const formattedCart = (cart || []).map((item) => ({
    ...item,
    quantity: item.quantity || 1,
    price: item.price !== undefined ? item.price : (item.final_price || 0),
    final_price: item.final_price !== undefined ? item.final_price : (item.price || 0)
  }));
  const res = await axios.post(`${API_BASE}/chat`, {
    message,
    conversation_history: conversationHistory,
    cart: formattedCart
  });
  return res.data;
};

export const createOrder = async (productId, discountPercentage = 0, crossSellId = null) => {
  const res = await axios.post(`${API_BASE}/orders/create`, {
    product_id: productId,
    discount_percentage: discountPercentage,
    cross_sell_product_id: crossSellId
  });
  return res.data;
};

export const verifyPayment = async (razorpayOrderId, razorpayPaymentId, razorpaySignature, items = []) => {
  const res = await axios.post(`${API_BASE}/orders/verify`, {
    razorpay_order_id: razorpayOrderId,
    razorpay_payment_id: razorpayPaymentId,
    razorpay_signature: razorpaySignature,
    items: items
  });
  return res.data;
};

export const reportPaymentFailure = async (razorpayOrderId, reason, items = []) => {
  const res = await axios.post(`${API_BASE}/orders/fail`, {
    razorpay_order_id: razorpayOrderId,
    reason,
    items
  });
  return res.data;
};

export const fetchAuditLogs = async () => {
  const res = await axios.get(`${API_BASE}/audit-logs`);
  return res.data;
};

export const clearAuditLogs = async () => {
  const res = await axios.post(`${API_BASE}/audit-logs/clear`);
  return res.data;
};
