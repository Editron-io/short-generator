import os, shutil
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent
WORK = ROOT / "work"
CACHE = WORK / "cache"
CLIPS = WORK / "clips"
AUDIO = WORK / "audio"
OUT = WORK / "out"
for d in (WORK, CACHE, CLIPS, AUDIO, OUT):
    d.mkdir(parents=True, exist_ok=True)

# ---- Content constraints -------------------------------------------------
TARGET_DURATION_SEC = int(os.getenv("TARGET_DURATION_SEC", "600"))   # 10 min
CLIP_SECONDS = 5.0
CHAPTER_SIZE = 20                                                    # segments per LLM call
NUM_CHAPTERS = max(1, round(TARGET_DURATION_SEC / (CLIP_SECONDS * CHAPTER_SIZE)))
MIN_WORDS, MAX_WORDS = 8, 20                                         # ~4-6s read

RESOLUTION = (1280, 720)
FPS = 30

# ---- Model fallback chain ------------------------------------------------
GEMINI_MODEL_CHAIN = [
    m.strip() for m in os.getenv(
        "GEMINI_MODEL_CHAIN",
        "gemini-2.5-flash,gemini-2.5-flash-lite,gemini-2.0-flash",
    ).split(",") if m.strip()
]

# ---- TTS -----------------------------------------------------------------
EDGE_VOICE = os.getenv("EDGE_VOICE", "en-US-ChristopherNeural")

# ---- Keys ----------------------------------------------------------------
GEMINI_API_KEY          = os.getenv("GEMINI_API_KEY", "")
PEXELS_API_KEY          = os.getenv("PEXELS_API_KEY", "")
PIXABAY_API_KEY         = os.getenv("PIXABAY_API_KEY", "")
YOUTUBE_CREDENTIALS_B64 = os.getenv("YOUTUBE_CREDENTIALS_B64", "")

# ---- Binaries ------------------------------------------------------------
def ffmpeg_bin() -> str:
    p = shutil.which("ffmpeg")
    if not p:
        raise RuntimeError("ffmpeg not on PATH")
    return p

def ffprobe_bin() -> str:
    p = shutil.which("ffprobe")
    if not p:
        raise RuntimeError("ffprobe not on PATH")
    return p
