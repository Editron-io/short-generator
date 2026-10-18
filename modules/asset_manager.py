"""Module 3 — Priority-fallback asset harvesting + per-segment distress."""
import logging, random, re, subprocess
from pathlib import Path
import requests
import config

log = logging.getLogger(__name__)
UA = {"User-Agent": "media-pipeline/1.0"}
TIMEOUT = 30
MAX_IA_BYTES = 250 * 1024 * 1024
IMG_EXT = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".gif", ".bmp"}


def _slug(kw: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", kw.lower()).strip("_")[:60]


def _download(url: str, dest: Path) -> Path:
    with requests.get(url, headers=UA, timeout=120, stream=True) as r:
        r.raise_for_status()
        with dest.open("wb") as fh:
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)
    return dest


# ---------- Priority 1: Internet Archive --------------------------------
def _ia_search(kw: str, collection: str | None = "prelinger") -> list[str]:
    q = f"({kw}) AND mediatype:(movies)"
    if collection:
        q += f" AND collection:({collection})"
    r = requests.get(
        "https://archive.org/advancedsearch.php",
        params={"q": q, "fl[]": ["identifier"], "rows": 12,
                "page": 1, "output": "json"},
        headers=UA, timeout=TIMEOUT,
    )
    r.raise_for_status()
    return [d["identifier"] for d in r.json()["response"]["docs"]]


def _ia_pick(identifier: str) -> tuple[str, bool] | None:
    r = requests.get(f"https://archive.org/metadata/{identifier}",
                     headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    files = r.json().get("files", [])
    for f in files:
        n = f.get("name", "")
        if n.lower().endswith((".mp4", ".mpeg", ".mpg", ".ogv")):
            if int(f.get("size", 0) or 0) > MAX_IA_BYTES:
                continue
            return f"https://archive.org/download/{identifier}/{n}", False
    for f in files:
        n = f.get("name", "")
        if Path(n).suffix.lower() in IMG_EXT:
            return f"https://archive.org/download/{identifier}/{n}", True
    return None


def harvest_archive(kw: str, idx: int) -> Path | None:
    try:
        ids = _ia_search(kw) or _ia_search(kw, collection=None)
        random.shuffle(ids)
        for ident in ids[:4]:
            pick = _ia_pick(ident)
            if not pick:
                continue
            url, is_img = pick
            suffix = Path(url).suffix or (".jpg" if is_img else ".mp4")
            raw = config.CACHE / f"ia_{idx}_{ident[:24]}{suffix}"
            if not raw.exists():
                _download(url, raw)
            return raw
    except Exception as e:                              # noqa: BLE001
        log.warning("archive miss for %r: %s", kw, e)
    return None


# ---------- Priority 2: stock video -------------------------------------
def harvest_pexels(kw: str, idx: int) -> Path | None:
    if not config.PEXELS_API_KEY:
        return None
    try:
        r = requests.get(
            "https://api.pexels.com/videos/search",
            headers={"Authorization": config.PEXELS_API_KEY},
            params={"query": kw, "orientation": "landscape",
                    "size": "medium", "per_page": 6},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        for v in r.json().get("videos", []):
            for f in sorted(v.get("video_files", []),
                            key=lambda x: x.get("width") or 0, reverse=True):
                if (f.get("width") or 0) >= 1280:
                    raw = config.CACHE / f"pex_{idx}_{v['id']}.mp4"
                    if not raw.exists():
                        _download(f["link"], raw)
                    return raw
    except Exception as e:                              # noqa: BLE001
        log.warning("pexels miss for %r: %s", kw, e)
    return None


def harvest_pixabay(kw: str, idx: int) -> Path | None:
    if not config.PIXABAY_API_KEY:
        return None
    try:
        r = requests.get(
            "https://pixabay.com/api/videos/",
            params={"key": config.PIXABAY_API_KEY,
                    "q": kw.replace(" ", "+"),
                    "video_type": "film", "per_page": 8},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        for hit in r.json().get("hits", []):
            v = hit.get("videos", {})
            src = (v.get("large") or v.get("medium") or {}).get("url")
            if src:
                raw = config.CACHE / f"pix_{idx}_{hit['id']}.mp4"
                if not raw.exists():
                    _download(src, raw)
                return raw
    except Exception as e:                              # noqa: BLE001
        log.warning("pixabay miss for %r: %s", kw, e)
    return None


# ---------- Fallback: CRT static ----------------------------------------
def make_crt_static(dest: Path, duration: float) -> Path:
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    w, h = config.RESOLUTION
    subprocess.run(
        [config.ffmpeg_bin(), "-y",
         "-f", "lavfi", "-i",
         f"color=c=0x0a0a0a:s={w}x{h}:r={config.FPS}:d={duration}",
         "-vf", "noise=alls=64:allf=t+u,eq=contrast=1.4,vignette=PI/5,format=yuv420p",
         "-c:v", "libx264", "-preset", "ultrafast", "-crf", "26",
         str(dest)],
        check=True, capture_output=True,
    )
    return dest


# ---------- Public API ---------------------------------------------------
class AssetManager:
    def build_clip_pool(self, segments: list[dict]) -> list[Path]:
        """One distressed clip per segment, trimmed to exact audio duration."""
        clips: list[Path] = []
        for i, seg in enumerate(segments):
            kw = seg.get("visual_keyword", "dark static")
            duration = float(seg.get("duration", config.CLIP_SECONDS))
            dest = config.CLIPS / f"clip_{i:04d}.mp4"
            if dest.exists() and dest.stat().st_size > 0:
                clips.append(dest)
                continue

            src = (harvest_archive(kw, i)
                   or harvest_pexels(kw, i)
                   or harvest_pixabay(kw, i))

            if src is None:
                make_crt_static(dest, duration)
            else:
                self._slice_and_distress(src, dest, duration)
            clips.append(dest)
            log.info("[%d/%d] %r → %s", i + 1, len(segments), kw, dest.name)
        return clips

    def _slice_and_distress(self, src: Path, dest: Path, duration: float) -> Path:
        """Extract `duration` from source, normalize to 720p, apply analog look."""
        w, h, fps = *config.RESOLUTION, config.FPS
        vf = (
            f"scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h},setsar=1,fps={fps},"
            f"colormatrix=bt709:bt601,"
            f"eq=contrast=1.18:brightness=-0.035:saturation=0.72:gamma=1.05,"
            f"rgbashift=rh=-2:bh=2,"
            f"noise=alls=14:allf=t+u,"
            f"vignette=PI/4.5"
        )
        if src.suffix.lower() in IMG_EXT:
            cmd = [config.ffmpeg_bin(), "-y", "-loop", "1", "-i", str(src),
                   "-t", f"{duration:.3f}", "-vf",
                   vf + f",zoompan=z='min(zoom+0.0012,1.22)':d={int(fps*duration)}"
                        f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps={fps}",
                   "-an", "-c:v", "libx264", "-preset", "ultrafast",
                   "-crf", "22", "-pix_fmt", "yuv420p", "-r", str(fps), str(dest)]
        else:
            offset = random.uniform(2.0, 12.0)
            cmd = [config.ffmpeg_bin(), "-y", "-ss", f"{offset:.2f}", "-i", str(src),
                   "-t", f"{duration:.3f}", "-an", "-vf", vf,
                   "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22",
                   "-pix_fmt", "yuv420p", "-r", str(fps), str(dest)]

        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=180)
            return dest
        except subprocess.CalledProcessError:
            log.warning("slice failed for %s — using CRT static", src.name)
            dest.unlink(missing_ok=True)
            return make_crt_static(dest, duration)
