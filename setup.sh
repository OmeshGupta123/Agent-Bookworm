#!/bin/bash
set -e

echo "==================================================="
echo "  Starting Agent Bookworm Setup (Razorpay Buildathon)"
echo "==================================================="

echo "[1/4] Installing Python backend requirements..."
python -m pip install -r backend/requirements.txt

echo ""
echo "[2/4] Installing React frontend node modules..."
cd frontend
npm install
cd ..

echo ""
echo "[3/4] Initializing Database tables & Seeding Clothing Catalog..."
cd backend
python -c "from app.main import app, engine, Base, SessionLocal; from app.api.products import seed_products; db = SessionLocal(); seed_products(db); db.close(); print('Database tables initialized and clothing catalog seeded successfully!')"
cd ..

echo ""
echo "==================================================="
echo "  Starting Backend (Port 8000) & Frontend (Port 5173)"
echo "==================================================="
echo "FastAPI API:  http://127.0.0.1:8000"
echo "React App:    http://localhost:5173"
echo "==================================================="

# Start backend in background
(cd backend && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload) &
BACKEND_PID=$!

# Start frontend in background
(cd frontend && npx vite --host 127.0.0.1 --port 5173) &
FRONTEND_PID=$!

trap "kill $BACKEND_PID $FRONTEND_PID" EXIT

wait
