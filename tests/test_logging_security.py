"""Regression tests use dummy secrets only; no live service required."""
import io
import logging
import traceback
from urllib.parse import quote

import httpx
import pytest

from itflow_mcp_server.logging_security import CredentialFormatter, configure_logging
from itflow_mcp_server.itflow import ITFlowError
from tests.test_itflow import client_with


@pytest.mark.parametrize('kind', ['transport', 'http', 'api', 'html', 'auth'])
async def test_errors_do_not_expose_url_or_response_secrets(kind):
    secret = 'test-key'
    def handler(request):
        text = f'echo {request.url} password=test-pwd'
        if kind == 'transport':
            raise httpx.ConnectError(text, request=request)
        if kind == 'html':
            return httpx.Response(200, text=text)
        return httpx.Response(401 if kind == 'auth' else 500 if kind == 'http' else 200,
                              json={'success': 'False', 'message': text, 'data': [secret]})
    client = client_with(handler)
    try:
        with pytest.raises(ITFlowError) as caught:
            await client.read('clients')
        error = caught.value
        assert error.payload is None
        rendered = ''.join(traceback.format_exception(type(error), error, error.__traceback__))
        assert secret not in rendered
        assert 'test-pwd' not in rendered
        assert 'api_key=' not in rendered
    finally:
        await client.aclose()


def test_formatter_redacts_secrets_in_messages_and_tracebacks(monkeypatch):
    secret = 'dummy/secret+key'
    monkeypatch.setenv('ITFLOW_API_KEY', '  ' + secret + '  ')
    monkeypatch.setenv('ITFLOW_API_KEY_PASSWORD', 'dummy-password')
    monkeypatch.setenv('MCP_API_KEY', ' dummy-mcp-one , dummy-mcp-two ')
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(CredentialFormatter('%(message)s'))
    log = logging.Logger('isolated-test')
    log.addHandler(handler)
    try:
        raise RuntimeError(f'{secret} dummy-password dummy-mcp-one dummy-mcp-two')
    except RuntimeError:
        log.exception('URL api_key=%s', quote(secret, safe=''))
    text = stream.getvalue()
    for value in (secret, quote(secret, safe=''), 'dummy-password', 'dummy-mcp-one', 'dummy-mcp-two'):
        assert value not in text
    assert '[REDACTED]' in text


def test_http_libraries_stay_quiet_at_debug(monkeypatch):
    # Restore root handlers because pytest owns them.
    root = logging.getLogger()
    previous_handlers, previous_level = root.handlers[:], root.level
    previous_levels = {n: logging.getLogger(n).level for n in ('httpx', 'httpcore')}
    monkeypatch.setenv('MCP_LOG_LEVEL', 'DEBUG')
    try:
        configure_logging()
        for name in previous_levels:
            assert not logging.getLogger(name).isEnabledFor(logging.INFO)
            assert not logging.getLogger(name).isEnabledFor(logging.DEBUG)
    finally:
        root.handlers = previous_handlers
        root.setLevel(previous_level)
        for name, level in previous_levels.items():
            logging.getLogger(name).setLevel(level)
