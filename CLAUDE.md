# Speakly

Text-to-speech mini-player — converts text to speech via multiple TTS providers and plays it in a floating PyQt6 mini-player with full playback controls.

## Tech Stack

- **Language**: Python 3.11+
- **Package manager**: uv
- **CLI framework**: Typer
- **GUI**: PyQt6 (QMediaPlayer + floating window)
- **TTS providers**: OpenAI, ElevenLabs, Inworld
- **Title generation**: Anthropic Claude Haiku
- **Secrets**: 1Password service account via `op run`

## Commands

```bash
# All commands use op run to inject secrets from 1Password
op run --env-file=.env -- uv run speakly "text to speak"          # Speak text
op run --env-file=.env -- uv run speakly --provider openai        # Use specific provider
op run --env-file=.env -- uv run speakly --voice nova             # Specify voice
op run --env-file=.env -- uv run speakly --speed 1.5              # Set playback speed
op run --env-file=.env -- uv run speakly --file doc.txt           # Read from file
op run --env-file=.env -- uv run speakly                          # Read from clipboard
op run --env-file=.env -- uv run speakly --list-voices            # List voices
uv sync                                                            # Install dependencies
```

Default provider is Inworld at 2x speed.

## Architecture

**Flow:** Raycast hotkey / CLI → player shows instantly (loading state) → TTS in background → auto-play when ready

- **Instant player**: Window appears immediately with loading indicator; TTS runs in background thread
- **File-then-play**: Audio saved to cache file, then played with `QMediaPlayer` for pause/resume/scrub/speed
- **Caching**: Audio cached by SHA256 of (text + provider + voice) in `~/.speakly/cache/`, 7-day eviction
- **Title generation**: Haiku LLM call fired in parallel with TTS, title swaps in when ready
- **Cache hits**: Player opens and plays immediately — no loading state

## Project Structure

```
speakly/
├── src/speakly/
│   ├── __init__.py
│   ├── cli.py              # Typer CLI entrypoint + orchestration
│   ├── providers/
│   │   ├── __init__.py     # TTSProvider protocol + decorator registry
│   │   ├── openai.py       # OpenAI TTS (tts-1-hd, 4096-char chunking)
│   │   ├── elevenlabs.py   # ElevenLabs (eleven_multilingual_v2)
│   │   └── inworld.py      # Inworld TTS 1.5 Max (2000-char chunking)
│   ├── player.py           # PyQt6 floating mini-player (always-on-top, dark theme)
│   ├── titler.py           # Background thread Haiku title generation
│   └── cache.py            # SHA256-based audio file caching
├── pyproject.toml
├── .env                    # 1Password op:// references (gitignored)
├── .gitignore
├── README.md
└── CLAUDE.md
```

## Player Controls

- Play/pause, rewind/forward 10s
- Scrub bar with time display
- Speed buttons: 1x, 1.5x, 2x, 3x
- Volume slider
- Draggable frameless window (~420x140px)
- Catppuccin Mocha dark theme
- Loading state with indeterminate progress bar while TTS generates

## Provider Notes

| Provider | Model | Speed Range | Voice Default |
|----------|-------|-------------|---------------|
| OpenAI | tts-1-hd | 0.25-4.0x | nova |
| ElevenLabs | eleven_multilingual_v2 | 1x only (use player speed) | Rachel |
| Inworld | inworld-tts-1.5-max | player speed only | Alex |

- OpenAI chunks text at 4096 chars and concatenates MP3s
- ElevenLabs resolves voice names to IDs via API
- Inworld chunks at 2000 chars, uses Basic auth (JWT key:secret base64-encoded)

## Raycast Integration

`~/raycast-scripts/speakly.sh` — reads clipboard and launches Speakly in background. Mode: silent. Loads PATH for Homebrew + uv, service account token from macOS keychain.

## API Keys

Secrets are managed via a **1Password service account** — no fingerprint prompts.

- **Vault:** `Speakly` (dedicated vault with copies of the API keys)
- **Service account:** "Speakly Local" — read-only access to the Speakly vault
- **Token storage:** macOS keychain (`security find-generic-password -a speakly -s op-service-account-token -w`)
- **Injection:** `OP_SERVICE_ACCOUNT_TOKEN=... op run --env-file=.env -- speakly "text"`

| Env Var | 1Password Reference |
|---------|-------------------|
| `OPENAI_API_KEY` | `op://Speakly/OpenAI/OPENAI_API_KEY` |
| `ELEVEN_API_KEY` | `op://Speakly/ElevenLabs/ELEVEN_API_KEY` |
| `INWORLD_JWT_KEY` | `op://Speakly/Inworld/INWORLD_JWT_KEY` |
| `INWORLD_JWT_SECRET` | `op://Speakly/Inworld/INWORLD_JWT_SECRET` |
| `ANTHROPIC_API_KEY` | `op://Speakly/Anthropic/ANTHROPIC_API_KEY` |
