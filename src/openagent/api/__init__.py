"""API module - REST API 层.

`create_app` builds the Sanic app; per-resource Blueprints live under
`api.controllers.*` and the shared Pydantic models in `api.schemas`.
"""

from openagent.api.app import create_app

__all__ = ["create_app"]
