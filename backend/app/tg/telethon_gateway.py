"""Real Telegram access via Telethon (MTProto). Not unit-tested against the network;
only the error mapping is. Every public coroutine maps Telethon errors to app.tg.types."""

from collections.abc import Awaitable

from telethon import TelegramClient, errors, functions, types, utils
from telethon.sessions import StringSession

from app.tg.types import (
    AdminInfo,
    ChatRef,
    DialogInfo,
    JoinRequestInfo,
    MemberInfo,
    TgCodeExpired,
    TgError,
    TgFatalAuth,
    TgFloodWait,
    TgInvalidCode,
    TgInvalidPassword,
    TgNeedPassword,
    TgPermanent,
    TgPhoneInvalid,
    TgTransient,
    TgUser,
)

FATAL = (
    errors.AuthKeyUnregisteredError,
    errors.UserDeactivatedError,
    errors.UserDeactivatedBanError,
    errors.SessionRevokedError,
    errors.AuthKeyDuplicatedError,
)


def map_telethon_error(exc: BaseException) -> TgError:
    if isinstance(exc, TgError):
        return exc
    if isinstance(exc, FATAL):
        return TgFatalAuth(type(exc).__name__)
    if isinstance(exc, errors.FloodWaitError):
        return TgFloodWait(int(exc.seconds))
    if isinstance(exc, errors.SessionPasswordNeededError):
        return TgNeedPassword()
    if isinstance(exc, errors.PhoneCodeInvalidError):
        return TgInvalidCode()
    if isinstance(exc, errors.PhoneCodeExpiredError):
        return TgCodeExpired()
    if isinstance(exc, errors.PasswordHashInvalidError):
        return TgInvalidPassword()
    if isinstance(exc, errors.PhoneNumberInvalidError):
        return TgPhoneInvalid()
    if isinstance(exc, (ConnectionError, OSError, TimeoutError)):
        return TgTransient(str(exc) or type(exc).__name__)
    if isinstance(exc, errors.RPCError):
        return TgPermanent(getattr(exc, "message", None) or type(exc).__name__)
    return TgPermanent(f"{type(exc).__name__}: {exc}")


async def _call[T](aw: Awaitable[T]) -> T:
    try:
        return await aw
    except Exception as e:  # noqa: BLE001 - mapped below
        raise map_telethon_error(e) from e


def _new_client(session: str, api_id: int, api_hash: str) -> TelegramClient:
    return TelegramClient(
        StringSession(session),
        api_id,
        api_hash,
        connection_retries=5,
        retry_delay=2,
        flood_sleep_threshold=0,
        device_model="Voryx",
        app_version="1.0",
    )


def _display_name(u) -> str:
    if u is None:
        return ""
    if getattr(u, "title", None):
        return u.title
    return " ".join(p for p in (getattr(u, "first_name", None), getattr(u, "last_name", None)) if p) or str(u.id)


def _kind(entity) -> str:
    if isinstance(entity, types.Channel):
        return "channel" if entity.broadcast else "supergroup"
    return "group"


def _is_admin(entity) -> bool:
    return bool(getattr(entity, "creator", False) or getattr(entity, "admin_rights", None))


def _rights_dict(rights) -> dict[str, bool]:
    if rights is None:
        return {}
    return {k: bool(v) for k, v in rights.to_dict().items() if k != "_" and isinstance(v, bool)}


class TelethonLogin:
    def __init__(self, client: TelegramClient, phone: str, phone_code_hash: str) -> None:
        self.client, self.phone, self.phone_code_hash = client, phone, phone_code_hash

    async def _finish(self) -> str:
        session = self.client.session.save()
        await self.client.disconnect()
        return session

    async def submit_code(self, code: str) -> str:
        await _call(self.client.sign_in(self.phone, code, phone_code_hash=self.phone_code_hash))
        return await self._finish()

    async def submit_password(self, password: str) -> str:
        await _call(self.client.sign_in(password=password))
        return await self._finish()

    async def cancel(self) -> None:
        await self.client.disconnect()


class TelethonClient:
    def __init__(self, client: TelegramClient) -> None:
        self.c = client
        self._peers: dict[int, object] = {}

    async def _peer(self, ref: ChatRef):
        """Input peer valid for THIS account. Channel access_hash differs per user account, so the
        hash stored with the channel (from the importing account) is never trusted here."""
        real_id, peer_type = utils.resolve_id(ref.chat_id)
        if peer_type is types.PeerChat:
            return types.InputPeerChat(real_id)
        if peer_type is not types.PeerChannel:
            raise TgPermanent("referência de chat inválida")
        cached = self._peers.get(ref.chat_id)
        if cached is not None:
            return cached
        for attempt in range(2):
            try:
                peer = await self.c.get_input_entity(types.PeerChannel(real_id))
                self._peers[ref.chat_id] = peer
                return peer
            except ValueError:
                if attempt == 0:
                    await _call(self.c.get_dialogs(limit=None))  # fills this account's entity cache
        raise TgPermanent("a conta não participa deste grupo")

    async def _user_input(self, ref: ChatRef, user_id: int):
        try:
            return await self.c.get_input_entity(types.PeerUser(user_id))
        except ValueError:
            # entity cache is in-memory only; refresh it from the pending list, then retry
            await self.get_pending_requests(ref)
            try:
                return await self.c.get_input_entity(types.PeerUser(user_id))
            except ValueError as e:
                raise TgPermanent("usuário não encontrado — atualize a lista e tente de novo") from e

    async def get_me(self) -> TgUser:
        me = await _call(self.c.get_me())
        if me is None:
            raise TgFatalAuth("AuthKeyUnregisteredError")
        return TgUser(id=me.id, name=_display_name(me), username=me.username, phone=me.phone)

    async def list_admin_dialogs(self) -> list[DialogInfo]:
        out: list[DialogInfo] = []

        async def collect():
            async for d in self.c.iter_dialogs():
                e = d.entity
                if isinstance(e, (types.Channel, types.Chat)) and _is_admin(e):
                    out.append(
                        DialogInfo(
                            chat_id=utils.get_peer_id(e),
                            access_hash=getattr(e, "access_hash", None),
                            title=e.title,
                            username=getattr(e, "username", None),
                            kind=_kind(e),
                            member_count=getattr(e, "participants_count", None),
                        )
                    )

        await _call(collect())
        return out

    async def get_chat(self, ref: ChatRef) -> DialogInfo:
        peer = await self._peer(ref)
        if isinstance(peer, types.InputPeerChannel):
            full = await _call(self.c(functions.channels.GetFullChannelRequest(peer)))
            count = full.full_chat.participants_count
        else:
            full = await _call(self.c(functions.messages.GetFullChatRequest(peer.chat_id)))
            parts = getattr(full.full_chat, "participants", None)
            count = len(getattr(parts, "participants", []) or [])
        entity = full.chats[0]
        if not _is_admin(entity):
            raise TgPermanent("a conta não é admin deste grupo")
        return DialogInfo(
            chat_id=utils.get_peer_id(entity),
            access_hash=getattr(entity, "access_hash", None),
            title=entity.title,
            username=getattr(entity, "username", None),
            kind=_kind(entity),
            member_count=count,
        )

    async def get_admins(self, ref: ChatRef) -> list[AdminInfo]:
        peer = await self._peer(ref)
        users = await _call(self.c.get_participants(peer, filter=types.ChannelParticipantsAdmins()))
        out = []
        for u in users:
            p = getattr(u, "participant", None)
            if isinstance(p, (types.ChannelParticipantCreator, types.ChatParticipantCreator)):
                rights = {"creator": True}
            else:
                rights = _rights_dict(getattr(p, "admin_rights", None))
            out.append(AdminInfo(user_id=u.id, name=_display_name(u), rights=rights))
        return out

    async def get_pending_requests(self, ref: ChatRef, limit: int = 100) -> list[JoinRequestInfo]:
        res = await _call(
            self.c(
                functions.messages.GetChatInviteImportersRequest(
                    peer=await self._peer(ref),
                    requested=True,
                    offset_date=None,
                    offset_user=types.InputUserEmpty(),
                    limit=limit,
                )
            )
        )
        users = {u.id: u for u in res.users}
        return [
            JoinRequestInfo(
                user_id=imp.user_id,
                name=_display_name(users.get(imp.user_id)) or str(imp.user_id),
                username=getattr(users.get(imp.user_id), "username", None),
                requested_at=imp.date,
            )
            for imp in res.importers
        ]

    async def decide_request(self, ref: ChatRef, user_id: int, approve: bool) -> None:
        user = await self._user_input(ref, user_id)
        await _call(
            self.c(
                functions.messages.HideChatJoinRequestRequest(
                    peer=await self._peer(ref), user_id=user, approved=approve
                )
            )
        )

    async def approve_all(self, ref: ChatRef) -> None:
        await _call(
            self.c(functions.messages.HideAllChatJoinRequestsRequest(peer=await self._peer(ref), approved=True))
        )

    async def search_members(self, ref: ChatRef, query: str, offset: int, limit: int) -> list[MemberInfo]:
        users = await _call(self.c.get_participants(await self._peer(ref), search=query, limit=offset + limit))
        return [MemberInfo(user_id=u.id, name=_display_name(u), username=u.username) for u in users[offset:]]

    async def kick(self, ref: ChatRef, user_id: int) -> None:
        user = await self._user_input(ref, user_id)
        await _call(self.c.kick_participant(await self._peer(ref), user))

    async def ban(self, ref: ChatRef, user_id: int) -> None:
        user = await self._user_input(ref, user_id)
        await _call(self.c.edit_permissions(await self._peer(ref), user, view_messages=False))

    async def can_post(self, ref: ChatRef) -> bool:
        entity = await _call(self.c.get_entity(await self._peer(ref)))
        if getattr(entity, "creator", False):
            return True
        rights = getattr(entity, "admin_rights", None)
        if isinstance(entity, types.Channel) and entity.broadcast:
            return bool(rights and rights.post_messages)
        if rights:
            return True
        banned = getattr(entity, "default_banned_rights", None)
        return not (banned and banned.send_messages)

    async def send_post(self, ref: ChatRef, text: str, media_paths: list[str]) -> list[int]:
        peer = await self._peer(ref)
        if not media_paths:
            msg = await _call(self.c.send_message(peer, text))
            return [msg.id]
        files = media_paths[0] if len(media_paths) == 1 else media_paths
        res = await _call(self.c.send_file(peer, files, caption=text or None))
        msgs = res if isinstance(res, list) else [res]
        return [m.id for m in msgs]

    async def disconnect(self) -> None:
        await self.c.disconnect()


class TelethonGateway:
    async def start_login(self, phone: str, api_id: int, api_hash: str) -> TelethonLogin:
        client = _new_client("", api_id, api_hash)
        await _call(client.connect())
        try:
            sent = await _call(client.send_code_request(phone))
        except TgError:
            await client.disconnect()
            raise
        return TelethonLogin(client, phone, sent.phone_code_hash)

    async def connect(self, session: str, api_id: int, api_hash: str) -> TelethonClient:
        client = _new_client(session, api_id, api_hash)
        try:
            await _call(client.connect())
            me = await _call(client.get_me())
        except TgFatalAuth:
            await client.disconnect()
            raise
        except TgError as e:
            await client.disconnect()
            # FloodWait / server errors / timeouts are NOT proof the session is dead
            if isinstance(e, (TgFloodWait, TgTransient)):
                raise
            raise TgTransient(str(e)) from e
        if me is None:
            await client.disconnect()
            raise TgFatalAuth("AuthKeyUnregisteredError")
        return TelethonClient(client)
