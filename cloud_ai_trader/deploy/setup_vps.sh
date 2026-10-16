#!/bin/bash
# Cloud AI Trader - VPS Setup Script
# Run on a fresh Ubuntu 22.04+ VPS

set -e
echo '=== Cloud AI Trader VPS Setup ==='

# Update system
sudo apt update && sudo apt upgrade -y

# Install Python 3.11
sudo apt install -y python3.11 python3.11-venv python3-pip

# Install Docker (optional)
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER

# Setup project
cd /opt
sudo mkdir -p cloud_ai_trader
sudo chown $USER:$USER cloud_ai_trader
cd cloud_ai_trader

# Create virtual environment
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip

# Clone or copy project files here, then:
# pip install -r requirements.txt
# cp .env.example .env
# Edit .env with your Gemini API key and bridge token

echo '=== Setup complete ==='
echo 'Next steps:'
echo '1. Copy project files to /opt/cloud_ai_trader/'
echo '2. pip install -r requirements.txt'
echo '3. cp .env.example .env && nano .env'
echo '4. python main.py'
