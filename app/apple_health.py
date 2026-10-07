"""Streaming parser for Apple Health export XML and export ZIP files."""

import math
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import BinaryIO, Iterator

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

MAX_UPLOAD_BYTES = 100 * 1024 * 1024
MAX_XML_BYTES = 500 * 1024 * 1024
MAX_RECORDS_PER_IMPORT = 250_000


class ImportFileError(ValueError):
    """The supplied file is not a supported, valid Apple Health export."""


class ImportSizeLimitError(ImportFileError):
    """An upload or its expanded XML exceeds the supported size limit."""


@dataclass(frozen=True)
class HealthRecord:
    metric_type: str
    unit: str
    value: float
    start_date: str
    end_date: str


@dataclass
class ParseStats:
    imported_candidates: int = 0
    skipped_records: int = 0


class _LimitedReader:
    def __init__(self, stream: BinaryIO, max_bytes: int) -> None:
        self._stream = stream
        self._max_bytes = max_bytes
        self._bytes_read = 0

    def read(self, size: int = -1) -> bytes:
        chunk = self._stream.read(size)
        self._bytes_read += len(chunk)
        if self._bytes_read > self._max_bytes:
            raise ImportSizeLimitError("Expanded Apple Health XML exceeds 500 MiB.")
        return chunk


def _utc_timestamp(value: str | None, field_name: str) -> str:
    if not value:
        raise ImportFileError(f"Apple Health record is missing {field_name}.")
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ImportFileError(
            f"Apple Health record has an invalid {field_name}."
        ) from exc
    if timestamp.tzinfo is None:
        raise ImportFileError(
            f"Apple Health {field_name} must include a timezone offset."
        )
    return timestamp.astimezone(timezone.utc).isoformat()


def _records_from_xml(stream: BinaryIO, stats: ParseStats) -> Iterator[HealthRecord]:
    limited_stream = _LimitedReader(stream, MAX_XML_BYTES)
    try:
        root = None
        depth = 0
        for event, element in ElementTree.iterparse(
            limited_stream, events=("start", "end")
        ):
            if event == "start":
                if root is None:
                    root = element
                depth += 1
                continue
            if element.tag == "Record":
                metric_type = element.get("type", "")
                value_text = element.get("value")
                if not metric_type.startswith("HKQuantityTypeIdentifier"):
                    stats.skipped_records += 1
                elif not value_text or not element.get("unit"):
                    stats.skipped_records += 1
                else:
                    try:
                        value = float(value_text)
                    except ValueError as exc:
                        raise ImportFileError(
                            "Apple Health quantity record has a non-numeric value."
                        ) from exc
                    if not math.isfinite(value):
                        raise ImportFileError(
                            "Apple Health quantity record has a non-finite value."
                        )
                    stats.imported_candidates += 1
                    if stats.imported_candidates > MAX_RECORDS_PER_IMPORT:
                        raise ImportSizeLimitError(
                            "An import may contain at most 250,000 quantity records."
                        )
                    yield HealthRecord(
                        metric_type=metric_type,
                        unit=element.get("unit", ""),
                        value=value,
                        start_date=_utc_timestamp(
                            element.get("startDate"), "startDate"
                        ),
                        end_date=_utc_timestamp(element.get("endDate"), "endDate"),
                    )
            if root is not None and depth == 2:
                root.clear()
            depth -= 1
    except ImportFileError:
        raise
    except (DefusedXmlException, ElementTree.ParseError, OSError, ValueError) as exc:
        raise ImportFileError("The file is not valid Apple Health export XML.") from exc


def iter_health_records(stream: BinaryIO, filename: str) -> tuple[Iterator[HealthRecord], ParseStats]:
    """Return an iterator over quantity records and counters for skipped records."""
    stats = ParseStats()
    position = stream.tell()
    stream.seek(0, 2)
    upload_size = stream.tell()
    stream.seek(position)
    if upload_size > MAX_UPLOAD_BYTES:
        raise ImportSizeLimitError("Uploads may not exceed 100 MiB.")

    is_zip = zipfile.is_zipfile(stream)
    stream.seek(position)
    if is_zip:
        try:
            archive = zipfile.ZipFile(stream)
        except (OSError, zipfile.BadZipFile) as exc:
            raise ImportFileError("The upload is not a valid Apple Health ZIP.") from exc
        export_files = [
            item
            for item in archive.infolist()
            if item.filename.rsplit("/", 1)[-1] == "export.xml"
        ]
        if len(export_files) != 1:
            archive.close()
            raise ImportFileError(
                "Apple Health ZIP must contain exactly one export.xml file."
            )
        if export_files[0].file_size > MAX_XML_BYTES:
            archive.close()
            raise ImportSizeLimitError(
                "Expanded Apple Health XML exceeds 500 MiB."
            )

        def zip_records() -> Iterator[HealthRecord]:
            try:
                with archive.open(export_files[0]) as xml_stream:
                    yield from _records_from_xml(xml_stream, stats)
            except ImportFileError:
                raise
            except (
                OSError,
                zipfile.BadZipFile,
                RuntimeError,
                NotImplementedError,
            ) as exc:
                raise ImportFileError(
                    "Could not read export.xml from the Apple Health ZIP."
                ) from exc
            finally:
                archive.close()

        return zip_records(), stats

    if not filename.lower().endswith(".xml"):
        raise ImportFileError("Upload an Apple Health .xml file or export .zip.")
    return _records_from_xml(stream, stats), stats
