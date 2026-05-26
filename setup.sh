#!/bin/bash
# OMEN Hub privilege setup helper
# Run this once after installation to enable GPU switching and fan control

set -e

echo "=== OMEN Hub Setup ==="
echo ""

# Check if running as non-root
if [ "$EUID" -eq 0 ]; then
  echo "❌ Don't run this as root!"
  exit 1
fi

# Check dependencies
echo "Checking dependencies..."

if ! command -v supergfxctl &> /dev/null; then
  echo "❌ supergfxctl not found. Install with:"
  echo "   sudo pacman -S supergfxctl"
  exit 1
fi

if ! command -v pkexec &> /dev/null; then
  echo "⚠️  pkexec not found. GPU switching will use sudo instead."
  NEED_POLKIT=1
fi

echo "✓ supergfxctl found"

# Test current setup
echo ""
echo "Testing current GPU mode access..."

if sudo -n supergfxctl -g &> /dev/null; then
  echo "✓ sudo NOPASSWD already configured for supergfxctl"
  SUDO_OK=1
elif pkexec supergfxctl -g &> /dev/null; then
  echo "✓ PolicyKit already configured"
  POLKIT_OK=1
else
  echo "⚠️  GPU switching not configured yet"
  SETUP_NEEDED=1
fi

# Offer setup if needed
if [ "$SETUP_NEEDED" = "1" ]; then
  echo ""
  echo "GPU switching setup options:"
  echo "1) Set up sudo NOPASSWD rule (simple, works everywhere)"
  echo "2) Install PolicyKit auth agent (more proper, needs setup)"
  echo "3) Install omenctl daemon (best, handles fans too)"
  echo ""
  read -p "Choose 1-3 (or press Enter to skip): " choice

  case $choice in
    1)
      echo "Setting up sudo NOPASSWD for supergfxctl..."
      echo "%wheel ALL=(ALL) NOPASSWD: /usr/bin/supergfxctl" | sudo tee -a /etc/sudoers.d/omen-hub > /dev/null
      echo "✓ Configured. GPU switching should work now."
      ;;
    2)
      echo "Installing polkit-qt5..."
      sudo pacman -S --noconfirm polkit-qt5
      echo "⚠️  Add this to your WM config (~/.config/niri/config.kdl or similar):"
      echo "   exec polkit-kde-agent-1"
      ;;
    3)
      echo "Installing omenctl-git..."
      sudo pacman -S --noconfirm omenctl-git
      sudo systemctl enable --now omenctl
      echo "✓ omenctl daemon installed and started"
      ;;
  esac
fi

# Check for fan controller
echo ""
echo "Checking fan control..."
if systemctl is-active --quiet omenctl; then
  echo "✓ omenctl daemon running (fan control available)"
elif command -v omenctl-fand &> /dev/null; then
  echo "⚠️  omenctl installed but not running"
  read -p "Start omenctl now? (y/n) " -n 1 -r
  echo
  if [[ $REPLY =~ ^[Yy]$ ]]; then
    sudo systemctl enable --now omenctl
    echo "✓ omenctl daemon started"
  fi
else
  echo "ℹ️  omenctl not installed (optional, for fan control)"
  echo "   Install with: sudo pacman -S omenctl-git"
fi

# Final check
echo ""
echo "=== Testing GPU switching ==="
if sudo -n supergfxctl -g &> /dev/null; then
  mode=$(sudo -n supergfxctl -g)
  echo "✓ GPU switching ready (current mode: $mode)"
elif pkexec supergfxctl -g &> /dev/null; then
  mode=$(pkexec supergfxctl -g)
  echo "✓ GPU switching ready (current mode: $mode)"
else
  echo "⚠️  GPU switching not working yet. See README for manual setup."
fi

echo ""
echo "=== Setup complete ==="
echo "Launch OMEN Hub with: omen-hub"
