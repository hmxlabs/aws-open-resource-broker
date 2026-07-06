"""Reflex configuration for the ORB UI (packaged copy).

This file ships inside the ``orb`` wheel at ``orb/ui/rxconfig.py`` so that
``reflex run`` can find it when the package is installed from PyPI.  The
embedded-UI runtime (``run_embedded_foreground``) sets ``cwd`` to the
directory that contains this file before exec-ing ``reflex run``.

A thin re-export at the repository root (``rxconfig.py``) delegates here so
that ``reflex run`` from the repo root continues to work for local
development.

Note: ``reflex`` is an optional dependency (the ``[ui]`` extra).  This
module must remain importable even when reflex is not installed so that
pyright and other static-analysis passes that run without the UI extra do
not raise ImportError.  The ``rx.Config`` block is only evaluated when
reflex is actually importable (i.e. at runtime with the [ui] extra or under
``reflex run``).

## Port configuration

``ORB_UI_BACKEND_PORT`` controls which port the Reflex backend binds to:

* **embedded mode** — ``run_embedded_foreground`` sets this to
  ``server_config.port`` (default 8000) before spawning the Reflex process.
  Reflex's backend IS the main server port; it serves the SPA, WebSocket
  state sync (``/_event``), and ORB's FastAPI (``/orb/*``) via
  ``api_transformer`` — all on one port.
* **split mode** — set to ``ui_config.backend_port`` (default 8001).
  The ORB FastAPI lives in a separate uvicorn process on ``server_config.port``.
* **dev mode** — defaults to 8001 (``ORB_UI_BACKEND_PORT`` env var).
* **standalone ``reflex run``** — falls back to the default (8001).

``ORB_UI_FRONTEND_PORT`` is only relevant in dev mode (Reflex's Bun frontend
dev server).  In production (``--env prod``) there is no separate frontend
process — the compiled bundle is served by the backend directly.
"""

from __future__ import annotations

import os

# These ports are overridden by run_embedded_foreground via environment
# variables before the Reflex process starts.  The defaults here are used
# when running ``reflex run`` directly and — critically — when
# ``reflex export`` runs during ``make ui-build`` to produce the SPA
# bundle that ships in the wheel.
#
# Reflex bakes ``api_url = f"http://localhost:{backend_port}"`` into the
# compiled JS at export time.  The client-side ``getBackendURL`` in the
# bundle rewrites the *hostname* to ``window.location.hostname`` when
# the baked URL is a same-domain hostname (localhost / 0.0.0.0) but it
# does NOT rewrite the port.  So the port that this rxconfig picks at
# build time is the port every deployed SPA will try to reach for
# ``/_event``, ``/_upload``, ``/ping`` and SSE — regardless of what
# port the running Reflex process is actually bound to.
#
# Embedded mode (the default deployment) binds Reflex to
# ``server_config.port`` which is 8000 out of the box.  Match that here
# so the shipped bundle works against a default install without any
# post-build rewrite.  Split-mode operators who bind Reflex to a
# different port must rebuild the bundle with
# ``ORB_UI_BACKEND_PORT=<their-port> make ui-build``.
_ORB_UI_BACKEND_PORT = int(os.getenv("ORB_UI_BACKEND_PORT", "8000"))

# ``ORB_UI_FRONTEND_PORT`` is only wired in dev mode (Reflex's Bun frontend
# dev server).  In prod backend-only, Reflex rejects any user-supplied
# ``frontend_port`` (config or CLI) — so we only surface the setting when
# the env var is explicitly set (dev mode wires it, prod does not).
_frontend_port_env = os.getenv("ORB_UI_FRONTEND_PORT")

try:
    import reflex as rx  # pyright: ignore[reportMissingImports]

    _plugins = [
        rx.plugins.SitemapPlugin(),
        rx.plugins.TailwindV4Plugin(),
        rx.plugins.RadixThemesPlugin(
            theme=rx.theme(appearance="light", accent_color="blue", radius="medium"),
        ),
    ]

    # Reflex resolves the app via ``app_module_import``; it imports
    # ``orb.ui.app`` and looks for a top-level ``app`` (rx.App instance).
    # ``app_name`` must match ^[a-zA-Z][a-zA-Z0-9_]*$ (Reflex requirement).
    # ``show_built_with_reflex=False`` hides the branding link.
    #
    # ``api_url=""`` makes Reflex bake *relative* URLs into the compiled
    # SPA bundle (``/_event``, ``/ping``, ``/_upload`` etc.) instead of
    # ``http://localhost:{backend_port}``.  The browser then resolves
    # every endpoint against ``window.location.origin``, so a single
    # bundle works across every deployment topology without rebuild:
    #
    #   * embedded — Reflex on server_config.port (8000)
    #   * split    — Reflex on ui_config.backend_port (8001); ORB REST
    #                lives on server_config.port (8000) and is reached
    #                separately via api_http (loopback)
    #   * dev      — reflex run with Bun frontend proxying to backend
    #   * HA/LB    — any worker on any port behind a load balancer
    #
    # Without this, the port that happened to be set in ``rxconfig`` at
    # ``reflex export`` time gets frozen into the JS bundle, and any
    # deployment mode that runs on a different port produces broken
    # WebSocket / SSE requests to the baked-in port.
    if _frontend_port_env is None:
        config = rx.Config(
            app_name="orb_ui",
            app_module_import="orb.ui.app",
            backend_port=_ORB_UI_BACKEND_PORT,
            show_built_with_reflex=False,
            plugins=_plugins,
        )
    else:
        config = rx.Config(
            app_name="orb_ui",
            app_module_import="orb.ui.app",
            backend_port=_ORB_UI_BACKEND_PORT,
            frontend_port=int(_frontend_port_env),
            show_built_with_reflex=False,
            plugins=_plugins,
        )
except ImportError:
    # reflex is not installed (CI lane without the [ui] extra, pyright, etc.).
    # ``config`` is left undefined; this file is only executed at runtime by
    # ``reflex run`` which requires the [ui] extra to be present.
    pass
