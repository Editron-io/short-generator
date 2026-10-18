"""Module 5 — Headless YouTube upload from base64 OAuth token blob."""
import base64, json, logging
from pathlib import Path
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import config

log = logging.getLogger(__name__)
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def _load_creds() -> Credentials:
    if not config.YOUTUBE_CREDENTIALS_B64:
        raise RuntimeError("YOUTUBE_CREDENTIALS_B64 missing")
    info = json.loads(base64.b64decode(config.YOUTUBE_CREDENTIALS_B64).decode())
    info.pop("refresh_token_expires_in", None)
    return Credentials.from_authorized_user_info(info, SCOPES)


class Uploader:
    def upload(self, video: Path, meta: dict, publish_at: str | None = None) -> str:
        yt = build("youtube", "v3", credentials=_load_creds(), cache_discovery=False)

        tags = [t for t in meta.get("tags", []) if isinstance(t, str)][:35]
        total = sum(len(t) for t in tags)
        while total > 480 and tags:
            total -= len(tags.pop())

        body = {
            "snippet": {
                "title": meta["title"][:100],
                "description": (
                    meta.get("description", "")
                    + "\n\nThis is a work of fiction."
                )[:4900],
                "tags": tags,
                "categoryId": "24",
                "defaultLanguage": "en",
                "defaultAudioLanguage": "en",
            },
            "status": {
                "privacyStatus": "private",
                "selfDeclaredMadeForKids": False,
                "license": "youtube",
                "embeddable": True,
            },
        }
        if publish_at:
            body["status"]["publishAt"] = publish_at

        media = MediaFileUpload(str(video), mimetype="video/mp4",
                                chunksize=8 * 1024 * 1024, resumable=True)
        req = yt.videos().insert(part="snippet,status", body=body, media_body=media)

        response, retries = None, 0
        while response is None:
            status, response = req.next_chunk()
            if status:
                log.info("upload %d%%", int(status.progress() * 100))
            if response is None:
                retries += 1
                if retries > 30:
                    raise RuntimeError("upload stalled")

        vid = response["id"]
        log.info("uploaded https://youtu.be/%s", vid)
        return vid
