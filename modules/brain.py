"""Module 1 — Trend/hook engine. Emits a chaptered storyboard."""
import json, logging, re
import config

log = logging.getLogger(__name__)

SYSTEM = """You are the head writer for a Speculative Fiction audio-documentary
channel in the style of declassified government archives and analog horror.
Output ONLY minified JSON. No markdown fences. No prose. No commentary.
Tone: bureaucratic, restrained, unsettling. Never gory. Never name real
living people. Frame everything as fiction."""

CHAPTER_PROMPT = """Write chapter {ch} of {total} of an original fictional report.

Chapter brief: {brief}

Requirements:
- Exactly {n} segments.
- Each "narration": 8-20 words, a 4-6 second read at documentary pace.
- Each "visual_keyword": 2-4 words, a concrete filmable or archival image
  ("concrete bunker fog", "1970s radar array", "empty county road night").
- Narration must flow from prior chapter. End each chapter on a hook.

Return ONLY this JSON shape:
{{"summary":"one sentence recap of this chapter","segments":[{{"narration":"...","visual_keyword":"..."}}]}}"""

BRIEFS = [
    "The first anomaly report. A routine survey that went unexplained.",
    "The agency reopens the file. Contradicting evidence in the margins.",
    "A witness comes forward. Their account does not match the record.",
    "The geographic anomaly expands. Instruments fail in specific patterns.",
    "The incident is quietly reclassified. A secondary site is found.",
    "The archive closes. One final fragment survives.",
]


def _clean(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.M).strip()
    i, j = raw.find("{"), raw.rfind("}")
    if i == -1 or j == -1:
        raise ValueError("no JSON object in response")
    return raw[i:j + 1]


def _split_long(text: str, keyword: str) -> list[dict]:
    """Split a segment whose narration exceeds MAX_WORDS, on punctuation."""
    words = text.split()
    out = []
    while len(words) > config.MAX_WORDS:
        cut = config.MAX_WORDS
        for k in range(len(words[:cut]) - 1, max(len(words[:cut]) - 7, 0), -1):
            if words[k].endswith((".", "!", "?", ";", ",")):
                cut = k + 1
                break
        out.append({"narration": " ".join(words[:cut]), "visual_keyword": keyword})
        words = words[cut:]
    if words:
        out.append({"narration": " ".join(words), "visual_keyword": keyword})
    return out


class ContentBrain:
    def __init__(self):
        if not config.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is not set")
        from google import genai
        self._client = genai.Client(api_key=config.GEMINI_API_KEY)

    def _call(self, prompt: str) -> str:
        last = None
        for model in config.GEMINI_MODEL_CHAIN:
            try:
                log.info("brain: trying %s", model)
                r = self._client.models.generate_content(model=model, contents=prompt)
                return r.text or ""
            except Exception as e:                       # noqa: BLE001
                last = e
                log.warning("brain: %s failed: %s", model, e)
        raise RuntimeError(f"all Gemini models failed: {last}")

    def generate_storyboard(self) -> dict:
        segs: list[dict] = []
        prev_summary = "This is the opening chapter of the report."

        for ch in range(config.NUM_CHAPTERS):
            brief = BRIEFS[ch % len(BRIEFS)]
            prompt = (
                SYSTEM + "\n\n"
                + CHAPTER_PROMPT.format(
                    ch=ch + 1, total=config.NUM_CHAPTERS,
                    n=config.CHAPTER_SIZE, brief=brief,
                )
                + f"\n\nPrior chapter recap: {prev_summary}"
            )
            raw = _clean(self._call(prompt))
            chapter = json.loads(raw)
            for s in chapter.get("segments", []):
                n = " ".join(str(s.get("narration", "")).split())
                kw = " ".join(str(s.get("visual_keyword", "dark static")).split()) or "dark static"
                if n:
                    segs.extend(_split_long(n, kw))
            prev_summary = chapter.get("summary", prev_summary)
            log.info("brain: chapter %d/%d done (%d segments total)",
                     ch + 1, config.NUM_CHAPTERS, len(segs))

        if len(segs) < 20:
            raise RuntimeError(f"storyboard too short after coercion: {len(segs)} segments")

        meta_prompt = (
            SYSTEM
            + "\n\nGenerate YouTube metadata for this documentary. "
            "Return ONLY minified JSON: "
            '{"title":str,"description":str,"tags":[str]}. '
            f"First 3 narration lines: {' | '.join(s['narration'] for s in segs[:3])}"
        )
        try:
            meta = json.loads(_clean(self._call(meta_prompt)))
        except Exception:                                # noqa: BLE001
            meta = {"title": "Declassified: Anomaly Report",
                    "description": "", "tags": []}

        return {
            "title": str(meta.get("title", "Declassified: Anomaly Report"))[:100],
            "description": str(meta.get("description", "")),
            "tags": [str(t) for t in (meta.get("tags") or [])][:35],
            "segments": segs,
        }
