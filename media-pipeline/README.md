# Analog Horror Media Pipeline

Long-form (5-15 min) speculative-fiction audio-documentaries with an analog
horror / classified-archive aesthetic. Fully automated: storyboard → narration
→ asset harvesting → compositing → YouTube upload.

## Pipeline

    brain.py → audio.py → asset_manager.py → composer.py → uploader.py

Each stage is resumable via `work/state.json`. Re-run `python main.py` and
completed stages are skipped.

## Quick start

    python -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    cp .env.example .env    # fill in the keys
    python main.py --dry-run

The final video lands in `work/out/final.mp4`.

## Requirements

- Python 3.10+
- FFmpeg 4.3+ on `PATH` (`ffmpeg` and `ffprobe`)
- `GEMINI_API_KEY` — storyboard generation
- `PEXELS_API_KEY` and/or `PIXABAY_API_KEY` — stock fallback
- `YOUTUBE_CREDENTIALS_B64` — base64-encoded OAuth token JSON (for upload)

## Configuration

All tunables live in `config.py` and can be overridden via `.env`:

- `TARGET_DURATION_SEC` (default 600) — total runtime
- `EDGE_VOICE` (default `en-US-ChristopherNeural`)
- `GEMINI_MODEL_CHAIN` — comma-separated fallback chain

## Output constraints

- 1280×720 @ 30 fps, H.264 + AAC, `+faststart`
- Each segment is 4-6 seconds of narration
- Visual clip is trimmed to the exact audio duration per segment
- Analog-horror filter is baked in during clip slicing (not at final mux)

## License

Personal use. Verify asset licenses (Pexels/Pixabay/IA) for your jurisdiction
before publishing monetized content.
