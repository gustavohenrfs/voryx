import logging
import os
import re
import uuid
from datetime import datetime, timedelta

from fastapi import HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import PostMedia, PostStatus, ScheduledPost

log = logging.getLogger("voryx.media")

CHUNK = 1024 * 1024
KEEP_AFTER_FINISH = timedelta(days=7)
ORPHAN_TTL = timedelta(hours=24)
_EXT_RE = re.compile(r"^\.[a-z0-9]{1,5}$")
_DEFAULT_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
    "video/webm": ".webm",
}


def _extension(filename: str | None, mime: str) -> str:
    ext = os.path.splitext(filename or "")[1].lower()
    if _EXT_RE.match(ext):
        return ".jpg" if ext == ".jpeg" else ext
    return _DEFAULT_EXT.get(mime, ".bin")


async def save_upload(db: AsyncSession, owner_id: int, file: UploadFile) -> PostMedia:
    mime = (file.content_type or "").lower()
    if not (mime.startswith("image/") or mime.startswith("video/")):
        raise HTTPException(415, "envie apenas fotos ou vídeos")
    settings = get_settings()
    limit = settings.max_upload_mb * 1024 * 1024
    folder = os.path.join(settings.media_dir, str(owner_id))
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, uuid.uuid4().hex + _extension(file.filename, mime))
    size = 0
    try:
        with open(path, "wb") as out:
            while chunk := await file.read(CHUNK):
                size += len(chunk)
                if size > limit:
                    raise HTTPException(413, f"arquivo maior que {settings.max_upload_mb} MB")
                out.write(chunk)
    except BaseException:
        if os.path.exists(path):
            os.remove(path)
        raise
    media = PostMedia(owner_id=owner_id, path=path, mime=mime, size=size)
    db.add(media)
    await db.flush()
    return media


def _remove_file(path: str) -> None:
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    except OSError:
        log.exception("could not remove %s", path)


async def cleanup_media(db: AsyncSession, now: datetime) -> int:
    """Delete media of posts finished (sent/canceled/failed) > 7 days ago, and orphans > 24 h."""
    finished = (
        (
            await db.execute(
                select(PostMedia)
                .join(ScheduledPost, PostMedia.post_id == ScheduledPost.id)
                .where(
                    ScheduledPost.status.in_([PostStatus.SENT, PostStatus.CANCELED, PostStatus.FAILED]),
                    ScheduledPost.finished_at < now - KEEP_AFTER_FINISH,
                )
            )
        )
        .scalars()
        .all()
    )
    orphans = (
        (
            await db.execute(
                select(PostMedia).where(PostMedia.post_id.is_(None), PostMedia.created_at < now - ORPHAN_TTL)
            )
        )
        .scalars()
        .all()
    )
    for m in [*finished, *orphans]:
        _remove_file(m.path)
        await db.delete(m)
    return len(finished) + len(orphans)
