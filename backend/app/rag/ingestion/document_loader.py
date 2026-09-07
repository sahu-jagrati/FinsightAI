"""document_loader — validates and persists an uploaded file to disk.

Kept deliberately dumb: no parsing happens here. Its only job is turning an
`UploadFile` into bytes safely on disk plus the metadata (size, hash,
extension) later stages and the DB row need. Splitting this out from
`document_parser` means format validation and disk I/O concerns can change
without touching extraction logic.
"""

import hashlib
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile

from app.core.config import settings
from app.core.exceptions import FileTooLargeError, UnsupportedFileTypeError

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass
class LoadedFile:
    stored_filename: str
    original_filename: str
    file_path: str
    file_size_bytes: int
    content_hash: str
    extension: str


def _sanitize_filename(name: str) -> str:
    name = Path(name).name  # strip any path components
    name = _SAFE_NAME_RE.sub("_", name)
    return name or "upload"


async def save_upload(file: UploadFile) -> LoadedFile:
    """Validate extension/size, stream the file to disk, and return metadata.

    Raises `UnsupportedFileTypeError` / `FileTooLargeError` (Section 32)
    before anything is written if validation fails.
    """
    original_name = file.filename or "upload"
    extension = Path(original_name).suffix.lower()

    allowed_extensions = settings.allowed_upload_extensions
    if extension not in allowed_extensions:
        raise UnsupportedFileTypeError(
            f"'{extension}' is not a supported file type. "
            f"Allowed: {', '.join(allowed_extensions)}"
        )

    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)

    stored_filename = f"{uuid.uuid4().hex}_{_sanitize_filename(original_name)}"
    dest_path = upload_dir / stored_filename

    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    hasher = hashlib.sha256()
    total_bytes = 0

    with dest_path.open("wb") as out:
        while chunk := await file.read(1024 * 1024):
            total_bytes += len(chunk)
            if total_bytes > max_bytes:
                out.close()
                dest_path.unlink(missing_ok=True)
                raise FileTooLargeError(
                    f"File exceeds the {settings.MAX_UPLOAD_MB}MB upload limit."
                )
            hasher.update(chunk)
            out.write(chunk)

    await file.close()

    return LoadedFile(
        stored_filename=stored_filename,
        original_filename=original_name,
        file_path=str(dest_path),
        file_size_bytes=total_bytes,
        content_hash=hasher.hexdigest(),
        extension=extension,
    )
