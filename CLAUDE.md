# Speakly

Text-to-speech mini-player — converts text to speech via multiple TTS providers and plays it in a floating PyQt6 mini-player with full playback controls.

## Tech Stack

- **Language**: Python 3.11+
- **Package manager**: uv
- **CLI framework**: Typer
- **GUI**: PyQt6 (QMediaPlayer + floating window)
- **TTS providers**: OpenAI, ElevenLabs, Inworld
- **Title generation**: Anthropic Claude Haiku

## Commands

```bash
uv run speakly "text to speak"                # Speak text
uv run speakly --provider elevenlabs          # Use specific provider
uv run speakly --voice nova                   # Specify voice
uv run speakly --speed 2.0                    # Set playback speed
uv run speakly --file doc.txt                 # Read from file
uv run speakly                                # Read from clipboard (pbpaste)
uv run speakly --list-voices                  # List voices for a provider
uv sync                                       # Install dependencies
```

## Architecture

**Flow:** Raycast script / CLI → TTS provider API → cached audio file → PyQt6 mini-player

- **File-then-play**: Download full audio to temp file, then play with `QMediaPlayer` for free pause/resume/scrub/speed control
- **Caching**: Audio cached by hash of (text + provider + voice) in `~/.speakly/cache/`, 7-day eviction
- **Title generation**: Haiku LLM call fired in parallel with TTS, title swaps in when ready

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
│   │   └── inworld.py      # Inworld TTS 1.5 (Basic auth, speakingRate)
│   ├── player.py           # PyQt6 floating mini-player (always-on-top, dark theme)
│   ├── titler.py           # Background thread Haiku title generation
│   └── cache.py            # SHA256-based audio file caching
├── pyproject.toml
├── .env                    # API keys (gitignored)
├── .gitignore
└── CLAUDE.md
```

## Player Controls

- Play/pause, rewind/forward 10s
- Scrub bar with time display
- Speed buttons: 1x, 1.5x, 2x, 3x
- Volume slider
- Draggable frameless window (~420x140px)
- Catppuccin Mocha dark theme

## Provider Notes

| Provider | Model | Speed Range | Voice Default |
|----------|-------|-------------|---------------|
| OpenAI | tts-1-hd | 0.25-4.0x | nova |
| ElevenLabs | eleven_multilingual_v2 | 1x only (use player speed) | Rachel |
| Inworld | TTS 1.5 | 0.5-1.5x | en-US-Standard-A |

- OpenAI chunks text at 4096 chars and concatenates MP3s
- ElevenLabs resolves voice names to IDs via API
- Inworld uses Basic auth (JWT key:secret base64-encoded)

## Raycast Integration

`~/raycast-scripts/speakly.sh` — copies selected text and launches Speakly in background. Mode: silent.

## API Keys

Keys stored in 1Password. Populate `.env` before use:
- `OPENAI_API_KEY` — "Brex CFO OpenAI" in Employee vault
- `ELEVEN_API_KEY` — "Elevenlabs API key for local development" in Engineering vault
- `INWORLD_JWT_KEY` / `INWORLD_JWT_SECRET` — "Inworld Local Personal API Key" in Employee vault
- `ANTHROPIC_API_KEY` — for title generation

## Future Ideas

- SwiftUI native macOS rebuild
- Streaming playback (play as audio arrives)
- PDF text extraction → TTS
- Sentence-level highlight sync
