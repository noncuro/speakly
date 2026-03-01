#!/bin/bash

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Speakly
# @raycast.mode silent

# Optional parameters:
# @raycast.packageName Speakly
# @raycast.icon 🔊
# @raycast.description Read selected text aloud with TTS mini-player
# @raycast.author Daniel

# Load full PATH (Raycast uses minimal environment)
eval "$(/opt/homebrew/bin/brew shellenv)"
export PATH="$HOME/.local/bin:$PATH"

# Grab clipboard (text should already be selected/copied)
TEXT=$(pbpaste 2>/dev/null)

if [ -z "$TEXT" ]; then
    echo "No text in clipboard"
    exit 1
fi

# Load service account token from keychain (no fingerprint prompt)
export OP_SERVICE_ACCOUNT_TOKEN=$(security find-generic-password -a speakly -s op-service-account-token -w)

# Launch speakly in background (op run injects secrets from 1Password)
nohup op run --env-file="$HOME/Documents/GitHub/speakly/.env" -- uv run --project "$HOME/Documents/GitHub/speakly" speakly "$TEXT" > /tmp/speakly.log 2>&1 &
