"""Compatibility helpers for third-party libraries."""

from __future__ import annotations

import inspect

import httpx


def ensure_httpx_proxy_support() -> None:
    """Patch httpx.Client to accept the deprecated ``proxy`` kwarg.

    Some dependencies (e.g. Supabase's Python SDK) still call
    ``httpx.Client(proxy=...)``. Recent httpx versions removed that argument in
    favour of ``proxies``. This shim preserves backwards compatibility without
    forcing the project to pin an older httpx release.
    """

    signature = inspect.signature(httpx.Client.__init__)
    if "proxy" in signature.parameters:
        return

    original_init = httpx.Client.__init__

    def patched_init(self, *args, proxy=None, **kwargs):  # type: ignore[override]
        if proxy is not None and "proxies" not in kwargs:
            kwargs["proxies"] = proxy
        original_init(self, *args, **kwargs)

    httpx.Client.__init__ = patched_init


__all__ = ["ensure_httpx_proxy_support"]
