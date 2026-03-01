# Speakly

A floating text-to-speech mini-player for macOS. Highlight text, press a hotkey, and listen with full playback controls.

**Providers:** OpenAI TTS, ElevenLabs, Inworld AI

## How It Works

1. Copy text to clipboard (or pass it as an argument)
2. Run `speakly` (via CLI, shell alias, or Raycast hotkey)
3. A floating mini-player appears instantly with a loading indicator
4. Audio generates in the background, then auto-plays
5. Control playback: pause, scrub, speed up (1x/1.5x/2x/3x), adjust volume

Repeated text is served from cache — instant playback on second listen.

## Quick Start

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- API key for at least one TTS provider (OpenAI, ElevenLabs, or Inworld)
- Optional: [1Password CLI](https://developer.1password.com/docs/cli/) for secret management

### Install

```bash
git clone https://github.com/noncuro/speakly.git
cd speakly
uv sync
```

### Configure API Keys

Create a `.env` file in the project root:

```bash
# Option A: Plain values
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...    # for auto-generated titles

# Option B: 1Password secret references (recommended)
OPENAI_API_KEY=op://VaultName/ItemName/FieldName
ANTHROPIC_API_KEY=op://VaultName/ItemName/FieldName
```

Only the provider you plan to use needs a key. `ANTHROPIC_API_KEY` is optional — it powers the auto-generated title that appears in the player.

### Run

```bash
# With plain .env values
uv run speakly "Hello world, this is a test"

# With 1Password references
op run --env-file=.env -- uv run speakly "Hello world, this is a test"

# Read from clipboard
uv run speakly

# Read from file
uv run speakly --file article.txt
```

## Usage

```
speakly [OPTIONS] [TEXT]

Options:
  -p, --provider  TTS provider: openai, elevenlabs, inworld  [default: inworld]
  -v, --voice     Voice name or ID
  -s, --speed     Playback speed multiplier                   [default: 2.0]
  -f, --file      Read text from a file
  --list-voices   List available voices for the provider
  --help          Show help
```

### Examples

```bash
speakly "The quick brown fox"                    # Default provider + speed
speakly -p openai -v nova "Hello world"          # OpenAI with specific voice
speakly -p elevenlabs -s 1.5 --file doc.txt      # ElevenLabs from file
speakly --list-voices -p openai                   # See available voices
```

## Shell Alias

For convenience, add an alias that handles 1Password injection:

```bash
# In ~/.zshrc or ~/.bashrc
alias speakly='OP_SERVICE_ACCOUNT_TOKEN=$(security find-generic-password -a speakly -s op-service-account-token -w) op run --env-file=$HOME/path/to/speakly/.env -- uv run --project $HOME/path/to/speakly speakly'
```

Then just: `speakly "text to speak"`

## Raycast Integration

A Raycast script is included at [`scripts/speakly-raycast.sh`](scripts/speakly-raycast.sh). To set it up:

1. Copy the script to your Raycast scripts directory:
   ```bash
   cp scripts/speakly-raycast.sh ~/raycast-scripts/speakly.sh
   chmod +x ~/raycast-scripts/speakly.sh
   ```

2. Edit the script to match your setup:
   - Update the `--project` path if you cloned Speakly elsewhere
   - If not using 1Password, replace the `op run` line with a direct `uv run` call and set env vars another way

3. In Raycast, search for "Speakly" and assign a hotkey (Cmd+K > Configure Hotkey)

4. **Usage:** Copy text (Cmd+C), press your hotkey. The player appears instantly.

The Raycast script:
```bash
#!/bin/bash

# @raycast.schemaVersion 1
# @raycast.title Speakly
# @raycast.mode silent
# @raycast.icon 🔊
# @raycast.description Read selected text aloud with TTS mini-player

# Load PATH for Homebrew + uv (Raycast uses minimal environment)
eval "$(/opt/homebrew/bin/brew shellenv)"
export PATH="$HOME/.local/bin:$PATH"

TEXT=$(pbpaste 2>/dev/null)
[ -z "$TEXT" ] && exit 1

# 1Password service account token from macOS keychain
export OP_SERVICE_ACCOUNT_TOKEN=$(security find-generic-password -a speakly -s op-service-account-token -w)

nohup op run --env-file="$HOME/Documents/GitHub/speakly/.env" -- \
  uv run --project "$HOME/Documents/GitHub/speakly" speakly "$TEXT" \
  > /tmp/speakly.log 2>&1 &
```

## Player

The mini-player is a 420x140px floating window with a Catppuccin Mocha dark theme:

- **Transport:** rewind 10s, play/pause, forward 10s
- **Scrub bar** with elapsed/total time
- **Speed buttons:** 1x, 1.5x, 2x, 3x
- **Volume slider**
- **Draggable** — click and drag anywhere on the window
- **Always on top** — stays visible over other windows
- **Auto-title** — Claude Haiku generates a short title from the text

## Providers

| Provider | Model | Native Speed | Default Voice |
|----------|-------|-------------|---------------|
| [OpenAI](https://platform.openai.com/docs/guides/text-to-speech) | tts-1-hd | 0.25-4.0x | nova |
| [ElevenLabs](https://elevenlabs.io/docs) | eleven_multilingual_v2 | 1x (use player) | Rachel |
| [Inworld](https://docs.inworld.ai/docs/tts/tts) | inworld-tts-1.5-max | 1x (use player) | Alex |

Long text is automatically chunked (4096 chars for OpenAI, 2000 for Inworld) and concatenated.

## Caching

Audio is cached in `~/.speakly/cache/` keyed by SHA256 of `(text + provider + voice)`. Cache entries are evicted after 7 days. Running the same text twice skips the API call entirely.

## License

MIT
