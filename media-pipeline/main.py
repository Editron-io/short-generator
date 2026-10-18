#!/usr/bin/env python3
"""Coordinator — 5 sequential stages, resumable via work/state.json."""
import argparse, json, logging, sys, traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
import config
from modules.brain import ContentBrain
from modules.audio import AudioEngine
from modules.asset_manager import AssetManager
from modules.composer import Composer
from modules.uploader import Uploader

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("pipeline")

STATE = config.WORK / "state.json"


def _load_state() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {}


def _save_state(state: dict) -> None:
    STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def run(dry_run: bool = False) -> int:
    state = _load_state()
    done = set(state.get("done", []))

    # 1. storyboard
    if "script" not in done:
        log.info("=== 1/5 storyboard ===")
        state["storyboard"] = ContentBrain().generate_storyboard()
        done.add("script"); state["done"] = sorted(done); _save_state(state)
    board = state["storyboard"]

    # 2. narration
    if "audio" not in done:
        log.info("=== 2/5 narration ===")
        state["timeline"] = AudioEngine().process_storyboard(board)
        # Push per-segment duration back onto each segment for the slicer
        for i, cue in enumerate(state["timeline"]["cues"]):
            board["segments"][i]["duration"] = cue["end"] - cue["start"]
        done.add("audio"); state["done"] = sorted(done); _save_state(state)

    # 3. assets
    if "assets" not in done:
        log.info("=== 3/5 assets ===")
        state["clips"] = [str(p) for p in
                          AssetManager().build_clip_pool(board["segments"])]
        done.add("assets"); state["done"] = sorted(done); _save_state(state)

    # 4. render
    if "render" not in done:
        log.info("=== 4/5 render ===")
        state["final"] = str(Composer().compile(
            [Path(p) for p in state["clips"]], state["timeline"]))
        done.add("render"); state["done"] = sorted(done); _save_state(state)

    if dry_run:
        log.info("dry-run: skipping upload. artifact = %s", state["final"])
        return 0

    # 5. upload
    if "upload" not in done:
        log.info("=== 5/5 upload ===")
        publish_at = (datetime.now(timezone.utc) + timedelta(hours=1)) \
            .strftime("%Y-%m-%dT%H:%M:%S.000Z")
        vid = Uploader().upload(
            video=Path(state["final"]), meta=board, publish_at=publish_at,
        )
        state["video_id"] = vid
        done.add("upload"); state["done"] = sorted(done); _save_state(state)

    log.info("done: https://youtu.be/%s", state.get("video_id"))
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="Skip upload, keep artifact")
    ap.add_argument("--reset", action="store_true",
                    help="Delete state.json and exit")
    a = ap.parse_args()

    if a.reset:
        STATE.unlink(missing_ok=True)
        sys.exit(0)

    try:
        sys.exit(run(dry_run=a.dry_run))
    except Exception:                                    # noqa: BLE001
        log.error("PIPELINE FAILED\n%s", traceback.format_exc())
        sys.exit(1)
