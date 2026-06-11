import httpx
import pytest
from bilibili_api.exceptions import ApiException

from bili_stalker_mcp.observability import begin_request, snapshot_metrics
from bili_stalker_mcp.retry import RetryableBiliApiError, with_retry


@pytest.mark.asyncio
async def test_retry_policy_does_not_sleep_before_first_attempt(monkeypatch):
    sleep_calls = []

    async def fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    monkeypatch.setattr("bili_stalker_mcp.retry.asyncio.sleep", fake_sleep)

    @with_retry(max_retries=2, base_delay=0.01)
    async def always_ok():
        return "ok"

    result = await always_ok()

    assert result == "ok"
    assert sleep_calls == []


@pytest.mark.asyncio
async def test_retry_policy_retries_request_error(monkeypatch):
    sleep_calls = []
    attempts = {"count": 0}

    async def fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    monkeypatch.setattr("bili_stalker_mcp.retry.asyncio.sleep", fake_sleep)
    begin_request("retry-request-error")

    request = httpx.Request("GET", "https://example.com")

    @with_retry(max_retries=2, base_delay=0.01)
    async def flaky():
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise httpx.RequestError("network down", request=request)
        return "ok"

    result = await flaky()

    assert result == "ok"
    assert attempts["count"] == 2
    assert len(sleep_calls) == 1
    assert snapshot_metrics()["retry_count"] == 1


@pytest.mark.asyncio
async def test_retry_policy_retries_known_api_error(monkeypatch):
    sleep_calls = []
    attempts = {"count": 0}

    async def fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    monkeypatch.setattr("bili_stalker_mcp.retry.asyncio.sleep", fake_sleep)
    begin_request("retry-api-error")

    @with_retry(max_retries=2, base_delay=0.01)
    async def flaky_api():
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise ApiException({"code": -412, "message": "blocked"})
        return "ok"

    result = await flaky_api()

    assert result == "ok"
    assert attempts["count"] == 2
    assert len(sleep_calls) == 1
    assert snapshot_metrics()["retry_count"] == 1


@pytest.mark.asyncio
async def test_retry_policy_retries_retryable_http_status(monkeypatch):
    sleep_calls = []
    attempts = {"count": 0}

    async def fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    monkeypatch.setattr("bili_stalker_mcp.retry.asyncio.sleep", fake_sleep)
    begin_request("retry-http-status")

    request = httpx.Request("GET", "https://example.com")
    response = httpx.Response(status_code=429, request=request)

    @with_retry(max_retries=2, base_delay=0.01)
    async def flaky_http():
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise httpx.HTTPStatusError(
                "too many requests", request=request, response=response
            )
        return "ok"

    result = await flaky_http()

    assert result == "ok"
    assert attempts["count"] == 2
    assert len(sleep_calls) == 1
    assert snapshot_metrics()["retry_count"] == 1


@pytest.mark.asyncio
async def test_retry_policy_does_not_retry_non_retryable_error(monkeypatch):
    sleep_calls = []

    async def fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    monkeypatch.setattr("bili_stalker_mcp.retry.asyncio.sleep", fake_sleep)

    @with_retry(max_retries=3, base_delay=0.01)
    async def fail_fast():
        raise ValueError("bad input")

    with pytest.raises(ValueError, match="bad input"):
        await fail_fast()

    assert sleep_calls == []


@pytest.mark.asyncio
async def test_empty_retryable_codes_disables_code_retries(monkeypatch):
    sleep_calls = []
    attempts = {"count": 0}

    async def fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    monkeypatch.setattr("bili_stalker_mcp.retry.asyncio.sleep", fake_sleep)

    @with_retry(max_retries=2, retryable_codes=set())
    async def fail_once():
        attempts["count"] += 1
        raise RetryableBiliApiError(-412, "blocked")

    with pytest.raises(RetryableBiliApiError):
        await fail_once()

    assert attempts["count"] == 1
    assert sleep_calls == []


@pytest.mark.asyncio
async def test_empty_retryable_exceptions_disables_transport_retries():
    attempts = {"count": 0}
    request = httpx.Request("GET", "https://example.com")

    @with_retry(max_retries=2, retryable_exceptions=())
    async def fail_once():
        attempts["count"] += 1
        raise httpx.RequestError("network down", request=request)

    with pytest.raises(httpx.RequestError):
        await fail_once()

    assert attempts["count"] == 1


@pytest.mark.asyncio
async def test_return_default_only_after_retry_exhaustion(monkeypatch):
    async def fake_sleep(delay: float) -> None:
        return None

    monkeypatch.setattr("bili_stalker_mcp.retry.asyncio.sleep", fake_sleep)

    @with_retry(
        max_retries=1,
        base_delay=0,
        return_default=True,
        default_on_exhaust="fallback",
    )
    async def retryable_failure():
        raise RetryableBiliApiError(-412, "blocked")

    @with_retry(return_default=True, default_on_exhaust="fallback")
    async def non_retryable_failure():
        raise ApiException({"code": -400, "message": "bad request"})

    assert await retryable_failure() == "fallback"
    with pytest.raises(ApiException):
        await non_retryable_failure()
