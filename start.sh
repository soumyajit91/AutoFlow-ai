#!/usr/bin/env bash
# start.sh
# Render startup script to initialize Ollama natively and boot Streamlit

export OLLAMA_HOST="0.0.0.0"

echo "Checking for Ollama installation..."
if ! command -v ollama &> /dev/null; then
    echo "Ollama not found. Installing natively..."
    curl -fsSL https://ollama.com/install.sh | sh
fi

echo "Ollama starting..."
ollama serve &

# Wait for Ollama daemon to initialize
sleep 5

echo "Pulling lightweight fallback model..."
# Use tinyllama to ensure memory stays < 512MB on Render Free
ollama pull tinyllama
echo "Model loaded successfully."

echo "Starting Autonomous Workflow System..."
# Boot the main application
streamlit run app.py --server.port $PORT --server.address 0.0.0.0
