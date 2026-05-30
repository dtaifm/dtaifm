"""Tests for the `dtaifm teachers` diagnostics command and underlying helpers.

The HTTP client used by --check is injected as a FakeHttpClient so no real
network calls are made in CI.
"""

import json
from typing import Any


from dtaifm.cli import main
from dtaifm.teacher.diagnostics import (
    describe_all,
    describe_teacher,
    format_teachers_text,
)


class FakeHttpClient:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self._responses: dict[str, Any] = {}
        self._exception_for: dict[str, Exception] = {}

    def queue_response_for(self, url_substring: str, response: Any) -> None:
        self._responses[url_substring] = response

    def raise_for(self, url_substring: str, exc: Exception) -> None:
        self._exception_for[url_substring] = exc

    def get(self, url: str, *, headers=None):
        self.calls.append(url)
        for substring, exc in self._exception_for.items():
            if substring in url:
                raise exc
        for substring, response in self._responses.items():
            if substring in url:
                return response
        raise RuntimeError(f"FakeHttpClient: no queued response for {url}")

    def post_json(self, url, payload, *, headers=None):
        raise RuntimeError("diagnostics should not POST")


# ----------------------------------------------------------------------
# describe_teacher (single)
# ----------------------------------------------------------------------

def test_describe_teacher_mock_is_builtin():
    info = describe_teacher("mock")
    assert info["name"] == "mock"
    assert info["kind"] == "builtin"


def test_describe_teacher_anthropic_reports_required_env_and_extra():
    info = describe_teacher("anthropic")
    assert info["kind"] == "cloud_sdk"
    assert info["requires_env"] == "ANTHROPIC_API_KEY"
    assert info["requires_extra"] == "dtaifm[anthropic]"


def test_describe_teacher_openai_reports_required_env_and_extra():
    info = describe_teacher("openai")
    assert info["kind"] == "cloud_sdk"
    assert info["requires_env"] == "OPENAI_API_KEY"
    assert info["requires_extra"] == "dtaifm[openai]"


def test_describe_teacher_ollama_default_base_url(monkeypatch):
    monkeypatch.delenv("DTAIFM_OLLAMA_BASE_URL", raising=False)
    info = describe_teacher("ollama")
    assert info["kind"] == "local_http"
    assert info["base_url"] == "http://localhost:11434"
    assert info["base_url_env"] == "DTAIFM_OLLAMA_BASE_URL"


def test_describe_teacher_lemonade_env_override(monkeypatch):
    monkeypatch.setenv("DTAIFM_LEMONADE_BASE_URL", "http://192.0.2.10:13305/")
    info = describe_teacher("lemonade")
    # Trailing slash is normalized
    assert info["base_url"] == "http://192.0.2.10:13305"


# ----------------------------------------------------------------------
# describe_all (with and without --check)
# ----------------------------------------------------------------------

def test_describe_all_lists_every_registered_teacher():
    infos = describe_all()
    names = {i["name"] for i in infos}
    assert {"mock", "anthropic", "openai", "ollama", "lemonade"}.issubset(names)


def test_describe_all_without_check_does_not_use_http_client():
    client = FakeHttpClient()  # would raise if called
    describe_all(check=False, http_client=client)
    assert client.calls == []


def test_describe_all_check_pings_each_local_endpoint(monkeypatch):
    monkeypatch.delenv("DTAIFM_OLLAMA_BASE_URL", raising=False)
    monkeypatch.delenv("DTAIFM_LEMONADE_BASE_URL", raising=False)
    client = FakeHttpClient()
    client.queue_response_for("/api/tags", {"models": [{"name": "llama3.2"}]})
    client.queue_response_for("/v1/models", {"data": [{"id": "Qwen3-0.6B-GGUF"}]})
    infos = describe_all(check=True, http_client=client)
    by_name = {i["name"]: i for i in infos}
    assert by_name["ollama"]["status"] == "reachable"
    assert by_name["ollama"]["models"] == ["llama3.2"]
    assert by_name["lemonade"]["status"] == "reachable"
    assert by_name["lemonade"]["models"] == ["Qwen3-0.6B-GGUF"]
    # Cloud and builtin teachers are NOT pinged
    assert by_name["mock"].get("status") == "registered"
    assert by_name["anthropic"].get("status") == "registered"
    assert by_name["openai"].get("status") == "registered"


def test_describe_all_check_reports_offline_gracefully():
    client = FakeHttpClient()
    client.raise_for("/api/tags", OSError("Connection refused"))
    client.raise_for("/v1/models", OSError("No route to host"))
    infos = describe_all(check=True, http_client=client)
    by_name = {i["name"]: i for i in infos}
    assert by_name["ollama"]["status"] == "offline"
    assert "Connection refused" in by_name["ollama"]["error"]
    assert by_name["lemonade"]["status"] == "offline"
    assert "No route" in by_name["lemonade"]["error"]


def test_describe_all_check_handles_non_json_response_gracefully():
    client = FakeHttpClient()
    client.raise_for("/api/tags", ValueError("HTTP GET ... returned non-JSON body"))
    client.queue_response_for("/v1/models", {"data": []})
    infos = describe_all(check=True, http_client=client)
    by_name = {i["name"]: i for i in infos}
    assert by_name["ollama"]["status"] == "offline"
    assert by_name["lemonade"]["status"] == "reachable"


def test_describe_all_check_uses_configured_base_url(monkeypatch):
    monkeypatch.setenv("DTAIFM_LEMONADE_BASE_URL", "http://192.0.2.10:13305")
    client = FakeHttpClient()
    client.queue_response_for("/api/tags", {"models": []})
    client.queue_response_for("192.0.2.10", {"data": []})
    describe_all(check=True, http_client=client)
    assert any("192.0.2.10:13305/v1/models" in url for url in client.calls)


# ----------------------------------------------------------------------
# format_teachers_text
# ----------------------------------------------------------------------

def test_format_teachers_text_lists_each_teacher():
    infos = describe_all()
    text = format_teachers_text(infos)
    for name in ("mock", "anthropic", "openai", "ollama", "lemonade"):
        assert name in text


def test_format_teachers_text_shows_local_endpoint_status(monkeypatch):
    monkeypatch.delenv("DTAIFM_OLLAMA_BASE_URL", raising=False)
    client = FakeHttpClient()
    client.queue_response_for("/api/tags", {"models": [{"name": "llama3.2"}]})
    client.queue_response_for("/v1/models", {"data": [{"id": "Qwen3-0.6B-GGUF"}]})
    infos = describe_all(check=True, http_client=client)
    text = format_teachers_text(infos)
    assert "reachable" in text
    assert "llama3.2" in text
    assert "Qwen3-0.6B-GGUF" in text


# ----------------------------------------------------------------------
# CLI: dtaifm teachers
# ----------------------------------------------------------------------

def test_cli_teachers_lists_every_teacher_without_check(capsys):
    exit_code = main(["teachers"])
    assert exit_code == 0
    out = capsys.readouterr().out
    for name in ("mock", "anthropic", "openai", "ollama", "lemonade"):
        assert name in out


def test_cli_teachers_json_output(capsys):
    exit_code = main(["teachers", "--json"])
    assert exit_code == 0
    infos = json.loads(capsys.readouterr().out)
    names = {i["name"] for i in infos}
    assert {"mock", "anthropic", "openai", "ollama", "lemonade"}.issubset(names)


def test_cli_teachers_check_with_offline_servers_exits_zero(monkeypatch, capsys):
    # Without injecting a client, --check uses the real HttpJsonClient. We don't
    # want a real network call in CI, so we monkeypatch the diagnostics check to
    # always report offline. The point of this test: --check must NOT crash even
    # when no server is reachable.
    from dtaifm.teacher import diagnostics

    def fake_check_local_endpoint(url, cfg, http_client):
        return {"status": "offline", "endpoint": url, "error": "(test) no server"}

    monkeypatch.setattr(diagnostics, "_check_local_endpoint", fake_check_local_endpoint)
    exit_code = main(["teachers", "--check"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "offline" in out
