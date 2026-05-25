"""
OpenClaw Gateway adapter (MOD-BE-02 v1.3 — WebSocket Gateway RPC).

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
     {sessionKey, message, idempotencyKey[, reasoningEffort]}
  6. Server sends res ok:true {runId, status:"started"}
  7. Server streams event:"chat" frames whose payload.state ∈
     {delta, final, aborted, error}; payload carries reasoning/content deltas.

Other event names (agent, health, tick, heartbeat, presence, ...) are ignored.

v1.3 变更（相对 v1.2）：
  - yield 协议升级：yield str → yield tuple[str, str]，即 (kind, text)
    kind ∈ {'reasoning', 'content'}
  - reasoning 字段防御性解析：_REASONING_FIELD 常量（首选 'reasoningDelta'）
    + kind=='reasoning' 备用路径，覆盖 OpenClaw 两种可能结构
  - reasoning_effort 透传：从 Django settings 读 OPENCLAW_REASONING_EFFORT，
    合法时注入 chat.send params.reasoningEffort（ADR-008）
  - 分段统计日志：对话结束时 INFO 输出 reasoning_tokens/content_tokens/各阶段毫秒数
    不打印 token 文本本身（REQ-NFR-007）

Security:
  - OPENCLAW_GATEWAY_TOKEN read from Django settings (server-side .env);
    never appears in yielded chunks or sent to the browser.
  - Token never logged at WARNING or above.
  - No chat history stored in FreeArk; OpenClaw normalizes the supplied
    sessionKey to "agent:main:<key>" internally and maintains context there.
  - reasoning/content token text never written to any log line.

项目: FreeArk_Openclaw
文档引用: module_design.md MOD-BE-02 v1.3, architecture_design.md ADR-006, ADR-008
需求引用: REQ-FUNC-008, REQ-FUNC-009, REQ-FUNC-012, REQ-NFR-007, REQ-NFR-008
"""

import asyncio
import json
import logging
import time
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

# Reasoning field name in event:chat state:delta payload.
# TODO(US-RSN-001): Confirm actual field name via production log probe (AC-008-01).
# Candidate values: 'reasoningDelta', 'thinkingDelta', 'reasoning'
# The fallback kind=='reasoning' path in stream_chat() covers the alternative
# structure where kind distinguishes reasoning/content and deltaText carries both.
# If reasoning_tokens remains 0 after deployment, trigger GROUP_E probe procedure
# to confirm the actual field name and update this constant (single-line fix).
_REASONING_FIELD = 'reasoningDelta'


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
            # reasoning_effort: '', 'low', 'medium', or 'high'
            # Empty string means do not pass the param (use model default).
            'reasoning_effort': getattr(settings, 'OPENCLAW_REASONING_EFFORT', '') or '',
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
    def _build_chat_send_frame(
        req_id: str,
        session_key: str,
        message: str,
        idempotency_key: str,
        reasoning_effort: str = '',
    ) -> dict:
        """Construct the 'chat.send' request frame.

        Args:
          reasoning_effort: If non-empty and a valid value ('low'/'medium'/'high'),
                            injected as params.reasoningEffort to control DeepSeek
                            reasoning depth. Empty string omits the param entirely
                            (model uses its default). Invalid values are rejected
                            upstream in _get_config validation.
        """
        params = {
            'sessionKey': session_key,
            'message': message,
            'idempotencyKey': idempotency_key,
        }
        if reasoning_effort in ('low', 'medium', 'high'):
            # camelCase key per OpenClaw RPC convention; confirm with US-RSN-001
            # probe if the actual key differs (ARCH-C-003).
            params['reasoningEffort'] = reasoning_effort
        return {
            'type': 'req',
            'id': req_id,
            'method': 'chat.send',
            'params': params,
        }

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    @classmethod
    async def stream_chat(
        cls,
        message: str,
        session_key: str,
    ) -> AsyncGenerator[tuple[str, str], None]:
        """Send a chat message to OpenClaw; yield (kind, text) tuples as they arrive.

        Args:
          message:     User message text (raw, no system prompt).
          session_key: FreeArk-side session UUID. OpenClaw normalizes this to
                       ``agent:main:<key>`` internally; the adapter does not
                       touch the value beyond passing it through.

        Yields:
          tuple[str, str] — (kind, text) where:
            kind: 'reasoning' | 'content'
            text: non-empty incremental token text
          Invariants:
            - text is never empty (empty text tuples are not yielded)
            - reasoning yields precede content yields (matches DeepSeek behavior)
            - a single delta frame may produce two consecutive yields
              (first reasoning then content) if both fields are non-empty

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
          - Token text is NEVER written to any log line (REQ-NFR-007).
            Only counts and durations appear in the stream_complete log entry.

        v1.3 reasoning field parsing (defensive, ADR-006):
          Priority 1: payload[_REASONING_FIELD] (e.g. 'reasoningDelta')
          Priority 2: payload.get('kind') == 'reasoning' → use deltaText as reasoning
          This covers both known OpenClaw payload structures without branching.
        """
        cfg = cls._get_config()
        if aiohttp is None:
            raise OpenClawUnavailableError(
                'aiohttp not installed (pip install aiohttp>=3.9.0)'
            )
        if not cfg['token']:
            logger.warning('OPENCLAW_GATEWAY_TOKEN not configured')
            raise OpenClawUnavailableError('OpenClaw gateway token not configured')

        # Validate reasoning_effort early; warn and clear if invalid.
        reasoning_effort = cfg.get('reasoning_effort', '')
        if reasoning_effort and reasoning_effort not in ('low', 'medium', 'high'):
            logger.warning(
                'OPENCLAW_REASONING_EFFORT=%s 非法（low/medium/high），忽略',
                reasoning_effort,
            )
            reasoning_effort = ''

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

        # Timing and token counters for stream_complete log (REQ-NFR-008).
        # None values mean "phase not yet started".
        start_time = time.monotonic()
        reasoning_tokens = 0
        content_tokens = 0
        reasoning_phase_start: Optional[float] = None
        content_phase_start: Optional[float] = None
        reasoning_ms = 0
        content_ms = 0
        _in_reasoning_phase = False  # tracks current phase for timing handoff

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
                                    # --- v1.3 defensive dual-path reasoning parse ---
                                    # Path 1: independent field (e.g. 'reasoningDelta')
                                    reasoning_text = payload.get(_REASONING_FIELD) or ''
                                    # Path 2: kind=='reasoning' uses deltaText as content
                                    if not reasoning_text and \
                                            payload.get('kind') == 'reasoning':
                                        reasoning_text = payload.get('deltaText') or ''
                                        delta_text = ''
                                    else:
                                        delta_text = payload.get('deltaText') or ''

                                    if reasoning_text:
                                        # Start reasoning phase timer on first token.
                                        if reasoning_phase_start is None:
                                            reasoning_phase_start = time.monotonic()
                                        _in_reasoning_phase = True
                                        reasoning_tokens += 1
                                        yield ('reasoning', reasoning_text)

                                    if delta_text:
                                        # Transition: reasoning → content phase.
                                        if _in_reasoning_phase:
                                            _in_reasoning_phase = False
                                            if reasoning_phase_start is not None:
                                                reasoning_ms = int(
                                                    (time.monotonic() - reasoning_phase_start)
                                                    * 1000
                                                )
                                        if content_phase_start is None:
                                            content_phase_start = time.monotonic()
                                        content_tokens += 1
                                        yield ('content', delta_text)

                                elif state == 'final':
                                    # Normal end of stream — emit statistics log.
                                    now = time.monotonic()
                                    total_ms = int((now - start_time) * 1000)
                                    # Finalize any still-open phase.
                                    if _in_reasoning_phase and reasoning_phase_start is not None:
                                        reasoning_ms = int((now - reasoning_phase_start) * 1000)
                                    if content_phase_start is not None:
                                        content_ms = int((now - content_phase_start) * 1000)
                                    logger.info(
                                        'stream_complete session=%s '
                                        'reasoning_tokens=%d content_tokens=%d '
                                        'reasoning_ms=%d content_ms=%d total_ms=%d',
                                        session_key[:8],
                                        reasoning_tokens, content_tokens,
                                        reasoning_ms, content_ms, total_ms,
                                    )
                                    return

                                elif state == 'aborted':
                                    stop_reason = payload.get('stopReason') or 'unknown'
                                    logger.warning('OpenClaw chat aborted: %s',
                                                   stop_reason)
                                    logger.info(
                                        'stream_incomplete session=%s '
                                        'reasoning_tokens=%d content_tokens=%d reason=aborted',
                                        session_key[:8],
                                        reasoning_tokens, content_tokens,
                                    )
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
                                    logger.info(
                                        'stream_incomplete session=%s '
                                        'reasoning_tokens=%d content_tokens=%d reason=error',
                                        session_key[:8],
                                        reasoning_tokens, content_tokens,
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
                                        reasoning_effort=reasoning_effort,
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
                    logger.info(
                        'stream_incomplete session=%s '
                        'reasoning_tokens=%d content_tokens=%d reason=timeout',
                        session_key[:8],
                        reasoning_tokens, content_tokens,
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
