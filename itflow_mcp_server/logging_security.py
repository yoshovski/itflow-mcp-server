"""Keep configured credentials out of application and dependency log output."""
from __future__ import annotations

import json
import logging
import os
from urllib.parse import quote, quote_plus


def credential_values() -> tuple[str, ...]:
    values = [os.environ.get(name, '') for name in (
        'ITFLOW_API_KEY', 'ITFLOW_API_KEY_PASSWORD', 'MCP_API_KEY'
    )]
    values.extend(os.environ.get('MCP_API_KEY', '').split(','))
    variants = set()
    for value in values:
        if value:
            variants.update((value, quote(value, safe=''), quote_plus(value),
                             json.dumps(value)[1:-1]))
    return tuple(sorted(variants, key=len, reverse=True))


class CredentialFormatter(logging.Formatter):
    """Redact after formatting, including exception and stack text."""
    def format(self, record: logging.LogRecord) -> str:
        output = super().format(record)
        for value in credential_values():
            output = output.replace(value, '[REDACTED]')
        return output


def configure_logging() -> None:
    level = os.environ.get('MCP_LOG_LEVEL', 'INFO').upper()
    handler = logging.StreamHandler()
    handler.setFormatter(CredentialFormatter(
        '%(asctime)s %(name)s %(levelname)s %(message)s'
    ))
    logging.basicConfig(level=getattr(logging, level, logging.INFO),
                        handlers=[handler], force=True)
    # These libraries log complete GET URLs (and DEBUG may include headers).
    for name in ('httpx', 'httpcore'):
        logging.getLogger(name).setLevel(logging.WARNING)
