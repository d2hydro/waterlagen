"""Shared validated Overpass requests and optional offline JSON caching."""

import json
import time
from pathlib import Path
from typing import Any

import requests

from waterlagen.logger import get_logger

logger = get_logger(__name__)
OVERPASS_ENDPOINT = "https://overpass-api.de/api/interpreter"


def _validate_response(payload: object, description: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise TypeError(f"Overpass-{description} is geen JSON-object.")
    if payload.get("remark"):
        raise ValueError(f"Overpass-{description} is onvolledig: {payload['remark']}")
    if not isinstance(payload.get("elements"), list):
        raise TypeError(f"Overpass-{description} bevat geen elementenlijst.")
    return payload


def _read_overpass(
    query: str,
    description: str,
    *,
    endpoint: str,
    cache_dir: Path | None,
    offline: bool,
    timeout: float,
) -> dict[str, Any]:
    cache_path = cache_dir / f"{description}.json" if cache_dir else None
    if offline:
        if cache_path is None:
            raise ValueError("Offline gebruik vereist een cachemap.")
        logger.info("Hergebruik OSM-%s uit %s", description, cache_path)
        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"OSM-cache ontbreekt of is ongeldig: {cache_path}"
            ) from exc
        return _validate_response(payload, description)

    logger.info("Ophalen OSM-%s via Overpass", description)
    for attempt in range(3):
        try:
            response = requests.post(
                endpoint,
                data={"data": query},
                headers={
                    "User-Agent": "waterlagen/OSM",
                    "Accept": "application/json",
                },
                timeout=timeout,
            )
            response.raise_for_status()
            payload = response.json()
            break
        except (requests.RequestException, requests.exceptions.JSONDecodeError) as exc:
            retryable = isinstance(exc, requests.RequestException) and (
                not isinstance(exc, requests.HTTPError)
                or exc.response is not None
                and exc.response.status_code in {406, 429, 500, 502, 503, 504}
            )
            if not retryable or attempt == 2:
                raise RuntimeError(f"OSM-{description} ophalen mislukt: {exc}") from exc
            delay = 30 * (attempt + 1)
            logger.warning(
                "Overpass tijdelijk niet bereikbaar; opnieuw over %s s", delay
            )
            time.sleep(delay)
    result = _validate_response(payload, description)
    if cache_path is not None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = cache_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
        temporary.replace(cache_path)
    return result
