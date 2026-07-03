"""Main entry point."""

from hermetic_agent.api.app import create_app
from hermetic_agent.config.settings import get_settings

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
