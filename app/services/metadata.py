"""Build and serve pump.fun-compatible token metadata JSON."""

import json
import logging

logger = logging.getLogger(__name__)


def build_metadata(
    name: str,
    symbol: str,
    description: str = "",
    image: str = "",
) -> dict:
    """
    Build pump.fun-compatible metadata.
    The URI for this metadata will be served at GET /v1/metadata/<bot_id>.
    """
    return {
        "name": name,
        "symbol": symbol,
        "description": description or f"{name} — launched on Eve",
        "image": image,
        "showName": True,
        "createdOn": "https://pump.fun",
    }


def metadata_to_json(meta: dict) -> str:
    return json.dumps(meta, separators=(",", ":"))
