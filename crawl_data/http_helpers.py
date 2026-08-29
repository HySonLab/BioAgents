from __future__ import annotations

import random
import time
from typing import Any

import requests


def request_with_retry(
    session: requests.Session,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    method: str = "GET",
    attempts: int = 5,
    base_wait: float = 10.0,
    cooldown_429: float = 900.0,
    timeout: tuple[float, float] = (20.0, 180.0),
) -> requests.Response:
    """Send a GET or POST request with retry and exponential backoff."""
    method = method.upper()
    if method not in {"GET", "POST"}:
        raise ValueError(f"Unsupported HTTP method: {method}")
    if attempts < 1:
        raise ValueError("attempts must be at least 1")

    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            if method == "POST":
                response = session.post(
                    url,
                    params=params,
                    data=data,
                    timeout=timeout,
                )
            else:
                response = session.get(
                    url,
                    params=params,
                    timeout=timeout,
                )

            if response.status_code == 429:
                try:
                    retry_after = float(response.headers.get("Retry-After", ""))
                except ValueError:
                    retry_after = 0.0
                wait = max(retry_after, float(cooldown_429))

            elif response.status_code in {500, 502, 503, 504}:
                wait = min(
                    1800.0,
                    float(base_wait) * (2 ** (attempt - 1))
                    + random.uniform(0.0, float(base_wait)),
                )

            else:
                response.raise_for_status()
                return response

            print(
                f"[HTTP {response.status_code}] attempt {attempt}/{attempts}; "
                f"waiting {wait:.0f}s",
                flush=True,
            )
            last_error = requests.HTTPError(
                f"HTTP {response.status_code}",
                response=response,
            )

            if attempt < attempts:
                time.sleep(wait)

        except (requests.ConnectionError, requests.Timeout) as error:
            wait = min(
                1800.0,
                float(base_wait) * (2 ** (attempt - 1))
                + random.uniform(0.0, float(base_wait)),
            )
            print(
                f"[NETWORK] attempt {attempt}/{attempts}; "
                f"waiting {wait:.0f}s",
                flush=True,
            )
            last_error = error

            if attempt < attempts:
                time.sleep(wait)

    raise last_error or RuntimeError("Request failed")
