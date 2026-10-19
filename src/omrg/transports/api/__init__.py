"""Optional local HTTP transport (``omrg web``).

The modules here need the ``web`` extra (FastAPI). This package file
imports nothing, so ``import omrg`` and the other commands never load the
web stack. Use :func:`omrg.transports.api.app.create_app` to build the app.
"""
