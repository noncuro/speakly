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

# Launch speakly in background (API keys loaded from keychain via keyring)
nohup uv run --project "$HOME/Documents/GitHub/speakly" speakly "$TEXT" > /tmp/speakly.log 2>&1 &
