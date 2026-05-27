import asyncio
import sys


def test_configure_windows_selector_event_loop_policy_sets_selector_policy(monkeypatch):
    from app.core.windows_event_loop import configure_windows_selector_event_loop_policy

    class DummyPolicy:
        pass

    calls = []
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(asyncio, "WindowsSelectorEventLoopPolicy", DummyPolicy, raising=False)
    monkeypatch.setattr(asyncio, "set_event_loop_policy", lambda policy: calls.append(policy))

    configure_windows_selector_event_loop_policy()

    assert len(calls) == 1
    assert isinstance(calls[0], DummyPolicy)


def test_configure_windows_selector_event_loop_policy_noops_off_windows(monkeypatch):
    from app.core.windows_event_loop import configure_windows_selector_event_loop_policy

    calls = []
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(asyncio, "set_event_loop_policy", lambda policy: calls.append(policy))

    configure_windows_selector_event_loop_policy()

    assert calls == []


def test_windows_selector_event_loop_factory_returns_selector_loop(monkeypatch):
    from app.core.windows_event_loop import windows_selector_event_loop_factory

    monkeypatch.setattr(sys, "platform", "win32")

    loop = windows_selector_event_loop_factory()
    try:
        assert isinstance(loop, asyncio.SelectorEventLoop)
    finally:
        loop.close()
