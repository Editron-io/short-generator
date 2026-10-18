"""Module 4 — Concat + burn stylized subtitles + mux audio."""
import logging, subprocess
from pathlib import Path
import config

log = logging.getLogger(__name__)

ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1280
PlayResY: 720
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Retro,Courier New,40,&H0000E5FF,&H000000FF,&H00101010,&H80000000,-1,0,0,0,100,100,1,0,1,3,2,2,70,70,52,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _ts(t: float) -> str:
    t = max(t, 0.0)
    h, m, s = int(t // 3600), int(t % 3600 // 60), t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def _wrap(text: str, width: int = 38) -> str:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width and cur:
            lines.append(cur); cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return r"\N".join(lines[:3])


def write_ass(cues: list[dict], dest: Path) -> Path:
    body = [
        f"Dialogue: 0,{_ts(c['start'])},{_ts(c['end'])},Retro,,0,0,0,,"
        f"{_wrap(c['text']).replace('{','(').replace('}',')')}"
        for c in cues
    ]
    dest.write_text(ASS_HEADER + "\n".join(body) + "\n", encoding="utf-8")
    return dest


class Composer:
    def compile(self, clips: list[Path], timeline: dict) -> Path:
        duration = timeline["duration"]

        # 1. concat demuxer (stream copy — no re-encode)
        listfile = config.WORK / "inputs.txt"
        listfile.write_text("".join(f"file '{c.name}'\n" for c in clips),
                            encoding="utf-8")
        concat = config.OUT / "concat.mp4"
        subprocess.run(
            [config.ffmpeg_bin(), "-y", "-f", "concat", "-safe", "0",
             "-i", listfile.name, "-c", "copy", str(concat)],
            check=True, capture_output=True, cwd=config.WORK,
        )

        # 2. burn subtitles + mux audio
        ass = write_ass(timeline["cues"], config.OUT / "subs.ass")
        final = config.OUT / "final.mp4"
        subprocess.run(
            [config.ffmpeg_bin(), "-y",
             "-i", str(concat),
             "-i", timeline["master_audio"],
             "-vf", f"ass={ass.name}",
             "-map", "0:v:0", "-map", "1:a:0",
             "-t", f"{duration:.3f}",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
             "-c:a", "aac", "-b:a", "160k", "-ar", "24000", "-ac", "2",
             "-movflags", "+faststart",
             str(final)],
            check=True, capture_output=True, cwd=config.OUT,
        )
        log.info("composer: rendered %s (%.1fs)", final.name, duration)
        return final
