#!/usr/bin/env bash
set -euo pipefail

cat <<'MSG'
This repairs WSL DNS resolution for ShelbyTrain uploads.

It disables auto-generated resolv.conf and installs public DNS resolvers.
You may need to run this from your own terminal with sudo access.
MSG

sudo tee /etc/wsl.conf >/dev/null <<'EOF'
[network]
generateResolvConf = false
EOF

sudo rm -f /etc/resolv.conf
sudo tee /etc/resolv.conf >/dev/null <<'EOF'
nameserver 1.1.1.1
nameserver 8.8.8.8
EOF

echo "DNS file written:"
cat /etc/resolv.conf

echo
echo "Testing DNS:"
getent hosts api.shelbynet.shelby.xyz
getent hosts aptos.dev

cat <<'MSG'

If DNS still fails, close this WSL terminal, run this in Windows PowerShell:

  wsl --shutdown

Then reopen WSL and restart ShelbyTrain.
MSG
