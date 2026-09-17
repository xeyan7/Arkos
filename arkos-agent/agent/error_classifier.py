"""API error classification for smart failover and recovery.

A priority-ordered pipeline maps an API exception to a ``ClassifiedError``
whose recovery hints (retry, rotate credential, fallback, compress, abort) the
retry loop in run_agent.py consults instead of re-matching strings itself.
"""

from __future__ import annotations

import enum
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterator, Optional, Sequence

logger = logging.getLogger(__name__)

PROVIDER_STREAM_NON_JSON_ERROR_CODE = "provider_stream_non_json_data"



class FailoverReason(enum.Enum):
    """Why an API call failed — determines recovery strategy."""
    auth = "auth"
    auth_permanent = "auth_permanent"
    billing = "billing"
    rate_limit = "rate_limit"
    upstream_rate_limit = "upstream_rate_limit"
    overloaded = "overloaded"
    server_error = "server_error"
    timeout = "timeout"
    ssl_cert_verification = "ssl_cert_verification"
    context_overflow = "context_overflow"
    payload_too_large = "payload_too_large"
    image_too_large = "image_too_large"
    image_corrupt = "image_corrupt"
    model_not_found = "model_not_found"
    provider_policy_blocked = "provider_policy_blocked"
    content_policy_blocked = "content_policy_blocked"
    format_error = "format_error"
    invalid_encrypted_content = "invalid_encrypted_content"
    multimodal_tool_content_unsupported = "multimodal_tool_content_unsupported"
    reasoning_mandatory = "reasoning_mandatory"

    thinking_signature = "thinking_signature"
    long_context_tier = "long_context_tier"
    oauth_long_context_beta_forbidden = "oauth_long_context_beta_forbidden"
    llama_cpp_grammar_pattern = "llama_cpp_grammar_pattern"
    unknown = "unknown"


@dataclass
class ClassifiedError:
    """Structured classification of an API error with recovery hints."""

    reason: FailoverReason
    status_code: Optional[int] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    message: str = ""
    error_context: Dict[str, Any] = field(default_factory=dict)

    retryable: bool = True
    should_compress: bool = False
    should_rotate_credential: bool = False
    should_fallback: bool = False

    @property
    def is_auth(self) -> bool:
        return self.reason in {FailoverReason.auth, FailoverReason.auth_permanent}

    @property
    def billing_unverified(self) -> bool:
        """True when a ``billing`` verdict rests on an ambiguous body."""
        return bool(self.error_context.get("billing_unverified"))



_BILLING_PATTERNS = (
    "insufficient credits", "insufficient_quota", "insufficient balance", "credit balance",
    "credits exhausted", "credits have been exhausted", "requires available credits",
    "account balance is too low", "no usable credits", "top up your credits", "payment required",
    "billing hard limit", "exceeded your current quota", "account is deactivated", "plan does not include",
    "out of extra usage", "out of funds", "run out of funds", "balance_depleted",
    "model_not_supported_on_free_tier", "not available on the free tier",
)

_UNVERIFIED_BILLING_PATTERNS = ("out of extra usage",)

_XAI_SPENDING_LIMIT_ERROR_CODE = "personal-team-blocked:spending-limit"

_BILLING_ERROR_CODES = frozenset({
    "insufficient_quota", "billing_not_active", "payment_required", "insufficient_credits",
    "no_usable_credits", "balance_depleted", "model_not_supported_on_free_tier",
    "member_spend_cap_exceeded", _XAI_SPENDING_LIMIT_ERROR_CODE,
})

_RATE_LIMIT_PATTERNS = (
    "rate limit", "rate_limit", "too many requests", "throttled", "requests per minute",
    "tokens per minute", "requests per day", "try again in", "please retry after",
    "resource exhausted", "resource_exhausted", "resource-exhausted", "resourceexhausted",
    "rate increased too quickly", "throttlingexception", "too many concurrent requests",
    "servicequotaexceededexception", "throttling",
)

_OVERLOADED_PATTERNS = (
    "overloaded", "temporarily overloaded", "service is temporarily overloaded",
    "service may be temporarily overloaded", "server is overloaded", "server overloaded",
    "service overloaded", "service is overloaded", "upstream overloaded", "currently overloaded",
    "at capacity", "over capacity",
)

_USAGE_LIMIT_PATTERNS = ("usage limit", "quota", "limit exceeded", "key limit exceeded")
_USAGE_LIMIT_TRANSIENT_SIGNALS = (
    "try again", "retry", "resets at", "reset in", "resets in", "reset after", "available in",
    "wait", "requests remaining", "periodic", "window", "per minute", "per second",
)

_PAYLOAD_TOO_LARGE_PATTERNS = (
    "request entity too large", "payload too large", "error code: 413", "request_too_large",
    "request exceeds the maximum size",
)

_IMAGE_TOO_LARGE_PATTERNS = (
    "image exceeds", "image too large", "image_too_large", "image size exceeds", "image dimensions exceed",
    "dimensions exceed max allowed size", "max allowed size: 8000", "media exceeds", "media too large",
)

_IMAGE_CORRUPT_PATTERNS = (
    "invalid png image", "invalid jpeg image", "base64 string of provided image cannot be decoded",
    "downloaded response does not contain a valid jpg, png, webp, or ico image",
)

_MULTIMODAL_TOOL_CONTENT_PATTERNS = (
    "text is not set", "tool message content must be a string", "tool content must be a string",
    "tool message must be a string", "expected string, got list", "expected string, got array",
    "tool_call.content must be string",
)

_CONTEXT_OVERFLOW_PATTERNS = (
    "context length", "context size", "maximum context", "token limit", "too many tokens",
    "reduce the length", "exceeds the limit", "context window", "prompt is too long",
    "prompt exceeds max length", "max_tokens", "maximum number of tokens",
    "exceeds the max_model_len", "max_model_len", "prompt length", "input is too long", "maximum model length",
    "context length exceeded", "truncating input",
    "slot context", "n_ctx_slot",
    "超过最大长度", "上下文长度",
    "tokens in request more than max tokens allowed",
    "input is too long", "max input token", "input token", "exceeds the maximum number of input tokens",
    "maximum allowed input length",
)

_MODEL_NOT_FOUND_PATTERNS = (
    "is not a valid model", "invalid model", "model not found", "model_not_found", "does not exist",
    "no such model", "unknown model", "unsupported model", "no endpoints found that support tool use",
)

_NO_USER_QUERY_SIGNAL = "no user query found"

_INVALID_MESSAGE_BODY_PATTERNS = (
    "must have non-empty content", "messages must have non-empty", "invalid_request_body",
    "text content blocks must be non-empty", "content field is required",
    "messages: at least one message is required", _NO_USER_QUERY_SIGNAL,
)

_REQUEST_VALIDATION_PATTERNS = (
    "unknown parameter", "unsupported parameter", "unrecognized request argument",
    "invalid_request_error", "unknown_parameter", "unsupported_parameter",
)

_SERVER_INJECTED_PARAM_SENDERS: Dict[str, tuple] = {
    "prompt_cache_retention": ("meta", "muse", "msl", "model-api", "bedrock", "mantle"),
}
_PARAM_REJECTION_WORDS = ("not supported", "unsupported", "unknown", "unrecognized")

_THINKING_MUTATION_WORDS = ("signature", "cannot be modified", "must remain as they were")

_MOA_ADAPTER_SHAPE_BUGS = (
    "'types.SimpleNamespace' object is not iterable", "'types.SimpleNamespace' object has no attribute 'index'",
)

_PROVIDER_POLICY_BLOCKED_PATTERNS = (
    "no endpoints available matching your guardrail", "no endpoints available matching your data policy",
    "no endpoints found matching your data policy",
)

_CONTENT_POLICY_BLOCKED_PATTERNS = (
    "flagged for possible cybersecurity risk", "trusted access for cyber",
    "violates our usage policies", "violates openai's usage policies", "your request was flagged by",
    "prompt was flagged by our safety", "responses cannot be generated due to safety",
    "content_filter", "responsibleaipolicyviolation", "new_sensitive",
)

_AUTH_PATTERNS = (
    "invalid api key", "invalid_api_key", "gateway_auth_failed", "authentication", "unauthorized",
    "forbidden", "invalid token", "token expired", "token revoked", "access denied",
)

_EMPTY_PROVIDER_RESPONSE_PATTERNS = (
    "returned an empty response", "empty response despite retries", "provider returned an empty response",
    "model returning empty responses", "empty response stream",
)

_TIMEOUT_MESSAGE_PATTERNS = (
    "timed out", "turn timed out", "request timed out", "deadline exceeded", "operation timed out",
    "upstream timed out",
)

_CONNECTION_MESSAGE_PATTERNS = (
    "connection refused", "econnrefused", "no route to host", "network is unreachable", "network unreachable",
    "name or service not known", "temporary failure in name resolution", "nodename nor servname provided",
    "getaddrinfo failed", "getaddrinfo enotfound", "eai_again",
    "fetch failed", "failed to fetch",
    "upstream connect error",
)

_TRANSPORT_ERROR_TYPES = frozenset({
    "ReadTimeout", "ConnectTimeout", "PoolTimeout", "ConnectError", "RemoteProtocolError",
    "ConnectionError", "ConnectionResetError", "ConnectionAbortedError", "BrokenPipeError",
    "TimeoutError", "ReadError", "ServerDisconnectedError",
    "SSLError", "SSLZeroReturnError", "SSLWantReadError", "SSLWantWriteError", "SSLEOFError", "SSLSyscallError",
    "APIConnectionError", "APITimeoutError",
})

_SERVER_DISCONNECT_PATTERNS = (
    "server disconnected", "peer closed connection", "connection reset by peer", "connection was closed",
    "network connection lost", "unexpected eof", "incomplete chunked read",
)

_SSL_CERT_VERIFY_PATTERNS = (
    "certificate verify failed", "certificate_verify_failed", "unable to get local issuer certificate",
    "self-signed certificate", "self signed certificate", "certificate has expired",
    "hostname mismatch, certificate is not valid", "unable to verify the first certificate",
)

_SSL_TRANSIENT_PATTERNS = (
    "bad record mac", "ssl alert", "tls alert", "ssl handshake failure", "tlsv1 alert", "sslv3 alert",
    "bad_record_mac", "ssl_alert", "tls_alert", "tls_alert_internal_error", "[ssl:",
)



Verdict = Dict[str, Any]


def _v(reason: FailoverReason, **hints: Any) -> Verdict:
    return {"reason": reason, **hints}


_ROTATE_FALLBACK = {"should_rotate_credential": True, "should_fallback": True}
_ABORT_FALLBACK = {"retryable": False, "should_fallback": True}
_R = FailoverReason

_V_BILLING = _v(_R.billing, retryable=False, **_ROTATE_FALLBACK)
_V_RATE_LIMIT = _v(_R.rate_limit, **_ROTATE_FALLBACK)
_V_AUTH_ROTATE = _v(_R.auth, retryable=False, **_ROTATE_FALLBACK)
_V_AUTH_FALLBACK = _v(_R.auth, **_ABORT_FALLBACK)
_V_MODEL_NOT_FOUND = _v(_R.model_not_found, **_ABORT_FALLBACK)
_V_CONTENT_BLOCKED = _v(_R.content_policy_blocked, **_ABORT_FALLBACK)
_V_FORMAT_ERROR = _v(_R.format_error, **_ABORT_FALLBACK)
_V_POLICY_BLOCKED = _v(_R.provider_policy_blocked, retryable=False)
_V_SSL_CERT = _v(_R.ssl_cert_verification, retryable=False)
_V_CONTEXT_OVERFLOW = _v(_R.context_overflow, should_compress=True)
_V_PAYLOAD_TOO_LARGE = _v(_R.payload_too_large, should_compress=True)
_V_OVERLOADED, _V_SERVER_ERROR, _V_TIMEOUT, _V_UNKNOWN = map(_v, (_R.overloaded, _R.server_error, _R.timeout, _R.unknown))
_V_IMAGE_TOO_LARGE, _V_IMAGE_CORRUPT = _v(_R.image_too_large), _v(_R.image_corrupt)
_V_MULTIMODAL, _V_INVALID_ENCRYPTED = _v(_R.multimodal_tool_content_unsupported), _v(_R.invalid_encrypted_content)
_V_REASONING_MANDATORY = _v(_R.reasoning_mandatory, should_compress=False, should_fallback=False)
_REASONING_MANDATORY_PATTERN = "reasoning is mandatory"


def _billing_hints(error_msg: str) -> Verdict:
    """Billing verdict carrying the  ambiguity marker when applicable."""
    ctx: Dict[str, Any] = {}
    if any(p in error_msg for p in _UNVERIFIED_BILLING_PATTERNS):
        ctx = {"billing_unverified": True, "possible_content_filter": True}
    return {**_V_BILLING, "error_context": ctx}


def _first_match(error_msg: str, rules: Sequence[tuple[Sequence[str], Any]]) -> Optional[Verdict]:
    """Verdict of the first rule whose pattern list hits ``error_msg``."""
    for patterns, verdict in rules:
        if any(p in error_msg for p in patterns):
            return verdict(error_msg) if callable(verdict) else verdict
    return None


_IMAGE_TOOL_RULES = (
    (_MULTIMODAL_TOOL_CONTENT_PATTERNS, _V_MULTIMODAL), (_IMAGE_CORRUPT_PATTERNS, _V_IMAGE_CORRUPT),
    (_IMAGE_TOO_LARGE_PATTERNS, _V_IMAGE_TOO_LARGE),
)

_OVERFLOW_AS_5XX_RULES = (
    (_EMPTY_PROVIDER_RESPONSE_PATTERNS, _V_SERVER_ERROR), (_CONTEXT_OVERFLOW_PATTERNS, _V_CONTEXT_OVERFLOW),
)

_404_RULES = (
    (_BILLING_PATTERNS, _V_BILLING), (_PROVIDER_POLICY_BLOCKED_PATTERNS, _V_POLICY_BLOCKED),
    (_MODEL_NOT_FOUND_PATTERNS, _V_MODEL_NOT_FOUND),
)

_400_TAIL_RULES = _OVERFLOW_AS_5XX_RULES + (
    (_PROVIDER_POLICY_BLOCKED_PATTERNS, _V_POLICY_BLOCKED), (_MODEL_NOT_FOUND_PATTERNS, _V_MODEL_NOT_FOUND),
    (_RATE_LIMIT_PATTERNS, _V_RATE_LIMIT), (_BILLING_PATTERNS, _billing_hints),
)

_MESSAGE_HEAD_RULES = ((_PAYLOAD_TOO_LARGE_PATTERNS, _V_PAYLOAD_TOO_LARGE),) + _IMAGE_TOOL_RULES

_MESSAGE_TAIL_RULES = (
    (_OVERLOADED_PATTERNS, _V_OVERLOADED), (_BILLING_PATTERNS, _billing_hints),
    (_RATE_LIMIT_PATTERNS, _V_RATE_LIMIT), (_EMPTY_PROVIDER_RESPONSE_PATTERNS, _V_SERVER_ERROR),
    (_CONTEXT_OVERFLOW_PATTERNS, _V_CONTEXT_OVERFLOW), (_AUTH_PATTERNS, _V_AUTH_ROTATE),
    (_PROVIDER_POLICY_BLOCKED_PATTERNS, _V_POLICY_BLOCKED), (_MODEL_NOT_FOUND_PATTERNS, _V_MODEL_NOT_FOUND),
    (_TIMEOUT_MESSAGE_PATTERNS, _V_TIMEOUT), (_CONNECTION_MESSAGE_PATTERNS, _V_TIMEOUT),
)

_ERROR_CODE_VERDICTS: Dict[str, Verdict] = {
    **dict.fromkeys(("resource_exhausted", "throttled", "rate_limit_exceeded"),
                    _v(_R.rate_limit, should_rotate_credential=True)),
    **dict.fromkeys(_BILLING_ERROR_CODES, _V_BILLING),
    **dict.fromkeys(("model_not_found", "model_not_available", "invalid_model"), _V_MODEL_NOT_FOUND),
    **dict.fromkeys(("context_length_exceeded", "max_tokens_exceeded"), _V_CONTEXT_OVERFLOW),
    "invalid_encrypted_content": _V_INVALID_ENCRYPTED,
}

_400_VALIDATION_CODES = {"unknown_parameter", "unsupported_parameter"}
_5XX_VALIDATION_CODES = _400_VALIDATION_CODES | {"invalid_request_error"}
_400_VALIDATION_PATTERNS = tuple(p for p in _REQUEST_VALIDATION_PATTERNS if p != "invalid_request_error")



@dataclass
class _Ctx:
    """Everything the classifier stages need about one failed call."""

    error: Exception
    status_code: Optional[int]
    body: dict
    msg: str
    provider: str
    model: str
    approx_tokens: int
    context_length: int
    num_messages: int

    def __post_init__(self) -> None:
        self.error_type = type(self.error).__name__
        self.error_code = _extract_error_code(self.body)
        self.code = self.error_code.lower()
        self.headers = _from_cause_chain(self.error, _headers_of, {})
        self.provider_slug = (self.provider or "").strip().lower()
        self.model_slug = (self.model or "").strip().lower()

    def large_session(self, frac: float, tokens: int, messages: int) -> bool:
        """Absolute thresholds only proxy for smaller context windows."""
        return self.approx_tokens > self.context_length * frac or (
            self.context_length <= 256000 and (self.approx_tokens > tokens or self.num_messages > messages)
        )


def _plugin_verdict(c: _Ctx) -> Optional[Verdict]:
    """First valid plugin classification (runs before the built-in pipeline so a
    provider plugin can add or correct verdicts). invoke_hook isolates callback
    failures; this guard only covers import/dispatch failure."""
    try:
        from arkos_cli.plugins import get_plugin_error_classification
        verdict = get_plugin_error_classification(
            provider=c.provider, model=c.model, status_code=c.status_code, error_type=c.error_type,
            error_code=c.error_code, error_message=c.msg, error_body=c.body, error=c.error,
            approx_tokens=c.approx_tokens, context_length=c.context_length, num_messages=c.num_messages,
        )
    except Exception as exc:
        logger.debug("Plugin error classification unavailable: %s", exc)
        return None
    if verdict is not None:
        logger.info("API error classified by plugin hook: %s (provider=%s, status=%s)",
                    verdict["reason"].value, c.provider, c.status_code)
    return verdict


def _provider_special_cases(c: _Ctx) -> Optional[Verdict]:
    """Highest-priority provider-specific shapes that a status code would misroute."""
    msg, status = c.msg, c.status_code
    if any(p in msg for p in _CONTENT_POLICY_BLOCKED_PATTERNS):
        return _V_CONTENT_BLOCKED
    if _is_codex_masked_replay_rejection(c):
        return _v(_R.invalid_encrypted_content, **_ABORT_FALLBACK)
    if status == 400 and "thinking" in msg and any(p in msg for p in _THINKING_MUTATION_WORDS):
        return _v(_R.thinking_signature)
    if status == 429 and "extra usage" in msg and "long context" in msg:
        return _v(_R.long_context_tier, should_compress=True)
    if status == 400 and "long context beta" in msg and "not yet available" in msg:
        return _v(_R.oauth_long_context_beta_forbidden)
    grammar_hit = "error parsing grammar" in msg or "json-schema-to-grammar" in msg or (
        "unable to generate parser" in msg and "template" in msg
    )
    if status == 400 and grammar_hit and _NO_USER_QUERY_SIGNAL not in msg:
        return _v(_R.llama_cpp_grammar_pattern)
    if "do not have an active grok subscription" in msg or ("out of available resources" in msg and "grok" in msg):
        return _V_AUTH_FALLBACK
    return None


def _moa_special_cases(c: _Ctx) -> Optional[Verdict]:
    if c.provider_slug == "moa" and any(s in str(c.error) for s in _MOA_ADAPTER_SHAPE_BUGS):
        return _v(_R.format_error, retryable=False)
    from agent.errors import MoAPresetNotFoundError
    return _v(_R.model_not_found, retryable=False) if isinstance(c.error, MoAPresetNotFoundError) else None


def _by_error_code(c: _Ctx) -> Optional[Verdict]:
    """Structured error codes from the response body."""
    if c.code == PROVIDER_STREAM_NON_JSON_ERROR_CODE and "request validation failed:" in c.msg:
        return _V_FORMAT_ERROR
    return _ERROR_CODE_VERDICTS.get(c.code)


def _by_message(c: _Ctx) -> Optional[Verdict]:
    """Message patterns when no status code settled it; status-less usage
    limits get the same disambiguation as 402."""
    head = _first_match(c.msg, _MESSAGE_HEAD_RULES)
    if head is not None:
        return head
    usage_limit = any(p in c.msg for p in _USAGE_LIMIT_PATTERNS)
    return _classify_402(c.msg, dict) if usage_limit else _first_match(c.msg, _MESSAGE_TAIL_RULES)


def _by_transport(c: _Ctx) -> Optional[Verdict]:
    """SSL, disconnect, circuit-breaker and transport-type heuristics, in that order."""
    msg = c.msg
    ssl = _first_match(msg, ((_SSL_CERT_VERIFY_PATTERNS, _V_SSL_CERT), (_SSL_TRANSIENT_PATTERNS, _V_TIMEOUT)))
    if ssl is not None:
        return ssl
    if any(p in msg for p in _SERVER_DISCONNECT_PATTERNS) and not c.status_code:
        from agent.reasoning_timeouts import get_reasoning_stale_timeout_floor
        if get_reasoning_stale_timeout_floor(c.model) is not None:
            return _V_TIMEOUT
        return _V_CONTEXT_OVERFLOW if c.large_session(0.6, 120000, 200) else _V_TIMEOUT
    if c.error_type == "RuntimeError" and "consecutive stale attempts" in msg and "aborting this call" in msg:
        return _v(_R.timeout, **_ABORT_FALLBACK)
    transport = c.error_type in _TRANSPORT_ERROR_TYPES or isinstance(c.error, (TimeoutError, ConnectionError, OSError))
    return _V_TIMEOUT if transport else None


def _by_status(c: _Ctx) -> Optional[Verdict]:
    """HTTP status code with message-aware refinement (unlisted 4xx/5xx → generic)."""
    status = c.status_code
    if status is None:
        return None
    default = _V_FORMAT_ERROR if 400 <= status < 500 else _V_SERVER_ERROR if 500 <= status < 600 else None
    return _STATUS_HANDLERS[status](c) if status in _STATUS_HANDLERS else default


_STAGES: Sequence[Callable[[_Ctx], Optional[Verdict]]] = (
    _plugin_verdict, _provider_special_cases, _by_status, _moa_special_cases,
    _by_error_code, _by_message, _by_transport,
)


def classify_api_error(
    error: Exception, *, provider: str = "", model: str = "",
    approx_tokens: int = 0, context_length: int = 200000, num_messages: int = 0,
) -> ClassifiedError:
    """Classify an API error into a structured recovery recommendation (see ``_STAGES``)."""
    status_code = _extract_status_code(error)
    if status_code is None and type(error).__name__ == "RateLimitError":
        status_code = 429
    body = _extract_error_body(error)
    c = _Ctx(
        error, status_code, body, _build_error_msg(error, body), provider, model,
        approx_tokens, context_length, num_messages,
    )
    verdict = next((v for v in (stage(c) for stage in _STAGES) if v is not None), _V_UNKNOWN)
    base = {"status_code": status_code, "provider": provider, "model": model, "message": _extract_message(error, body)}
    return ClassifiedError(**{**base, **verdict})



def _status_403(c: _Ctx) -> Verdict:
    xai_spend = c.provider_slug == "xai-oauth" and c.code == _XAI_SPENDING_LIMIT_ERROR_CODE
    billing = xai_spend or any(p in c.msg for p in ("key limit exceeded", "spending limit") + _BILLING_PATTERNS)
    return _V_BILLING if billing else _V_AUTH_FALLBACK


def _status_404(c: _Ctx) -> Verdict:
    verdict = _first_match(c.msg, _404_RULES)
    if verdict is not None:
        return verdict
    return _V_MODEL_NOT_FOUND if _model_id_missing_known_prefix(c.model_slug, c.provider_slug) else _V_UNKNOWN


def _status_429(c: _Ctx) -> Verdict:
    if any(p in c.msg for p in _OVERLOADED_PATTERNS):
        return _V_OVERLOADED
    if _is_openrouter_upstream_error(c.body, c.provider_slug):
        upstream = _extract_upstream_provider_name(c.body)
        ctx = {"upstream_provider": upstream} if upstream else {}
        return _v(_R.upstream_rate_limit, should_fallback=True, error_context=ctx)
    quota_wall = c.code == "usage_limit_reached" or any(
        p in c.msg for p in ("usage_limit_reached",) + _USAGE_LIMIT_PATTERNS + _BILLING_PATTERNS
    )
    explicit_rate_limit = any(p in c.msg for p in _RATE_LIMIT_PATTERNS)
    if quota_wall and not explicit_rate_limit and not _has_usage_limit_transient_signal(c.msg, c.body, c.headers):
        return _V_BILLING
    return _V_RATE_LIMIT


def _status_5xx(c: _Ctx) -> Verdict:
    validation = any(p in c.msg for p in _REQUEST_VALIDATION_PATTERNS) or c.code in _5XX_VALIDATION_CODES
    if validation and not _is_server_injected_param_rejection(c.msg, c.provider_slug):
        return _V_FORMAT_ERROR
    return _first_match(c.msg, _OVERFLOW_AS_5XX_RULES) or _V_SERVER_ERROR


def _classify_402(error_msg: str, result_fn: Callable[..., Any]) -> Any:
    """Disambiguate 402: "usage limit, try again in 5 minutes" is a periodic quota, not billing."""
    transient = any(p in error_msg for p in _USAGE_LIMIT_PATTERNS) and any(
        p in error_msg for p in _USAGE_LIMIT_TRANSIENT_SIGNALS
    )
    return result_fn(**(_V_RATE_LIMIT if transient else _V_BILLING))


def _classify_400(c: _Ctx) -> Verdict:
    """400 Bad Request — image/tool shapes, request-shape rejections, overflow, or generic."""
    msg, code = c.msg, c.code
    verdict = _first_match(msg, _IMAGE_TOOL_RULES)
    if verdict is not None:
        return verdict
    if code == "invalid_encrypted_content" or "invalid_encrypted_content" in msg or (
        "encrypted content for item" in msg and "could not be verified" in msg
    ) or "could not decrypt the provided encrypted_content" in msg:
        return _V_INVALID_ENCRYPTED
    if _REASONING_MANDATORY_PATTERN in msg:
        return _V_REASONING_MANDATORY
    if _is_server_injected_param_rejection(msg, c.provider_slug):
        return _V_SERVER_ERROR
    if any(p in msg for p in _400_VALIDATION_PATTERNS) or code in _400_VALIDATION_CODES:
        return _V_FORMAT_ERROR
    if any(p in msg for p in _INVALID_MESSAGE_BODY_PATTERNS) or code == "invalid_request_body":
        logger.warning(
            "Malformed message array 400 (invalid request body) classified as format_error, NOT context "
            "overflow — failing fast + falling back instead of entering the compression loop. This usually "
            "means an empty-content assistant stub is in the transcript; num_messages=%s approx_tokens=%s. "
            "error=%.200s", c.num_messages, c.approx_tokens, msg,
        )
        return _V_FORMAT_ERROR
    verdict = _first_match(msg, _400_TAIL_RULES)
    if verdict is not None:
        return verdict
    body_msg = next((m for m in (str(x or "").strip().lower() for x in _body_message_candidates(c.body)) if m), "")
    is_generic = len(body_msg) < 30 or body_msg in {"error", ""}
    if is_generic and c.large_session(0.4, 80000, 80):
        return _V_CONTEXT_OVERFLOW
    return _V_FORMAT_ERROR


_STATUS_HANDLERS: Dict[int, Callable[[_Ctx], Verdict]] = {
    400: _classify_400, 401: lambda c: _V_AUTH_ROTATE, 402: lambda c: _classify_402(c.msg, dict),
    403: _status_403, 404: _status_404, 408: lambda c: _V_TIMEOUT, 413: lambda c: _V_PAYLOAD_TOO_LARGE,
    429: _status_429, 500: _status_5xx, 502: _status_5xx,
    503: lambda c: _first_match(c.msg, _OVERFLOW_AS_5XX_RULES) or _V_OVERLOADED,
    529: lambda c: _first_match(c.msg, _OVERFLOW_AS_5XX_RULES) or _V_OVERLOADED,
}



_RESET_FIELDS = ("resets_in_seconds", "resets_at", "reset_at", "retry_after")
_RESET_HEADERS = ("retry-after", "Retry-After", "x-ratelimit-reset", "X-RateLimit-Reset")


def _has_usage_limit_transient_signal(error_msg: str, body: dict, response_headers) -> bool:
    """Whether a usage-limit response identifies a reset window (message, body fields, or headers)."""
    if any(pattern in error_msg for pattern in _USAGE_LIMIT_TRANSIENT_SIGNALS):
        return True
    payloads = [p for p in (body, _error_obj(body)) if isinstance(p, dict)]
    if any(payload.get(f) not in (None, "") for payload in payloads for f in _RESET_FIELDS):
        return True
    if response_headers and hasattr(response_headers, "get"):
        return any(response_headers.get(h) not in (None, "") for h in _RESET_HEADERS)
    return False


def _model_id_missing_known_prefix(model: str, provider: str) -> bool:
    """True when a bare model id is only known to the provider as ``vendor/id``.

    Never guesses: an id absent from the curated catalogue returns False so real
    endpoint problems keep their retryable ``unknown`` classification.
    """
    name = (model or "").strip()
    if not name or "/" in name:
        return False
    try:
        from arkos_cli.model_normalize import suggest_prefixed_model_id
        return bool(suggest_prefixed_model_id((provider or "").strip(), name))
    except Exception:
        return False


def _is_server_injected_param_rejection(error_msg: str, provider: str) -> bool:
    """True when a 400 blames a one-route-only parameter this route never sends.

    Conservative: known parameters only, and only when ``provider`` is not a
    sender, so a genuine bad parameter (``max_tokens`` on GPT-5) stays format_error.
    """
    provider_slug = (provider or "").strip().lower()
    for param, senders in _SERVER_INJECTED_PARAM_SENDERS.items():
        if error_msg and param in error_msg and any(w in error_msg for w in _PARAM_REJECTION_WORDS):
            return not any(sender in provider_slug for sender in senders)
    return False


_CODEX_MASKED_REPLAY_MESSAGE = "request blocked."


def _is_codex_masked_replay_rejection(c: "_Ctx") -> bool:
    """HTTP 400 / status-less ``{code: invalid_prompt, message: "Request blocked."}`` from
    ``openai-codex`` — as an SDK error body, a Responses ``error`` SSE frame, or the
    ``response.failed`` text ``"invalid_prompt: Request blocked."``."""
    if c.provider_slug != "openai-codex" or c.status_code not in (None, 400):
        return False
    body_msg = next((str(m).strip().lower() for m in _body_message_candidates(c.body or {}) if m), "")
    return (c.code == "invalid_prompt" and body_msg == _CODEX_MASKED_REPLAY_MESSAGE) or (
        c.msg.strip() == f"invalid_prompt: {_CODEX_MASKED_REPLAY_MESSAGE}"
    )


def _error_obj(body: Any) -> dict:
    """``body["error"]`` when it is a dict, else ``{}``."""
    err = body.get("error") if isinstance(body, dict) else None
    return err if isinstance(err, dict) else {}


def _json_dict(text: Any) -> Optional[dict]:
    """Parse a JSON object string; None for non-strings, blanks, invalid JSON or non-objects."""
    if not (isinstance(text, str) and text.strip()):
        return None
    try:
        inner = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    return inner if isinstance(inner, dict) else None


def _openrouter_wrapped_message(err_obj: dict) -> str:
    """Lowercased inner message from OpenRouter's ``error.metadata.raw`` JSON wrapper."""
    metadata = err_obj.get("metadata", {})
    inner = _json_dict(metadata.get("raw")) if isinstance(metadata, dict) else None
    return str(_error_obj(inner).get("message") or "").lower() if inner else ""


def _build_error_msg(error: Exception, body: Any) -> str:
    """Lowercased str(error) + body message + OpenRouter-wrapped upstream message
    (OpenAI SDK's APIStatusError.__str__ omits the body, so it is appended)."""
    raw_msg = str(error).lower()
    body_msg = metadata_msg = ""
    if isinstance(body, dict):
        err_obj = _error_obj(body)
        body_msg = str(err_obj.get("message") or "").lower() or str(body.get("message") or "").lower()
        metadata_msg = _openrouter_wrapped_message(err_obj) if err_obj else ""
    parts = [raw_msg]
    if body_msg and body_msg not in raw_msg:
        parts.append(body_msg)
    if metadata_msg and metadata_msg not in raw_msg and metadata_msg not in body_msg:
        parts.append(metadata_msg)
    return " ".join(parts)


def _body_message_candidates(body: dict) -> Iterator[Any]:
    """Body message fields in priority order (OpenAI, flat, litellm/Bedrock proxy shapes)."""
    yield _error_obj(body).get("message")
    yield body.get("message")
    yield body.get("errorMessage")
    args = body.get("errorArgs")
    yield args.get("reason") if isinstance(args, dict) else None


def _from_cause_chain(error: Exception, pick: Callable[[Any], Any], default: Any) -> Any:
    """First non-None ``pick(exc)`` over the error and its __cause__/__context__ chain (max 5 deep)."""
    current = error
    for _ in range(5):
        found = pick(current)
        if found is not None:
            return found
        cause = getattr(current, "__cause__", None) or getattr(current, "__context__", None)
        if cause is None or cause is current:
            break
        current = cause
    return default


def _status_of(exc: Any) -> Optional[int]:
    code = getattr(exc, "status_code", None)
    if isinstance(code, int):
        return code
    code = getattr(exc, "status", None)
    return code if isinstance(code, int) and 100 <= code < 600 else None


def _body_of(exc: Any) -> Optional[dict]:
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        return body
    response = getattr(exc, "response", None)
    try:
        json_body = response.json() if response is not None else None
    except Exception:
        return None
    return json_body if isinstance(json_body, dict) else None


def _headers_of(exc: Any) -> Any:
    headers = getattr(getattr(exc, "response", None), "headers", None)
    return headers if headers and hasattr(headers, "get") else None


def _extract_status_code(error: Exception) -> Optional[int]:
    """HTTP status code from the error or its cause chain."""
    return _from_cause_chain(error, _status_of, None)


def _extract_error_body(error: Exception) -> dict:
    """Structured error body from an SDK exception or its cause chain."""
    return _from_cause_chain(error, _body_of, {})


def _code_from_payload(payload: Any, top_keys: Sequence[str], peek_message: bool) -> str:
    """Code/type from ``payload.error`` or a top-level key; ``"400"`` is not a code.
    ``peek_message`` also parses a JSON ``error.message`` for a nested code
    (Responses API surfaces ``invalid_encrypted_content`` this way)."""
    if not isinstance(payload, dict):
        return ""
    error_obj = payload.get("error", {})
    if isinstance(error_obj, dict):
        code = error_obj.get("code") or error_obj.get("type") or ""
        if isinstance(code, str) and code.strip() and code.strip() != "400":
            return code.strip()
        message = error_obj.get("message")
        if peek_message and isinstance(message, str) and message.strip().startswith("{"):
            nested_code = _code_from_payload(_json_dict(message), ("code", "error_code"), False)
            if nested_code:
                return nested_code
    code = next((payload.get(k) for k in top_keys if payload.get(k)), "")
    text = str(code).strip() if isinstance(code, (str, int)) else ""
    return text if text and text != "400" else ""


def _extract_error_code(body: dict) -> str:
    """Extract an error code string from the response body."""
    return _code_from_payload(body, ("code", "error_code", "errorCode"), True) if body else ""


def _extract_message(error: Exception, body: dict) -> str:
    """Extract the most informative error message (structured body first)."""
    msg = next((m for m in _body_message_candidates(body or {}) if isinstance(m, str) and m.strip()), None)
    return (msg.strip() if msg else str(error))[:500]


def _is_openrouter_upstream_error(body: Any, provider: str) -> bool:
    """OpenRouter's "Provider returned error" wrapper: the key is healthy, the
    upstream failed, so credential rotation is the wrong recovery."""
    err = _error_obj(body)
    if str(err.get("message") or "").strip().lower() != "provider returned error":
        return False
    if (provider or "").strip().lower() == "openrouter":
        return True
    metadata = err.get("metadata")
    return isinstance(metadata, dict) and ("raw" in metadata or "provider_name" in metadata)


def _extract_upstream_provider_name(body: Any) -> Optional[str]:
    """Pull the upstream provider name out of OpenRouter's error metadata."""
    metadata = _error_obj(body).get("metadata")
    name = metadata.get("provider_name") if isinstance(metadata, dict) else None
    return name.strip() if isinstance(name, str) and name.strip() else None
