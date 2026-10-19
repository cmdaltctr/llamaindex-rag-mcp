"""The sse-starlette shutdown flag must not leak from one test to the next.

``sse_starlette.sse.AppStatus.should_exit`` is process-wide and never resets.
A test that calls uvicorn's ``handle_exit`` sets it, and every later streamed
response in the same process then ends at once. The autouse fixture in
``conftest.py`` resets it. These two tests run in file order (``--dist
loadfile``): the first leaks the flag, the second proves it was cleared.
"""

from __future__ import annotations

from sse_starlette.sse import AppStatus


def test_a_test_may_set_the_shutdown_flag() -> None:
    AppStatus.should_exit = True


def test_the_next_test_starts_with_the_flag_cleared() -> None:
    assert AppStatus.should_exit is False
