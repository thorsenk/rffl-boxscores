#!/bin/bash
# setup.sh - Quick setup script for rffl-boxscores
# Usage: ./setup.sh

set -e

echo "🚀 Setting up rffl-boxscores..."

# Check if Python 3.9+ is available
python_version=$(python3 --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
required_version="3.9"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    echo "❌ Python 3.9+ is required. Found: $python_version"
    exit 1
fi

echo "✅ Python version: $python_version"

# Create virtual environment
echo "📦 Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Upgrade pip
echo "⬆️  Upgrading pip..."
pip install --upgrade pip

# Install the package
echo "🔧 Installing rffl-boxscores..."
pip install -e .

# Run installation test
echo "🧪 Testing installation..."
python test_installation.py

echo ""
echo "🎉 Setup complete!"
echo ""
echo "Next steps:"
echo "1. Activate the virtual environment: source venv/bin/activate"
echo "2. Set up your league ID: echo 'export LEAGUE=YOUR_LEAGUE_ID' >> .env"
echo "3. For private leagues, add ESPN_S2 and SWID to .env"
echo "4. Load vibe mode: source ./vibe.sh"
echo ""
echo "Quick test:"
echo "  rffl-bs --help"
echo "  source ./vibe.sh && bs 2024"
