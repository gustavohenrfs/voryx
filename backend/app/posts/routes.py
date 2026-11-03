from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.service import ref_of
from app.deps import current_user, get_db, get_owned, owned
from app.jobs.runner import enqueue
from app.models import Channel, Job, JobStatus, PostMedia, PostStatus, ScheduledPost, TgAccount, User
from app.posts.media import save_upload
from app.tg.http import tg_call
from app.timeutil import utcnow

router = APIRouter(tags=["posts"])

MAX_TEXT = 4096
MAX_CAPTION = 1024
MAX_MEDIA = 10
PAST_TOLERANCE = timedelta(seconds=60)


class MediaOut(BaseModel):
    id: int
    mime: str
    size: int


class PostIn(BaseModel):
    account_id: int
    channel_id: int
    text: str = ""
    media_ids: list[int] = Field(default_factory=list)
    run_at: datetime | None = None
    post_now: bool = False


class PostPatch(BaseModel):
    text: str | None = None
    media_ids: list[int] | None = None
    run_at: datetime | None = None
    post_now: bool = False


class PostOut(BaseModel):
    id: int
    account_id: int | None
    channel_id: int | None
    text: str
    run_at: datetime
    status: str
    error: str | None
    media: list[MediaOut]
    sent_message_ids: list[int] | None
    finished_at: datetime | None
    created_at: datetime


async def _out(db: AsyncSession, post: ScheduledPost) -> PostOut:
    media = (
        await db.execute(select(PostMedia).where(PostMedia.post_id == post.id).order_by(PostMedia.position))
    ).scalars()
    return PostOut(
        id=post.id,
        account_id=post.account_id,
        channel_id=post.channel_id,
        text=post.text,
        run_at=post.run_at,
        status=post.status,
        error=post.error,
        media=[MediaOut(id=m.id, mime=m.mime, size=m.size) for m in media],
        sent_message_ids=post.sent_message_ids,
        finished_at=post.finished_at,
        created_at=post.created_at,
    )


def _resolve_run_at(run_at: datetime | None, post_now: bool) -> datetime:
    now = utcnow()
    if post_now:
        return now
    if run_at is None:
        raise HTTPException(422, "informe o horário ou use 'postar agora'")
    if run_at.tzinfo is None:
        raise HTTPException(422, "horário sem fuso")
    if run_at < now - PAST_TOLERANCE:
        raise HTTPException(422, "horário no passado")
    return run_at


def _validate_text(text: str, n_media: int) -> None:
    if n_media > MAX_MEDIA:
        raise HTTPException(422, f"no máximo {MAX_MEDIA} mídias por post")
    if n_media == 0 and not text.strip():
        raise HTTPException(422, "post vazio")
    limit = MAX_CAPTION if n_media else MAX_TEXT
    if len(text) > limit:
        raise HTTPException(422, f"texto passa de {limit} caracteres")


async def _load_media(db: AsyncSession, ids: list[int], user: User, owner_id: int, post_id: int | None):
    if len(set(ids)) != len(ids):
        raise HTTPException(422, "mídia repetida")
    media = []
    for mid in ids:
        m = await get_owned(db, PostMedia, mid, user)
        if m.owner_id != owner_id:
            raise HTTPException(404, "não encontrado")
        if m.post_id is not None and m.post_id != post_id:
            raise HTTPException(409, "mídia já usada em outro post")
        media.append(m)
    return media


@router.post("/media", response_model=MediaOut, status_code=201)
async def upload_media(
    file: UploadFile = File(...), db: AsyncSession = Depends(get_db), user: User = Depends(current_user)
):
    m = await save_upload(db, user.id, file)
    await db.commit()
    return MediaOut(id=m.id, mime=m.mime, size=m.size)


@router.get("/posts", response_model=list[PostOut])
async def list_posts(
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    channel_id: int | None = None,
    account_id: int | None = None,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
):
    stmt = owned(select(ScheduledPost), ScheduledPost, user)
    if from_ is not None:
        stmt = stmt.where(ScheduledPost.run_at >= from_)
    if to is not None:
        stmt = stmt.where(ScheduledPost.run_at < to)
    if channel_id is not None:
        stmt = stmt.where(ScheduledPost.channel_id == channel_id)
    if account_id is not None:
        stmt = stmt.where(ScheduledPost.account_id == account_id)
    if status is not None:
        stmt = stmt.where(ScheduledPost.status == status)
    posts = (await db.execute(stmt.order_by(ScheduledPost.run_at).limit(500))).scalars().all()
    return [await _out(db, p) for p in posts]


@router.post("/posts", response_model=PostOut, status_code=201)
async def create_post(
    body: PostIn, request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)
):
    acc = await get_owned(db, TgAccount, body.account_id, user)
    ch = await get_owned(db, Channel, body.channel_id, user)
    if acc.owner_id != ch.owner_id:
        raise HTTPException(404, "não encontrado")
    run_at = _resolve_run_at(body.run_at, body.post_now)
    _validate_text(body.text, len(body.media_ids))
    media = await _load_media(db, body.media_ids, user, ch.owner_id, None)
    ref = ref_of(ch)
    if not await tg_call(request.app.state.manager, acc.id, lambda c: c.can_post(ref)):
        raise HTTPException(422, "a conta não pode postar neste grupo")
    post = ScheduledPost(owner_id=ch.owner_id, account_id=acc.id, channel_id=ch.id, text=body.text, run_at=run_at)
    db.add(post)
    await db.flush()
    for i, m in enumerate(media):
        m.post_id, m.position = post.id, i
    job = await enqueue(db, "send_post", {"post_id": post.id}, acc.id, run_at=run_at)
    post.job_id = job.id
    await db.commit()
    return await _out(db, post)


@router.patch("/posts/{post_id}", response_model=PostOut)
async def patch_post(
    post_id: int, body: PostPatch, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)
):
    post = await get_owned(db, ScheduledPost, post_id, user)
    if post.status != PostStatus.SCHEDULED:
        raise HTTPException(409, "só dá para editar posts agendados")
    text = body.text if body.text is not None else post.text
    if body.media_ids is not None:
        media = await _load_media(db, body.media_ids, user, post.owner_id, post.id)
        current = (await db.execute(select(PostMedia).where(PostMedia.post_id == post.id))).scalars().all()
        for m in current:
            if m.id not in body.media_ids:
                m.post_id = None  # becomes orphan, cleaned up later
        for i, m in enumerate(media):
            m.post_id, m.position = post.id, i
        n_media = len(media)
    else:
        n_media = len((await db.execute(select(PostMedia.id).where(PostMedia.post_id == post.id))).all())
    _validate_text(text, n_media)
    post.text = text
    if body.run_at is not None or body.post_now:
        post.run_at = _resolve_run_at(body.run_at, body.post_now)
        job = await db.get(Job, post.job_id) if post.job_id else None
        if job is not None and job.status == JobStatus.PENDING:
            job.run_at = post.run_at
    await db.commit()
    return await _out(db, post)


@router.delete("/posts/{post_id}")
async def cancel_post(post_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    post = await get_owned(db, ScheduledPost, post_id, user)
    if post.status != PostStatus.SCHEDULED:
        raise HTTPException(409, "só dá para cancelar posts agendados")
    post.status = PostStatus.CANCELED
    post.finished_at = utcnow()
    job = await db.get(Job, post.job_id) if post.job_id else None
    if job is not None and job.status == JobStatus.PENDING:
        job.status, job.last_error = JobStatus.FAILED, "cancelado"
    await db.commit()
    return {"ok": True}
