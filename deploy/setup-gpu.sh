#!/bin/bash
# Run this on your rented GPU machine. Does everything automatically.
# Usage: curl -sSL https://raw.githubusercontent.com/FishEnjoyer2025/ollama-team/main/deploy/setup-gpu.sh | bash

set -e
echo "=== Ollama Team GPU Setup ==="

# --- Install Ollama ---
echo "[1/6] Installing Ollama..."
curl -fsSL https://ollama.com/install.sh | sh
ollama serve &
sleep 5

# --- Pull models (70B for coding, 7B as fallback) ---
echo "[2/6] Pulling models (this takes ~5 min on fast internet)..."
ollama pull qwen2.5-coder:32b &
ollama pull qwen2.5:32b &
wait
echo "Models ready."

# --- Install Python + Node ---
echo "[3/6] Installing dependencies..."
apt-get update -qq && apt-get install -y -qq python3 python3-pip python3-venv nodejs npm git > /dev/null 2>&1

# --- Clone the repo ---
echo "[4/6] Cloning repo..."
cd /root
git clone https://github.com/FishEnjoyer2025/ollama-team.git
cd ollama-team

# --- Install Python deps ---
echo "[5/6] Installing Python packages..."
pip install -r requirements.txt pytest > /dev/null 2>&1

# --- Install frontend deps + build ---
echo "[6/6] Building frontend..."
cd frontend
npm install --silent
npm run build
cd ..

# --- Update models in code for GPU ---
echo "Configuring for GPU models..."
# Use 32B models instead of 7B, bump context to 16K, use all GPU threads
python3 -c "
import pathlib

# Update ollama_service.py — bigger context, higher quality
svc = pathlib.Path('backend/services/ollama_service.py')
txt = svc.read_text()
txt = txt.replace('\"num_ctx\": 4096', '\"num_ctx\": 16384')
txt = txt.replace('\"num_thread\": 8', '\"num_gpu\": 99')  # Use all GPU layers
txt = txt.replace('\"temperature\": 0.3', '\"temperature\": 0.2')
svc.write_text(txt)

# Update agent models
for name, model in [
    ('planner', 'qwen2.5:32b'),
    ('coder', 'qwen2.5-coder:32b'),
    ('reviewer', 'qwen2.5-coder:32b'),
]:
    path = pathlib.Path(f'backend/agents/{name}.py')
    txt = path.read_text()
    for old in ['qwen2.5-coder:7b', 'qwen2.5:7b', 'qwen2.5-coder:3b']:
        txt = txt.replace(old, model)
    path.write_text(txt)

# Faster cooldown — GPU can handle rapid cycles
db = pathlib.Path('backend/db.py')
txt = db.read_text()
txt = txt.replace('\"cycle_cooldown_seconds\": \"60\"', '\"cycle_cooldown_seconds\": \"15\"')
db.write_text(txt)

print('Config updated for GPU')
"

# --- Configure git for the agents ---
git config user.email "ollama-team@bot.local"
git config user.name "Ollama Team Bot"

# --- Init the database ---
python3 -c "
import asyncio
from backend import db
async def seed():
    await db.init_db()
    for i, (d, n) in enumerate([
        ('Improve prompts', 'Better output'),
        ('Add tests', 'Prevent regressions'),
        ('Improve git_service', 'Graceful failures'),
        ('Add tools helpers', 'More validation'),
        ('Improve reviewer prompt', 'Better reviews'),
    ], 1):
        cid = f'bootstrap-{i}'
        await db.create_cycle(cid, {'description': d, 'files': [], 'expected_outcome': 'improvement', 'risk': 'low'})
        await db.complete_cycle(cid, 'success')
        await db.add_feedback(cid, 'up', n)
    print('Database seeded')
asyncio.run(seed())
"

echo ""
echo "=== READY ==="
echo ""
echo "To start:"
echo "  cd /root/ollama-team"
echo "  uvicorn backend.main:app --host 0.0.0.0 --port 8000 &"
echo "  npx serve frontend/dist -l 5173 &"
echo ""
echo "Then open http://<YOUR_IP>:5173 in your browser"
echo "API at http://<YOUR_IP>:8000"
echo ""
echo "Models: qwen2.5-coder:32b (coding), qwen2.5:32b (planning)"
echo "Context: 16K tokens | Cooldown: 15s between cycles"
