"""Daemon package — long-running background processes.

This package contains processes that run independently of the
request-response transports (MCP, CLI). Currently houses the file
watcher; future daemons (queue workers, scheduled re-indexers) belong
here too.
"""
