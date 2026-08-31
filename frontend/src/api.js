import axios from 'axios';

const API_BASE = '/api';

export const fetchProducts = async () => {
  const res = await axios.get(`${API_BASE}/products`);
  return res.data;
};

export const sendChatMessage = async (message, conversationHistory = [], cart = []) => {
  const res = await axios.post(`${API_BASE}/chat`, {
    message,
    conversation_history: conversationHistory,
    cart: cart
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

export const verifyPayment = async (razorpayOrderId, razorpayPaymentId, razorpaySignature) => {
  const res = await axios.post(`${API_BASE}/orders/verify`, {
    razorpay_order_id: razorpayOrderId,
    razorpay_payment_id: razorpayPaymentId,
    razorpay_signature: razorpaySignature
  });
  return res.data;
};

export const fetchAuditLogs = async () => {
  const res = await axios.get(`${API_BASE}/audit-logs`);
  return res.data;
};
