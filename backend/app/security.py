"""Security utilities: credential encryption, input sanitization, rate limiting."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import time
from collections import defaultdict
from functools import wraps
from typing import Optional

from cryptography.fernet import Fernet
from fastapi import HTTPException, Request, status


# ── Credential Encryption ───────────────────────────────────────────

class CredentialEncryptor:
    """
    Encrypt/decrypt sensitive credentials (ESXi passwords, SNMP communities, etc.)
    using Fernet symmetric encryption (AES-128-CBC).
    
    The encryption key is derived from the SECRET_KEY in .env.
    """

    def __init__(self, secret_key: str):
        # Derive a 32-byte Fernet key from the secret using SHA-256
        raw_key = hashlib.sha256(secret_key.encode()).digest()
        # Fernet requires base64-encoded 32-byte key
        self._key = base64.urlsafe_b64encode(raw_key)
        self._fernet = Fernet(self._key)

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a string, returns base64-encoded ciphertext."""
        if not plaintext:
            return ""
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a base64-encoded ciphertext string."""
        if not ciphertext:
            return ""
        try:
            return self._fernet.decrypt(ciphertext.encode()).decode()
        except Exception:
            # If decryption fails, return empty (graceful degradation)
            return ""


def get_encryptor() -> CredentialEncryptor:
    """Factory — creates encryptor from app settings."""
    from app.config import get_settings
    settings = get_settings()
    return CredentialEncryptor(settings.secret_key)


# ── Input Validation / Sanitization ─────────────────────────────────

# Patterns for common injection attacks
SQL_INJECTION_PATTERNS = [
    r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|UNION|ALTER|CREATE|EXEC|EXECUTE)\b)",
    r"(--|;|/\*|\*/|xp_)",
]

XSS_PATTERNS = [
    r"<script[^>]*>",
    r"javascript:",
    r"on\w+\s*=",
]

# Valid patterns for common fields
HOSTNAME_PATTERN = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9\-_\.]{0,127}$')
IP_PATTERN = re.compile(
    r'^(\d{1,3}\.){3}\d{1,3}$|^([0-9a-fA-F:]+)$'
)
COMMUNITY_PATTERN = re.compile(r'^[a-zA-Z0-9\-_\.]{1,128}$')
TOKEN_PATTERN = re.compile(r'^[a-fA-F0-9]{64}$')


def sanitize_string(value: str, max_length: int = 256) -> str:
    """Basic string sanitization: trim, limit length, strip control chars."""
    if not value:
        return ""
    # Remove control characters except newline/tab
    cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', value.strip())
    return cleaned[:max_length]


def check_sql_injection(value: str) -> bool:
    """Returns True if SQL injection patterns detected."""
    for pattern in SQL_INJECTION_PATTERNS:
        if re.search(pattern, value, re.IGNORECASE):
            return True
    return False


def check_xss(value: str) -> bool:
    """Returns True if XSS patterns detected."""
    for pattern in XSS_PATTERNS:
        if re.search(pattern, value, re.IGNORECASE):
            return True
    return False


def validate_device_input(data: dict) -> list[str]:
    """Validate device creation/update input. Returns list of errors."""
    errors = []

    name = data.get("name", "")
    if not name or len(name) < 2:
        errors.append("Device name must be at least 2 characters")
    if len(name) > 128:
        errors.append("Device name max 128 characters")

    ip = data.get("ip_address", "")
    if ip and not IP_PATTERN.match(ip):
        errors.append(f"Invalid IP address format: {ip}")

    device_type = data.get("device_type", "")
    if device_type not in ("mikrotik", "esxi", "vm_guest"):
        errors.append(f"Invalid device type: {device_type}")

    # Check for injection in text fields
    for field in ("name", "location", "description", "snmp_community", "esxi_username"):
        val = data.get(field, "")
        if val and (check_sql_injection(val) or check_xss(val)):
            errors.append(f"Suspicious characters in {field}")

    poll_interval = data.get("poll_interval", 60)
    if not isinstance(poll_interval, int) or poll_interval < 10 or poll_interval > 3600:
        errors.append("Poll interval must be between 10 and 3600 seconds")

    return errors


# ── Rate Limiting (in-memory, per-IP) ───────────────────────────────

class RateLimiter:
    """
    Simple in-memory sliding window rate limiter.
    
    Usage:
        limiter = RateLimiter(max_requests=60, window_seconds=60)
        
        @limiter.limit
        async def my_endpoint(request: Request):
            ...
    """

    def __init__(self, max_requests: int = 60, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = defaultdict(list)

    def _cleanup(self, ip: str, now: float):
        """Remove expired entries for an IP."""
        cutoff = now - self.window_seconds
        self._requests[ip] = [t for t in self._requests[ip] if t > cutoff]

    def is_allowed(self, ip: str) -> tuple[bool, dict]:
        """Check if request is allowed. Returns (allowed, headers)."""
        now = time.time()
        self._cleanup(ip, now)
        timestamps = self._requests[ip]

        remaining = max(0, self.max_requests - len(timestamps))
        reset_time = int(timestamps[0] + self.window_seconds) if timestamps else int(now + self.window_seconds)

        headers = {
            "X-RateLimit-Limit": str(self.max_requests),
            "X-RateLimit-Remaining": str(remaining),
            "X-RateLimit-Reset": str(reset_time),
        }

        if len(timestamps) >= self.max_requests:
            return False, headers

        self._requests[ip].append(now)
        return True, headers

    def limit(self, max_requests: int | None = None, window_seconds: int | None = None):
        """Decorator for FastAPI endpoints."""
        _max = max_requests or self.max_requests
        _window = window_seconds or self.window_seconds

        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                # Find Request in args/kwargs
                request: Optional[Request] = kwargs.get("request")
                if not request:
                    for arg in args:
                        if isinstance(arg, Request):
                            request = arg
                            break

                if request:
                    ip = request.client.host if request.client else "unknown"
                    allowed, headers = self.is_allowed(ip)
                    if not allowed:
                        raise HTTPException(
                            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail="Rate limit exceeded. Try again later.",
                            headers={**headers, "Retry-After": str(_window)},
                        )
                return await func(*args, **kwargs)
            return wrapper
        return decorator


# Global rate limiter instances
auth_limiter = RateLimiter(max_requests=10, window_seconds=60)   # Strict for auth
api_limiter = RateLimiter(max_requests=120, window_seconds=60)    # General API
agent_limiter = RateLimiter(max_requests=300, window_seconds=60)  # Agent push (higher)


# ── Security Headers Middleware ─────────────────────────────────────

from starlette.middleware.base import BaseHTTPMiddleware

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; img-src 'self' data:;"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Remove server header
        if "server" in response.headers:
            del response.headers["server"]
        return response
