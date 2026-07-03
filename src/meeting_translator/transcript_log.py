from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def utc_stamp(value: datetime | None = None) -> str:
    current = value or utc_now()
    return current.strftime("%Y%m%d-%H%M%S")


@dataclass
class RunSummary:
    started_at: str
    ended_at: str | None
    input_device: str
    output_device: str
    target_language: str
    received_audio_bytes: int = 0
    input_transcript_segments: int = 0
    output_transcript_segments: int = 0
    error_status: str | None = None
    metrics: dict[str, object] | None = None


class TranscriptLogger:
    def __init__(
        self,
        *,
        input_device: str,
        output_device: str,
        target_language: str,
        log_dir: Path = Path("logs"),
    ) -> None:
        log_dir.mkdir(parents=True, exist_ok=True)
        started = utc_now()
        self.path = log_dir / f"meeting-translator-{utc_stamp(started)}.jsonl"
        self.summary = RunSummary(
            started_at=started.isoformat(),
            ended_at=None,
            input_device=input_device,
            output_device=output_device,
            target_language=target_language,
        )
        self._write({"type": "start", "summary": asdict(self.summary)})

    def _write(self, record: dict[str, object]) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            handle.write("\n")

    def input_transcript(self, text: str) -> None:
        self.summary.input_transcript_segments += 1
        self._write({"type": "input_transcript", "text": text, "time": utc_now().isoformat()})

    def output_transcript(self, text: str) -> None:
        self.summary.output_transcript_segments += 1
        self._write({"type": "output_transcript", "text": text, "time": utc_now().isoformat()})

    def output_audio(self, byte_count: int) -> None:
        self.summary.received_audio_bytes += byte_count

    def close(
        self,
        *,
        error_status: str | None = None,
        metrics: dict[str, object] | None = None,
    ) -> RunSummary:
        self.summary.ended_at = utc_now().isoformat()
        self.summary.error_status = error_status
        self.summary.metrics = metrics
        self._write({"type": "summary", "summary": asdict(self.summary)})
        return self.summary
