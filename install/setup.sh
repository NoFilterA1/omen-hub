#!/usr/bin/env bash
# OMEN Hub setup script.
# Idempotent: safe to run multiple times — checks before acting.
# Supports: Arch (pacman), Debian/Ubuntu (apt), Fedora (dnf).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SERVICE_NAME="omen-hub-daemon"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "${GREEN}  [OK]${NC}  $*"; }
warn() { echo -e "${YELLOW}  [??]${NC}  $*"; }
fail() { echo -e "${RED}  [!!]${NC}  $*"; }
step() { echo -e "\n${YELLOW}==> $*${NC}"; }

require_root() {
    if [[ $EUID -ne 0 ]]; then
        fail "Run as root: sudo $0"
        exit 1
    fi
}

# ---------------------------------------------------------------------------
# 1. Detect package manager
# ---------------------------------------------------------------------------
detect_pm() {
    if command -v pacman &>/dev/null; then echo "pacman"
    elif command -v apt &>/dev/null;   then echo "apt"
    elif command -v dnf &>/dev/null;   then echo "dnf"
    else echo "unknown"; fi
}

install_pkg() {
    local pm="$1"; shift
    case "$pm" in
        pacman) pacman -S --noconfirm --needed "$@" ;;
        apt)    apt-get install -y "$@" ;;
        dnf)    dnf install -y "$@" ;;
        *)      warn "Unknown package manager. Install manually: $*"; return 1 ;;
    esac
}

# ---------------------------------------------------------------------------
# 2. Check kernel module
# ---------------------------------------------------------------------------
check_module() {
    step "Checking kernel module (hp-omen-wmi-dkms)"
    if lsmod | grep -q "hp_wmi"; then
        ok "hp_wmi loaded"
    else
        warn "hp_wmi not loaded — trying to load"
        if modprobe hp-wmi 2>/dev/null; then
            ok "hp_wmi loaded"
        else
            fail "Could not load hp_wmi. Install hp-omen-wmi-dkms and reboot."
            fail "Arch: yay -S hp-omen-wmi-dkms"
            exit 1
        fi
    fi

    if [[ -d /sys/devices/platform/hp-wmi/rgb_zones ]]; then
        ok "RGB zones available"
    else
        warn "RGB zones not found — may need reboot after module install"
    fi
}

# ---------------------------------------------------------------------------
# 3. Python dependencies
# ---------------------------------------------------------------------------
check_python_deps() {
    step "Checking Python dependencies"
    local pm="$1"

    if ! command -v python3 &>/dev/null; then
        fail "python3 not found"
        install_pkg "$pm" python3
    else
        ok "python3 found"
    fi

    local missing=()
    python3 -c "import PyQt6" 2>/dev/null || missing+=("python3-pyqt6 PyQt6")
    python3 -c "import tomlkit" 2>/dev/null || missing+=("python-tomlkit")

    if [[ ${#missing[@]} -gt 0 ]]; then
        warn "Installing missing Python packages: ${missing[*]}"
        case "$pm" in
            pacman) pacman -S --noconfirm --needed python-pyqt6 python-tomlkit ;;
            apt)    apt-get install -y python3-pyqt6 python3-tomlkit ;;
            dnf)    dnf install -y python3-PyQt6 python3-tomlkit ;;
            *)      pip3 install PyQt6 tomlkit ;;
        esac
    else
        ok "PyQt6 and tomlkit available"
    fi
}

# ---------------------------------------------------------------------------
# 4. EC access (debugfs)
# ---------------------------------------------------------------------------
check_ec_access() {
    step "Checking EC access (debugfs)"
    if [[ -f /sys/kernel/debug/ec/ec0/io ]]; then
        ok "EC accessible at /sys/kernel/debug/ec/ec0/io"
    else
        warn "debugfs not mounted — mounting"
        mount -t debugfs none /sys/kernel/debug 2>/dev/null || true
        if [[ -f /sys/kernel/debug/ec/ec0/io ]]; then
            ok "EC accessible (mounted debugfs)"
            # Make persistent
            if ! grep -q "debugfs" /etc/fstab; then
                echo "none /sys/kernel/debug debugfs defaults 0 0" >> /etc/fstab
                ok "Added debugfs to /etc/fstab"
            fi
        else
            fail "EC not accessible. Is hp_wmi loaded? Try rebooting."
            exit 1
        fi
    fi
}

# ---------------------------------------------------------------------------
# 5. Create 'omen' group and add current user
# ---------------------------------------------------------------------------
setup_group() {
    step "Setting up 'omen' group for RGB access"
    if ! getent group omen &>/dev/null; then
        groupadd omen
        ok "Created group 'omen'"
    else
        ok "Group 'omen' exists"
    fi

    # Add the user who ran sudo (not root)
    local real_user="${SUDO_USER:-}"
    if [[ -n "$real_user" ]]; then
        if id -nG "$real_user" | grep -qw omen; then
            ok "$real_user already in 'omen' group"
        else
            usermod -aG omen "$real_user"
            ok "Added $real_user to 'omen' group (re-login required)"
        fi
    fi
}

# ---------------------------------------------------------------------------
# 6. udev rules
# ---------------------------------------------------------------------------
setup_udev() {
    step "Installing udev rules"
    local src="$SCRIPT_DIR/99-omen-rgb.rules"
    local dst="/etc/udev/rules.d/99-omen-rgb.rules"

    if [[ -f "$dst" ]] && diff -q "$src" "$dst" &>/dev/null; then
        ok "udev rules already up to date"
    else
        cp "$src" "$dst"
        udevadm control --reload-rules
        udevadm trigger --subsystem-match=platform
        ok "udev rules installed and reloaded"
    fi
}

# ---------------------------------------------------------------------------
# 7. systemd service
# ---------------------------------------------------------------------------
setup_service() {
    step "Installing systemd service"
    local src="$SCRIPT_DIR/omen-hub-daemon.service"
    local dst="/etc/systemd/system/${SERVICE_NAME}.service"

    # Substitute real install path
    sed "s|INSTALL_PATH|${PROJECT_DIR}|g" "$src" > "$dst"

    systemctl daemon-reload

    if systemctl is-enabled --quiet "$SERVICE_NAME" 2>/dev/null; then
        ok "Service already enabled"
    else
        systemctl enable "$SERVICE_NAME"
        ok "Service enabled"
    fi

    if systemctl is-active --quiet "$SERVICE_NAME" 2>/dev/null; then
        systemctl restart "$SERVICE_NAME"
        ok "Service restarted"
    else
        systemctl start "$SERVICE_NAME"
        ok "Service started"
    fi
}

# ---------------------------------------------------------------------------
# 8. omenctl symlink
# ---------------------------------------------------------------------------
setup_cli() {
    step "Setting up omenctl CLI"
    local target="/usr/local/bin/omenctl"
    local src="$PROJECT_DIR/omenctl.py"

    chmod +x "$src"
    if [[ -L "$target" ]] && [[ "$(readlink "$target")" == "$src" ]]; then
        ok "omenctl symlink already correct"
    else
        ln -sf "$src" "$target"
        ok "omenctl available at $target"
    fi
}

# ---------------------------------------------------------------------------
# 9. GUI launcher + mode scripts
# ---------------------------------------------------------------------------
setup_gui() {
    step "Setting up GUI launcher and mode scripts"

    # Make mode scripts executable
    chmod +x "$PROJECT_DIR/scripts/"*.sh

    # Create /usr/local/bin/omen-hub launcher
    local gui_launcher="/usr/local/bin/omen-hub"
    cat > "$gui_launcher" << EOF
#!/bin/bash
# OMEN Hub GUI launcher — single-instance via lock file
if pgrep -f "omen-hub/gui/app.py" > /dev/null 2>&1; then
    exit 0
fi
exec python3 "$PROJECT_DIR/gui/app.py" "\$@"
EOF
    chmod +x "$gui_launcher"
    ok "GUI launcher: omen-hub"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    echo ""
    echo "  OMEN Hub Setup"
    echo "  =============="

    require_root
    local pm; pm="$(detect_pm)"
    ok "Package manager: $pm"

    check_module
    check_python_deps "$pm"
    check_ec_access
    setup_group
    setup_udev
    setup_service
    setup_cli
    setup_gui

    echo ""
    ok "Setup complete!"
    echo ""
    echo "  CLI:  omenctl status"
    echo "  CLI:  omenctl mode silent | balanced | performance"
    echo "  GUI:  omen-hub"
    echo ""
    echo "  Mode scripts for keybinds:"
    echo "    $PROJECT_DIR/scripts/fmin.sh  (silent)"
    echo "    $PROJECT_DIR/scripts/fbal.sh  (balanced)"
    echo "    $PROJECT_DIR/scripts/fmax.sh  (performance)"
    echo ""
    warn "If you were just added to the 'omen' group, log out and back in for RGB access."
}

main "$@"
