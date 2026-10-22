"""Optional local HTTP transport (``omrs web``).

The modules here need the ``web`` extra (FastAPI). This package file
imports nothing, so ``import omrs`` and the other commands never load the
web stack. Use :func:`omrs.transports.api.app.create_app` to build the app.
"""
