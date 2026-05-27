from __future__ import annotations

import uvicorn

from app.config import config


def main() -> None:
    uvicorn.run(
        "app.main:app",
        host=config.host,
        port=config.port,
        loop="app.core.windows_event_loop:windows_selector_event_loop_factory",
    )


if __name__ == "__main__":
    main()
