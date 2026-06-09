"""Main entry point."""

from openagent.api.app import create_app
from openagent.config.settings import get_settings

if __name__ == "__main__":
    settings = get_settings()
    app = create_app(settings)

    app.run(
        host=settings.host,
        port=settings.port,
        workers=settings.workers,
        access_log=True,
        single_process=True,
    )
