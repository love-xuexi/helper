from __future__ import annotations

import asyncio
import selectors
import sys


def configure_windows_selector_event_loop_policy() -> None:
    if sys.platform != "win32":
        return

    selector_policy_factory = getattr(asyncio, "WindowsSelectorEventLoopPolicy", None)
    if selector_policy_factory is None:
        return

    asyncio.set_event_loop_policy(selector_policy_factory())


def windows_selector_event_loop_factory(use_subprocess: bool = False) -> asyncio.AbstractEventLoop:
    if sys.platform == "win32":
        return asyncio.SelectorEventLoop(selectors.SelectSelector())

    return asyncio.new_event_loop()
