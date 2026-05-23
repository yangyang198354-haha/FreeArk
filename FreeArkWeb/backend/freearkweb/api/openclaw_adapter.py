"""
OpenClaw Gateway adapter (MOD-BE-02 v1.2 — WebSocket Gateway RPC).

Connects to the OpenClaw Gateway via its native WebSocket RPC protocol
(protocol v4) and forwards token deltas to ChatConsumer as an async generator.

Verified against OpenClaw 2026.5.20 (Node.js gateway) on 2026-05-23 via
end-to-end probe → DeepSeek round-trip. The earlier v1.1 assumption of
``POST /v1/agent/run/stream`` SSE did not match the real wire protocol;
this revision speaks the documented WS protocol the official CLI uses.

Protocol summary (one WS connection per chat.send call):
  1. WS connect to ws(s)://<host>:<port>/ with Authorization: Bearer <token>
  2. Server sends event:connect.challenge {nonce, ts}
  3. Client sends req method:"connect" with backend+loopback shortcut
     (no device ECDSA signature required when client.mode="backend",
      connection is loopback, and shared token is present)
  4. Server sends res ok:true with hello-ok payload (server, protocol,
     auth, policy, features.methods, features.events)
  5. Client sends req method:"chat.send" with
     {sessionKey, message, idempotencyKey}
  6. Server sends res ok:true {runId, status:"started"}
  7. Server streams event:"chat" frames whose payload.state ∈
     {delta, final, aborted, error}; payload.deltaText carries token chunks.

Other event names (agent, health, tick, heartbeat, presence, ...) are ignored.

Security:
  - OPENCLAW_GATEWAY_TOKEN read from Django settings (server-side .env);
    never appears in yielded chunks or sent to the browser.
  - Token never logged at WARNING or above.
  - No chat history stored in FreeArk; OpenClaw normalizes the supplied
    sessionKey to "agent:main:<key>" internally and maintains context there.

项目: FreeArk_Openclaw
文档引用: module_design.md MOD-BE-02, architecture_design.md ADR-002 (v1.2)
需求引用: REQ-FUNC-005, REQ-NFR-002, REQ-NFR-004
"""

import asyncio
import json
import logging
import uuid
from typing import AsyncGenerator, Optional

try:
    import aiohttp
except ImportError:
    aiohttp = None  # type: ignore[assignment]

from django.conf import settings

logger = logging.getLogger('api.openclaw_adapter')


class OpenClawUnavailableError(Exception):
    """Raised on connect failure, handshake rejection, terminal aborted/error
    events from OpenClaw, or unexpected WS disconnection. ChatConsumer maps
    this to the OPENCLAW_UNAVAILABLE error code sent to the browser."""
    pass


# Operator scopes required by chat.send (operator.write at minimum).
# Including read/admin also enables chat.history / chat.abort over the
# same connection should that be needed later.
_DEFAULT_SCOPES = ("operator.read", "operator.write", "operator.admin")

# OpenClaw 2026.5.20 ships gateway protocol v4 only.
_PROTOCOL_VERSION = 4


class OpenClawAdapter:
    """OpenClaw Gateway WS adapter. See module docstring for the wire protocol."""

    # -----------------------------------------------------------------
    # Config & URL helpers
    # -----------------------------------------------------------------

    @classmethod
    def _get_config(cls):
        """Read runtime config lazily (after Django settings are loaded)."""
        return {
            'base_url': getattr(settings, 'OPENCLAW_BASE_URL', 'http://127.0.0.1:18789'),
            'token': getattr(settings, 'OPENCLAW_GATEWAY_TOKEN', ''),
            'timeout': getattr(settings, 'OPENCLAW_TIMEOUT', 60),
            'connect_timeout': getattr(settings, 'OPENCLAW_CONNECT_TIMEOUT', 10),
        }

    @staticmethod
    def _to_ws_url(base_url: str) -> str:
        """Normalize an http(s):// base URL to ws(s):// with trailing slash.

        Accepts: 'http://host:port', 'https://host:port', 'ws://...', 'wss://...'.
        For settings already on http(s):// (legacy from v1.1) we transparently
        upgrade to ws(s):// so deployments don't need to rewrite the env var.
        """
        b = base_url.strip()
        if b.startswith('https://'):
            b = 'wss://' + b[len('https://'):]
        elif b.startswith('http://'):
            b = 'ws://' + b[len('http://'):]
        elif not b.startswith(('ws://', 'wss://')):
            b = 'ws://' + b
        # Strip path components except the bare root — OpenClaw Gateway is at '/'.
        # Keep trailing '/' to make the upgrade target explicit.
        if b.endswith('/'):
            return b
        return b + '/'

    # -----------------------------------------------------------------
    # Frame builders
    # -----------------------------------------------------------------

    @staticmethod
    def _build_connect_frame(req_id: str, token: str) -> dict:
        """Construct the 'connect' request frame for backend+loopback+token mode.

        Mirrors what the official CLI sends in that mode (no device signature).
        """
        return {
            'type': 'req',
            'id': req_id,
            'method': 'connect',
            'params': {
                'minProtocol': _PROTOCOL_VERSION,
                'maxProtocol': _PROTOCOL_VERSION,
                'client': {
                    'id': 'gateway-client',
                    'version': 'freeark-1.0',
                    'platform': 'linux',
                    'mode': 'backend',
                },
                'caps': [],
                'auth': {'token': token},
                'role': 'operator',
                'scopes': list(_DEFAULT_SCOPES),
            },
        }

    @staticmethod
    def _build_chat_send_frame(req_id: str, session_key: str, message: str,
                                idempotency_key: str) -> dict:
        """Construct the 'chat.send' request frame."""
        return {
            'type': 'req',
            'id': req_id,
            'method': 'chat.send',
            'params': {
                'sessionKey': session_key,
                'message': message,
                'idempotencyKey': idempotency_key,
            },
        }

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    @classmethod
    async def stream_chat(
        cls,
        message: str,
        session_key: str,
    ) -> AsyncGenerator[str, None]:
        """Send a chat message to OpenClaw; yield deltaText chunks as they arrive.

        Args:
          message:     User message text (raw, no system prompt).
          session_key: FreeArk-side session UUID. OpenClaw normalizes this to
                       ``agent:main:<key>`` internally; the adapter does not
                       touch the value beyond passing it through.

        Yields:
          str — non-empty incremental token text from event:chat state:delta.

        Raises:
          OpenClawUnavailableError — connection failure, handshake rejection,
                                     terminal aborted/error event, scope error,
                                     unexpected disconnect.
          asyncio.TimeoutError — total response time exceeded OPENCLAW_TIMEOUT.

        Notes:
          - Each call opens a fresh WS; FreeArk does NOT pool connections.
            For a single user message that's fine; reconsider only if
            multi-message bursts become common (see RISK-001).
          - aiohttp.ClientTimeout(total=OPENCLAW_TIMEOUT) gates the whole flow
            including the WS upgrade, the handshake and the streaming reply.
        """
        cfg = cls._get_config()
        if aiohttp is None:
            raise OpenClawUnavailableError(
                'aiohttp not installed (pip install aiohttp>=3.9.0)'
            )
        if not cfg['token']:
            logger.warning('OPENCLAW_GATEWAY_TOKEN not configured')
            raise OpenClawUnavailableError('OpenClaw gateway token not configured')

        ws_url = cls._to_ws_url(cfg['base_url'])
        token = cfg['token']
        connect_req_id = uuid.uuid4().hex
        chat_req_id = uuid.uuid4().hex
        idempotency_key = uuid.uuid4().hex

        client_timeout = aiohttp.ClientTimeout(
            total=cfg['timeout'],
            sock_connect=cfg['connect_timeout'],
        )
        headers = {'Authorization': f'Bearer {token}'}

        try:
            async with aiohttp.ClientSession(timeout=client_timeout) as session:
                # heartbeat=30s matches OpenClaw's policy.tickIntervalMs default,
                # so a missed tick fires aiohttp's auto-ping rather than us closing.
                async with session.ws_connect(
                    ws_url,
                    headers=headers,
                    heartbeat=30,
                    max_msg_size=8 * 1024 * 1024,
                ) as ws:
                    connect_acked = False
                    chat_started = False
                    our_run_id: Optional[str] = None

                    async for msg in ws:
                        if msg.type != aiohttp.WSMsgType.TEXT:
                            if msg.type in (aiohttp.WSMsgType.CLOSED,
                                             aiohttp.WSMsgType.CLOSING):
                                raise OpenClawUnavailableError(
                                    'OpenClaw connection closed unexpectedly'
                                )
                            if msg.type == aiohttp.WSMsgType.ERROR:
                                logger.error('OpenClaw WS transport error: %s',
                                             ws.exception())
                                raise OpenClawUnavailableError(
                                    'OpenClaw WebSocket transport error'
                                )
                            # PING/PONG/BINARY are not used by this protocol; skip.
                            continue

                        try:
                            frame = json.loads(msg.data)
                        except (ValueError, TypeError):
                            # Malformed frame from server — surface as failure.
                            logger.warning('OpenClaw sent malformed JSON frame')
                            continue

                        ftype = frame.get('type')

                        # -------- Event frames (challenge + streaming) --------
                        if ftype == 'event':
                            ev = frame.get('event')
                            payload = frame.get('payload') or {}

                            if ev == 'connect.challenge' and not connect_acked:
                                # Respond with connect request (no device sig).
                                await ws.send_json(
                                    cls._build_connect_frame(connect_req_id, token)
                                )
                                continue

                            if ev == 'chat' and chat_started:
                                if our_run_id is not None and \
                                        payload.get('runId') != our_run_id:
                                    # Event for a different run on shared conn; ignore.
                                    continue
                                state = payload.get('state')
                                if state == 'delta':
                                    delta_text = payload.get('deltaText') or ''
                                    if delta_text:
                                        yield delta_text
                                elif state == 'final':
                                    # Normal end of stream.
                                    return
                                elif state == 'aborted':
                                    stop_reason = payload.get('stopReason') or 'unknown'
                                    logger.warning('OpenClaw chat aborted: %s',
                                                   stop_reason)
                                    raise OpenClawUnavailableError(
                                        f'OpenClaw aborted ({stop_reason})'
                                    )
                                elif state == 'error':
                                    err_kind = payload.get('errorKind') or 'unknown'
                                    err_msg = payload.get('errorMessage') or 'unknown'
                                    logger.error(
                                        'OpenClaw chat error: kind=%s msg=%s',
                                        err_kind, err_msg,
                                    )
                                    raise OpenClawUnavailableError(
                                        f'OpenClaw error ({err_kind}): {err_msg}'
                                    )
                                # else: ignore unknown state for forward-compat.

                            # All other event names are diagnostics; ignore.
                            continue

                        # -------- Response frames (handshake + chat.send ack) --
                        if ftype == 'res':
                            rid = frame.get('id')

                            if rid == connect_req_id:
                                if not frame.get('ok'):
                                    err = frame.get('error') or {}
                                    logger.error('OpenClaw connect rejected: %s',
                                                 err)
                                    raise OpenClawUnavailableError(
                                        f'OpenClaw connect rejected: '
                                        f'{err.get("message", "unknown")}'
                                    )
                                connect_acked = True
                                # Server is ready; submit chat.send.
                                await ws.send_json(
                                    cls._build_chat_send_frame(
                                        chat_req_id, session_key,
                                        message, idempotency_key,
                                    )
                                )
                                continue

                            if rid == chat_req_id:
                                if not frame.get('ok'):
                                    err = frame.get('error') or {}
                                    code = err.get('code') or 'UNKNOWN'
                                    text = err.get('message') or 'unknown'
                                    logger.error(
                                        'OpenClaw chat.send rejected: %s %s',
                                        code, text,
                                    )
                                    raise OpenClawUnavailableError(
                                        f'OpenClaw chat.send rejected ({code}): {text}'
                                    )
                                chat_started = True
                                our_run_id = (frame.get('payload') or {}).get('runId')
                                continue

                            # Response to some unknown request id; ignore.

                        # Other frame types (req from server, custom) — ignore.

                    # Iterator ended without seeing state:final.
                    if chat_started:
                        logger.warning(
                            'OpenClaw stream ended without final event'
                        )
                    raise OpenClawUnavailableError(
                        'OpenClaw stream ended unexpectedly'
                    )

        except aiohttp.ClientConnectorError as exc:
            logger.error('Cannot connect to OpenClaw Gateway (%s): %s',
                         ws_url, exc)
            raise OpenClawUnavailableError(
                'Cannot connect to OpenClaw Gateway (service down?)'
            ) from exc
        except aiohttp.WSServerHandshakeError as exc:
            logger.error('OpenClaw WS handshake failed (HTTP %s): %s',
                         exc.status, exc.message)
            if exc.status == 401:
                raise OpenClawUnavailableError(
                    'OpenClaw rejected token (401 during WS upgrade)'
                ) from exc
            raise OpenClawUnavailableError(
                f'OpenClaw WS handshake failed: HTTP {exc.status}'
            ) from exc
        except asyncio.TimeoutError:
            # Bubble up; ChatConsumer maps to the TIMEOUT error code.
            logger.warning('OpenClaw stream timed out (%ds total)', cfg['timeout'])
            raise
