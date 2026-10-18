"""Module 2 — Narration synthesis + per-segment timeline."""
import asyncio, json, logging, subprocess
from pathlib import Path
import edge_tts
import config

log = logging.getLogger(__name__)


def _probe(path: Path) -> float:
    out = subprocess.run(
        [config.ffprobe_bin(), "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return float(out)


class AudioEngine:
    def __init__(self, voice: str = config.EDGE_VOICE):
        self.voice = voice

    async def _synth(self, text: str, out: Path) -> None:
        await edge_tts.Communicate(text, self.voice, rate="+0%").save(str(out))

    def process_storyboard(self, storyboard: dict) -> dict:
        segments = storyboard["segments"]
        wavs: list[Path] = []
        cues: list[dict] = []
        cursor = 0.0

        for i, seg in enumerate(segments):
            mp3 = config.AUDIO / f"seg_{i:04d}.mp3"
            if not mp3.exists():
                asyncio.run(self._synth(seg["narration"], mp3))
            dur = _probe(mp3)
            cues.append({
                "start": round(cursor, 3),
                "end": round(cursor + dur, 3),
                "text": seg["narration"],
            })
            cursor += dur

            wav = config.AUDIO / f"seg_{i:04d}.wav"
            if not wav.exists():
                subprocess.run(
                    [config.ffmpeg_bin(), "-y", "-i", str(mp3),
                     "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le", str(wav)],
                    check=True, capture_output=True,
                )
            wavs.append(wav)

        listfile = config.AUDIO / "audio_list.txt"
        listfile.write_text("".join(f"file '{w.name}'\n" for w in wavs),
                            encoding="utf-8")

        master = config.AUDIO / "master.wav"
        subprocess.run(
            [config.ffmpeg_bin(), "-y", "-f", "concat", "-safe", "0",
             "-i", listfile.name,
             "-af", "loudnorm=I=-16:TP=-1.5:LRA=11,aresample=24000",
             "-c:a", "pcm_s16le", str(master)],
            check=True, capture_output=True, cwd=config.AUDIO,
        )

        timeline = {
            "master_audio": str(master),
            "duration": _probe(master),
            "cues": cues,
        }
        (config.AUDIO / "timeline.json").write_text(
            json.dumps(timeline, indent=2), encoding="utf-8")
        log.info("audio: %.1fs across %d segments", timeline["duration"], len(cues))
        return timeline
