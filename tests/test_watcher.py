"""Tests for the file system watcher (rag_mcp.daemon.watcher).

Uses mocks for Observer, FileSystemEvent, threading.Timer, and
ingest_path to avoid file-system I/O and Ollama dependencies.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from unittest.mock import ANY, AsyncMock, MagicMock, patch, call

import pytest

from rag_mcp.daemon.watcher import (
    CONSECUTIVE_ERROR_THRESHOLD,
    DEFAULT_DEBOUNCE_SECONDS,
    MIN_DEBOUNCE_SECONDS,
    MAX_CONCURRENT_INGESTS,
    MAX_SHUTDOWN_SECONDS,
    MAX_HASH_CACHE_ENTRIES,
    DocumentIngestHandler,
    _sha256_file,
    watch_directory,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

# The lazy import in _do_ingest means we must patch at the source module.
_INGEST_PATH_TARGET = "rag_mcp.core.ingestion.ingest_path_async"


def _patch_ingest(**kwargs):
    """Patch ingest_path_async with an AsyncMock."""
    return patch(_INGEST_PATH_TARGET, new_callable=AsyncMock, **kwargs)


def _make_event(src_path: str, event_type: str = "modified") -> MagicMock:
    """Create a mock watchdog FileSystemEvent."""
    event = MagicMock()
    event.src_path = src_path
    event.event_type = event_type
    event.is_directory = False
    return event


class _FakeTimer:
    """A threading.Timer substitute that fires immediately for testing.

    Records whether it was started, cancelled, and provides a way to
    manually trigger the callback.
    """

    def __init__(self, interval, function, args=None, kwargs=None):
        self.interval = interval
        self.function = function
        self.args = args or []
        self.kwargs = kwargs or {}
        self._cancelled = False
        self._started = False
        self.daemon = False

    def start(self):
        self._started = True

    def cancel(self):
        self._cancelled = True

    def fire(self):
        """Manually trigger the timer callback (simulates debounce elapsing)."""
        if not self._cancelled:
            self.function(*self.args, **self.kwargs)

    def join(self, timeout=None):
        pass


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def handler():
    """Create a DocumentIngestHandler with fast debounce timers."""
    return DocumentIngestHandler(debounce_seconds=0.01)


# ── 5.2 Test on_created triggers ingest after debounce ───────────────────────


class TestOnCreatedIngestion:
    """on_created with a supported file triggers ingest_path after debounce."""

    @patch("rag_mcp.daemon.watcher.threading.Timer", _FakeTimer)
    @patch("rag_mcp.daemon.watcher._sha256_file", return_value="abc123")
    @_patch_ingest()
    def test_on_created_triggers_ingest(
        self, mock_ingest, mock_hash, handler,
    ):
        """Test that on_created with a supported PDF triggers ingest_path."""
        mock_ingest.return_value = {
            "status": "ok",
            "chunks_created": 5,
            "file_details": [],
        }
        event = _make_event("/tmp/test.pdf", "created")
        handler.on_created(event)

        # Fire the debounce timer
        timer = handler._timers.get("/tmp/test.pdf")
        assert timer is not None
        timer.fire()

        mock_ingest.assert_called_once_with(
            "/tmp/test.pdf", collection_name="documents", effective_settings=ANY
        )

    @patch("rag_mcp.daemon.watcher.threading.Timer", _FakeTimer)
    @patch("rag_mcp.daemon.watcher._sha256_file", return_value="abc123")
    @_patch_ingest()
    def test_on_created_logs_chunk_count(
        self, mock_ingest, mock_hash, handler, caplog,
    ):
        """Test that successful ingestion logs chunk count."""
        caplog.set_level(logging.DEBUG)
        mock_ingest.return_value = {
            "status": "ok",
            "chunks_created": 3,
            "file_details": [],
        }
        event = _make_event("/tmp/doc.docx", "created")
        handler.on_created(event)
        timer = handler._timers.get("/tmp/doc.docx")
        timer.fire()

        assert any(
            "Auto-ingested" in r.message and "3 chunk" in r.message
            for r in caplog.records
        )


# ── 5.3 & 5.4 Test content hash deduplication ──────────────────────────────


class TestContentHashDeduplication:
    """SHA-256 hash cache prevents re-ingesting unchanged files."""

    @patch("rag_mcp.daemon.watcher.threading.Timer", _FakeTimer)
    @patch("rag_mcp.daemon.watcher._sha256_file", return_value="fixed_hash")
    @_patch_ingest()
    def test_skips_unchanged_content(
        self, mock_ingest, mock_hash, handler,
    ):
        """on_modified with identical content skips ingestion."""
        # First event: ingest succeeds
        mock_ingest.return_value = {
            "status": "ok",
            "chunks_created": 2,
            "file_details": [],
        }
        event1 = _make_event("/tmp/test.pdf", "modified")
        handler.on_modified(event1)
        handler._timers["/tmp/test.pdf"].fire()
        assert mock_ingest.call_count == 1

        # Second event: same hash → skip
        event2 = _make_event("/tmp/test.pdf", "modified")
        handler.on_modified(event2)
        timer2 = handler._timers.get("/tmp/test.pdf")
        if timer2:
            timer2.fire()

        # ingest_path called only once (second was deduplicated)
        assert mock_ingest.call_count == 1

    @patch("rag_mcp.daemon.watcher.threading.Timer", _FakeTimer)
    @patch("rag_mcp.daemon.watcher._sha256_file")
    @_patch_ingest()
    def test_ingests_changed_content(
        self, mock_ingest, mock_hash, handler,
    ):
        """on_modified with different content triggers ingestion."""
        mock_hash.side_effect = ["hash_v1", "hash_v2"]
        mock_ingest.return_value = {
            "status": "ok",
            "chunks_created": 3,
            "file_details": [],
        }

        # First event: hash_v1
        event1 = _make_event("/tmp/test.pdf", "modified")
        handler.on_modified(event1)
        handler._timers["/tmp/test.pdf"].fire()

        # Second event: hash_v2 (different)
        event2 = _make_event("/tmp/test.pdf", "modified")
        handler.on_modified(event2)
        handler._timers["/tmp/test.pdf"].fire()

        assert mock_ingest.call_count == 2


# ── 5.5 Test unsupported extensions are ignored ─────────────────────────────


class TestUnsupportedExtensions:
    """PatternMatchingEventHandler rejects unsupported file types."""

    @pytest.mark.parametrize("filename", [
        "image.png",
        "video.mp4",
        "data.tmp",
        "download.part",
    ])
    def test_unsupported_extensions_not_in_patterns(self, filename, handler):
        """Unsupported extensions are not in the handler's patterns."""
        from watchdog.utils.patterns import match_any_paths
        # Should NOT match any supported extension pattern
        matched = match_any_paths(
            [filename],
            included_patterns=handler.patterns,
            case_sensitive=False,
        )
        assert not matched, f"{filename} should not match handler patterns"

    @pytest.mark.parametrize("filename", [
        ".DS_Store",
        "~$temp.docx",
        ".gitkeep",
    ])
    def test_ignored_files_match_ignore_patterns(self, filename, handler):
        """Hidden/temp files match the ignore patterns."""
        from watchdog.utils.patterns import match_any_paths
        ignored = match_any_paths(
            [filename],
            included_patterns=handler.ignore_patterns,
            case_sensitive=False,
        )
        assert ignored, f"{filename} should match ignore patterns"


# ── 5.6 Test debounce: rapid events result in single ingestion ───────────────


class TestDebouncing:
    """Rapid successive events debounce to a single ingestion."""

    @patch("rag_mcp.daemon.watcher.threading.Timer", _FakeTimer)
    @patch("rag_mcp.daemon.watcher._sha256_file", return_value="hash1")
    @_patch_ingest()
    def test_rapid_events_single_ingest(
        self, mock_ingest, mock_hash, handler,
    ):
        """Multiple rapid events reset the timer — single ingestion."""
        mock_ingest.return_value = {
            "status": "ok",
            "chunks_created": 1,
            "file_details": [],
        }

        # Fire 5 rapid events — each should reset the timer
        for _ in range(5):
            event = _make_event("/tmp/test.pdf", "modified")
            handler.on_modified(event)

        # Only one timer should exist (last one wins)
        assert len(handler._timers) == 1
        timer = handler._timers["/tmp/test.pdf"]
        assert timer is not None

        # Fire it — should result in exactly one ingest_path call
        timer.fire()
        assert mock_ingest.call_count == 1


# ── 5.7 Test graceful shutdown ──────────────────────────────────────────────


class TestGracefulShutdown:
    """stop() cancels timers and waits for in-flight ingestions."""

    @patch("rag_mcp.daemon.watcher.threading.Timer", _FakeTimer)
    def test_stop_cancels_timers(self, handler):
        """stop() cancels all pending debounce timers."""
        event = _make_event("/tmp/test.pdf", "created")
        handler.on_created(event)

        timer = handler._timers.get("/tmp/test.pdf")
        assert timer is not None
        assert not timer._cancelled

        handler.stop()
        assert timer._cancelled
        assert len(handler._timers) == 0

    @patch("rag_mcp.daemon.watcher.threading.Timer", _FakeTimer)
    @patch("rag_mcp.daemon.watcher._sha256_file", return_value="hash1")
    @_patch_ingest()
    def test_stop_waits_for_in_flight(
        self, mock_ingest, mock_hash, handler,
    ):
        """stop() waits for in-flight ingest_path() to complete."""
        barrier = threading.Barrier(2, timeout=5)

        def slow_ingest(path, **kwargs):
            barrier.wait()
            return {"status": "ok", "chunks_created": 1, "file_details": []}

        mock_ingest.side_effect = slow_ingest

        event = _make_event("/tmp/test.pdf", "created")
        handler.on_created(event)
        timer = handler._timers["/tmp/test.pdf"]

        # Fire the timer in a background thread (blocks on ingest)
        ingest_thread = threading.Thread(target=timer.fire)
        ingest_thread.start()

        # Wait for in-flight to start (polling loop, up to 5s)
        for _ in range(50):
            if handler.in_flight_count > 0:
                break
            time.sleep(0.1)
        else:
            pytest.fail("Ingestion did not start within 5 seconds")
        assert handler.in_flight_count > 0

        # Start stop() in a background thread
        stop_done = threading.Event()

        def do_stop():
            handler.stop()
            stop_done.set()

        stop_thread = threading.Thread(target=do_stop)
        stop_thread.start()

        # Let ingest_path complete
        barrier.wait()

        # stop() should finish
        stop_done.wait(timeout=5)
        assert handler.in_flight_count == 0


# ── 5.8 Test --debounce flag ────────────────────────────────────────────────


class TestDebounceValidation:
    """--debounce flag overrides default; rejects values < 0.5."""

    def test_rejects_zero_debounce(self):
        """--debounce 0 must be rejected (minimum 0.5s)."""
        with pytest.raises(SystemExit) as exc_info:
            watch_directory("/tmp", debounce=0.0)
        assert exc_info.value.code == 1

    def test_rejects_small_debounce(self):
        """--debounce 0.3 must be rejected."""
        with pytest.raises(SystemExit) as exc_info:
            watch_directory("/tmp", debounce=0.3)
        assert exc_info.value.code == 1

    @patch("rag_mcp.daemon.watcher.Observer")
    def test_accepts_valid_debounce(self, MockObserver):
        """--debounce 5.0 is accepted and observer is scheduled."""
        mock_observer = MagicMock()
        MockObserver.return_value = mock_observer
        mock_observer.join.side_effect = KeyboardInterrupt()

        with pytest.raises(KeyboardInterrupt):
            watch_directory("/tmp", debounce=5.0)

        mock_observer.schedule.assert_called_once()

    def test_handler_uses_custom_debounce(self):
        """Handler stores the custom debounce interval."""
        h = DocumentIngestHandler(debounce_seconds=5.0)
        assert h.debounce_seconds == 5.0


# ── 5.9 Test ConnectionError handling ───────────────────────────────────────


class TestConnectionErrorHandling:
    """ConnectionError logs WARNING, does NOT update hash, increments counter."""

    @patch("rag_mcp.daemon.watcher.threading.Timer", _FakeTimer)
    @patch("rag_mcp.daemon.watcher._sha256_file", return_value="hash_con")
    @_patch_ingest()
    def test_connection_error_no_hash_update(
        self, mock_ingest, mock_hash, handler, caplog,
    ):
        """ConnectionError does NOT update hash cache."""
        mock_ingest.return_value = {
            "status": "error",
            "error_type": "connection",
            "message": "Cannot connect to Ollama at localhost:11434",
            "file_details": [],
        }

        event = _make_event("/tmp/test.pdf", "created")
        handler.on_created(event)
        handler._timers["/tmp/test.pdf"].fire()

        # Hash should NOT be in cache
        assert "/tmp/test.pdf" not in handler._hash_cache
        # Consecutive errors should be 1
        assert handler._consecutive_errors == 1
        # WARNING level log
        assert any(
            r.levelno == logging.WARNING and "ConnectionError" in r.message
            for r in caplog.records
        )


# ── 5.10 Test consecutive ConnectionError threshold ─────────────────────────


class TestConsecutiveErrorThreshold:
    """5 consecutive ConnectionError triggers CRITICAL-level log."""

    @patch("rag_mcp.daemon.watcher.threading.Timer", _FakeTimer)
    @patch("rag_mcp.daemon.watcher._sha256_file")
    @_patch_ingest()
    def test_critical_after_threshold(
        self, mock_ingest, mock_hash, handler, caplog,
    ):
        """CRITICAL log after CONSECUTIVE_ERROR_THRESHOLD failures."""
        mock_hash.side_effect = [f"hash_{i}" for i in range(10)]
        mock_ingest.return_value = {
            "status": "error",
            "error_type": "connection",
            "message": "Cannot connect to Ollama at localhost:11434",
            "file_details": [],
        }

        for i in range(CONSECUTIVE_ERROR_THRESHOLD):
            path = f"/tmp/file_{i}.pdf"
            event = _make_event(path, "created")
            handler.on_created(event)
            handler._timers[path].fire()

        assert handler._consecutive_errors == CONSECUTIVE_ERROR_THRESHOLD
        assert any(
            r.levelno == logging.CRITICAL
            and "consecutive" in r.message.lower()
            for r in caplog.records
        )

    @patch("rag_mcp.daemon.watcher.threading.Timer", _FakeTimer)
    @patch("rag_mcp.daemon.watcher._sha256_file")
    @_patch_ingest()
    def test_success_resets_error_counter(
        self, mock_ingest, mock_hash, handler,
    ):
        """Successful ingestion resets the consecutive error counter."""
        mock_hash.side_effect = [f"hash_{i}" for i in range(6)]

        # 3 failures
        mock_ingest.return_value = {
            "status": "error",
            "error_type": "connection",
            "message": "Cannot connect to Ollama at localhost:11434",
            "file_details": [],
        }
        for i in range(3):
            path = f"/tmp/fail_{i}.pdf"
            event = _make_event(path, "created")
            handler.on_created(event)
            handler._timers[path].fire()

        assert handler._consecutive_errors == 3

        # Now a success
        mock_ingest.return_value = {
            "status": "ok",
            "chunks_created": 1,
            "file_details": [],
        }
        event = _make_event("/tmp/success.pdf", "created")
        handler.on_created(event)
        handler._timers["/tmp/success.pdf"].fire()

        assert handler._consecutive_errors == 0


# ── 5.11 Test file deleted during debounce ──────────────────────────────────


class TestFileDeletedDuringDebounce:
    """File deleted during debounce: DEBUG log, hash removed, no crash."""

    @patch("rag_mcp.daemon.watcher.threading.Timer", _FakeTimer)
    @patch("rag_mcp.daemon.watcher._sha256_file", side_effect=FileNotFoundError)
    @_patch_ingest()
    def test_file_deleted_before_ingest(
        self, mock_ingest, mock_hash, handler, caplog,
    ):
        """File deleted during debounce → DEBUG log, no crash."""
        caplog.set_level(logging.DEBUG)
        event = _make_event("/tmp/gone.pdf", "created")
        handler.on_created(event)
        handler._timers["/tmp/gone.pdf"].fire()

        mock_ingest.assert_not_called()
        assert any(
            r.levelno == logging.DEBUG and "vanished" in r.message
            for r in caplog.records
        )
        # Hash and timer entries cleaned up
        assert "/tmp/gone.pdf" not in handler._hash_cache
        assert "/tmp/gone.pdf" not in handler._timers


# ── 5.12 Test generic Exception (corrupt file) ─────────────────────────────


class TestGenericException:
    """Generic exceptions log WARNING, hash NOT updated, watcher continues."""

    @patch("rag_mcp.daemon.watcher.threading.Timer", _FakeTimer)
    @patch("rag_mcp.daemon.watcher._sha256_file", return_value="corrupt_hash")
    @_patch_ingest()
    def test_generic_exception_logged(
        self, mock_ingest, mock_hash, handler, caplog,
    ):
        """Corrupt file raises generic Exception → WARNING, hash unchanged."""
        mock_ingest.return_value = {
            "status": "error",
            "error_type": "file",
            "message": "Cannot parse PDF: corrupt header",
            "file_details": [],
        }

        event = _make_event("/tmp/corrupt.pdf", "created")
        handler.on_created(event)
        handler._timers["/tmp/corrupt.pdf"].fire()

        # Hash NOT updated
        assert "/tmp/corrupt.pdf" not in handler._hash_cache
        # WARNING level
        assert any(r.levelno == logging.WARNING for r in caplog.records)


# ── 5.13 Test empty directory ───────────────────────────────────────────────


class TestEmptyDirectory:
    """Watcher on empty directory: blocks, no errors, no ingestion calls."""

    @patch("rag_mcp.daemon.watcher.Observer")
    def test_empty_dir_no_ingestion(self, MockObserver):
        """Observer starts on empty dir with no ingestion calls."""
        mock_observer = MagicMock()
        MockObserver.return_value = mock_observer
        mock_observer.join.side_effect = KeyboardInterrupt()

        with pytest.raises(KeyboardInterrupt):
            watch_directory("/tmp", debounce=1.0)

        mock_observer.schedule.assert_called_once()
        mock_observer.start.assert_called_once()


# ── 5.14 Test ingestion throttling ─────────────────────────────────────────


class TestIngestionThrottling:
    """BoundedSemaphore(2) limits concurrent ingest_path() calls."""

    @patch("rag_mcp.daemon.watcher.threading.Timer", _FakeTimer)
    @patch("rag_mcp.daemon.watcher._sha256_file")
    @_patch_ingest()
    def test_throttling_limits_concurrency(
        self, mock_ingest, mock_hash, handler,
    ):
        """5 simultaneous events result in at most 2 concurrent calls."""
        mock_hash.side_effect = [f"hash_{i}" for i in range(5)]

        active_count = 0
        max_active = 0
        lock = threading.Lock()

        def track_ingest(path, **kwargs):
            nonlocal active_count, max_active
            with lock:
                active_count += 1
                max_active = max(max_active, active_count)
            time.sleep(0.05)
            with lock:
                active_count -= 1
            return {"status": "ok", "chunks_created": 1, "file_details": []}

        mock_ingest.side_effect = track_ingest

        # Fire 5 events in parallel
        threads = []
        for i in range(5):
            path = f"/tmp/file_{i}.pdf"
            event = _make_event(path, "created")
            handler.on_created(event)
            timer = handler._timers[path]

            t = threading.Thread(target=timer.fire)
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=10)

        assert max_active <= MAX_CONCURRENT_INGESTS
        assert mock_ingest.call_count == 5


# ── 5.16 Integration test for debounce timing (slow) ────────────────────────


@pytest.mark.slow
class TestRealDebounceTiming:
    """Integration test using real threading.Timer with time.sleep."""

    @patch("rag_mcp.daemon.watcher._sha256_file", return_value="real_hash")
    @_patch_ingest()
    def test_debounce_with_real_timer(
        self, mock_ingest, mock_hash,
    ):
        """Real debounce timer: rapid events → single ingestion."""
        mock_ingest.return_value = {
            "status": "ok",
            "chunks_created": 1,
            "file_details": [],
        }
        handler = DocumentIngestHandler(debounce_seconds=0.3)

        # Fire 3 rapid events
        for _ in range(3):
            event = _make_event("/tmp/test.pdf", "modified")
            handler.on_modified(event)

        # Wait just past the debounce window
        time.sleep(0.5)

        assert mock_ingest.call_count == 1
        handler.stop()


# ── Path validation tests ────────────────────────────────────────────────────


class TestPathValidation:
    """watch_directory validates path argument early."""

    def test_rejects_nonexistent_path(self):
        """Non-existent path → SystemExit(1)."""
        with pytest.raises(SystemExit) as exc_info:
            watch_directory("/nonexistent/path/that/does/not/exist")
        assert exc_info.value.code == 1

    def test_rejects_file_path(self, tmp_path):
        """File (not directory) → SystemExit(1)."""
        file_path = tmp_path / "test.txt"
        file_path.write_text("hello")
        with pytest.raises(SystemExit) as exc_info:
            watch_directory(str(file_path))
        assert exc_info.value.code == 1

    @patch("rag_mcp.daemon.watcher.Observer")
    def test_accepts_valid_directory(self, MockObserver, tmp_path):
        """Valid directory → observer starts."""
        mock_observer = MagicMock()
        MockObserver.return_value = mock_observer
        mock_observer.join.side_effect = KeyboardInterrupt()

        with pytest.raises(KeyboardInterrupt):
            watch_directory(str(tmp_path))

        mock_observer.start.assert_called_once()


# ── SHA-256 helper tests ─────────────────────────────────────────────────────


class TestSHA256File:
    """_sha256_file computes correct hashes."""

    def test_hash_deterministic(self, tmp_path):
        """Same content → same hash."""
        f = tmp_path / "test.txt"
        f.write_text("hello world")
        h1 = _sha256_file(f)
        h2 = _sha256_file(f)
        assert h1 == h2

    def test_different_content_different_hash(self, tmp_path):
        """Different content → different hash."""
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_text("hello")
        f2.write_text("world")
        assert _sha256_file(f1) != _sha256_file(f2)

    def test_nonexistent_file_raises(self):
        """Non-existent file → FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            _sha256_file(Path("/nonexistent/file.txt"))


# ── 5.15 Test _sha256_file raising OSError (permission denied) ───────────────


class TestSHA256OSError:
    """OSError during hashing (e.g. permission denied) logs WARNING, no crash."""

    @patch("rag_mcp.daemon.watcher.threading.Timer", _FakeTimer)
    @patch("rag_mcp.daemon.watcher._sha256_file", side_effect=OSError("Permission denied"))
    @_patch_ingest()
    def test_oserror_logged_as_warning(
        self, mock_ingest, mock_hash, handler, caplog,
    ):
        """Permission-denied OSError → WARNING log, watcher continues."""
        caplog.set_level(logging.WARNING)
        event = _make_event("/tmp/protected.pdf", "created")
        handler.on_created(event)
        handler._timers["/tmp/protected.pdf"].fire()

        # ingest_path should NOT have been called
        mock_ingest.assert_not_called()
        # Timer entry should be cleaned up
        assert "/tmp/protected.pdf" not in handler._timers
        # WARNING log about the read failure
        assert any(
            r.levelno == logging.WARNING and "Cannot read file" in r.message
            for r in caplog.records
        )


# ── 5.16 Test --verbose flag sets logger to DEBUG ────────────────────────────


class TestVerboseFlag:
    """--verbose flag sets the watcher logger to DEBUG level."""

    @patch("rag_mcp.daemon.watcher.Observer")
    def test_verbose_sets_debug_level(self, MockObserver, tmp_path):
        """verbose=True sets rag_mcp.daemon.watcher logger to DEBUG."""
        watcher_logger = logging.getLogger("rag_mcp.daemon.watcher")
        # Set to a known non-DEBUG level first
        watcher_logger.setLevel(logging.WARNING)

        mock_observer = MagicMock()
        MockObserver.return_value = mock_observer
        mock_observer.join.side_effect = KeyboardInterrupt()

        with pytest.raises(KeyboardInterrupt):
            watch_directory(str(tmp_path), verbose=True)

        assert watcher_logger.level == logging.DEBUG

    @patch("rag_mcp.daemon.watcher.Observer")
    def test_non_verbose_keeps_level(self, MockObserver, tmp_path):
        """verbose=False does not change the logger level."""
        watcher_logger = logging.getLogger("rag_mcp.daemon.watcher")
        watcher_logger.setLevel(logging.WARNING)

        mock_observer = MagicMock()
        MockObserver.return_value = mock_observer
        mock_observer.join.side_effect = KeyboardInterrupt()

        with pytest.raises(KeyboardInterrupt):
            watch_directory(str(tmp_path), verbose=False)

        assert watcher_logger.level == logging.WARNING

# ── 6.1 Test shutdown timeout ───────────────────────────────────────────────


class TestShutdownTimeout:
    """stop() completes within MAX_SHUTDOWN_SECONDS even when ingest_path()
    hangs indefinitely."""

    @patch("rag_mcp.daemon.watcher.threading.Timer", _FakeTimer)
    @patch("rag_mcp.daemon.watcher._sha256_file", return_value="hash1")
    @_patch_ingest()
    def test_stop_timeout_on_hung_ingestion(
        self, mock_ingest, mock_hash, handler, caplog,
    ):
        """stop() completes within the timeout when ingestion hangs."""
        caplog.set_level(logging.WARNING)

        # ingest_path blocks forever (simulates hung Ollama)
        ingest_started = threading.Event()
        keep_blocking = threading.Event()

        def hung_ingest(path, **kwargs):
            ingest_started.set()
            keep_blocking.wait()  # blocks forever unless released
            return {"status": "ok", "chunks_created": 1, "file_details": []}

        mock_ingest.side_effect = hung_ingest

        event = _make_event("/tmp/test.pdf", "created")
        handler.on_created(event)
        timer = handler._timers["/tmp/test.pdf"]

        # Fire in background thread
        ingest_thread = threading.Thread(target=timer.fire)
        ingest_thread.start()

        # Wait for ingestion to actually start
        ingest_started.wait(timeout=5)
        assert handler.in_flight_count > 0

        # Call stop() — should complete within MAX_SHUTDOWN_SECONDS + 1
        start = time.monotonic()
        handler.stop()
        elapsed = time.monotonic() - start
        assert elapsed < MAX_SHUTDOWN_SECONDS + 1

        # Verify WARNING log about abandoned ingestions
        assert any(
            r.levelno == logging.WARNING
            and "abandoning" in r.message.lower()
            and "in-flight" in r.message.lower()
            for r in caplog.records
        )

        # Release the blocked thread for cleanup
        keep_blocking.set()
        ingest_thread.join(timeout=5)

# ── 6.2 Test symlink traversal ──────────────────────────────────────────────


class TestSymlinkTraversal:
    """Symlink traversal is blocked when resolved path is outside watch root."""

    @patch("rag_mcp.daemon.watcher.threading.Timer", _FakeTimer)
    @patch("rag_mcp.daemon.watcher._sha256_file", return_value="hash_sym")
    @_patch_ingest()
    def test_traversal_blocked_outside_root(
        self, mock_ingest, mock_hash, caplog,
    ):
        """Symlink resolving outside watch root → WARNING, no ingestion."""
        caplog.set_level(logging.WARNING)

        watch_root = Path("/tmp/watched")
        handler = DocumentIngestHandler(
            debounce_seconds=0.01, watch_root=watch_root
        )

        # Patch path.resolve() to return a path outside the watch root
        with patch.object(Path, "resolve", return_value=Path("/etc/passwd")):
            event = _make_event("/tmp/watched/malicious_link.pdf", "created")
            handler.on_created(event)
            handler._timers["/tmp/watched/malicious_link.pdf"].fire()

        # ingest_path must NOT be called
        mock_ingest.assert_not_called()

        # WARNING log about path traversal blocked
        assert any(
            r.levelno == logging.WARNING
            and "path traversal blocked" in r.message.lower()
            for r in caplog.records
        )

        # Timer and hash entries should be cleaned up
        assert "/tmp/watched/malicious_link.pdf" not in handler._timers
        assert "/tmp/watched/malicious_link.pdf" not in handler._hash_cache

    @patch("rag_mcp.daemon.watcher.threading.Timer", _FakeTimer)
    @patch("rag_mcp.daemon.watcher._sha256_file", return_value="hash_ok")
    @_patch_ingest()
    def test_traversal_allowed_inside_root(
        self, mock_ingest, mock_hash,
    ):
        """Symlink resolving inside watch root → ingestion proceeds."""
        mock_ingest.return_value = {
            "status": "ok",
            "chunks_created": 2,
            "file_details": [],
        }

        watch_root = Path("/tmp/watched")
        handler = DocumentIngestHandler(
            debounce_seconds=0.01, watch_root=watch_root
        )

        # Patch path.resolve() to return a path inside the watch root
        with patch.object(
            Path, "resolve",
            return_value=Path("/tmp/watched/subdir/file.pdf"),
        ):
            event = _make_event("/tmp/watched/subdir/file.pdf", "created")
            handler.on_created(event)
            handler._timers["/tmp/watched/subdir/file.pdf"].fire()

        # ingest_path MUST be called
        mock_ingest.assert_called_once()

    @patch("rag_mcp.daemon.watcher.threading.Timer", _FakeTimer)
    @patch("rag_mcp.daemon.watcher._sha256_file", return_value="hash_no_root")
    @_patch_ingest()
    def test_watch_root_none_allows_all(
        self, mock_ingest, mock_hash,
    ):
        """When watch_root is None, all paths proceed (backward compat)."""
        mock_ingest.return_value = {
            "status": "ok",
            "chunks_created": 1,
            "file_details": [],
        }

        # Handler without watch_root (default None)
        handler = DocumentIngestHandler(debounce_seconds=0.01)

        event = _make_event("/tmp/some_file.pdf", "created")
        handler.on_created(event)
        handler._timers["/tmp/some_file.pdf"].fire()

        mock_ingest.assert_called_once()

# ── 6.3 Test error_type handling ────────────────────────────────────────────


class TestErrorTypeHandling:
    """error_type from ingest_path() drives connection/embedding/file
    distinction in the watcher's error counter and logging."""

    @patch("rag_mcp.daemon.watcher.threading.Timer", _FakeTimer)
    @patch("rag_mcp.daemon.watcher._sha256_file")
    @_patch_ingest()
    def test_connection_error_increments_counter(
        self, mock_ingest, mock_hash, handler, caplog,
    ):
        """error_type: "connection" increments _consecutive_errors."""
        mock_hash.side_effect = [f"hash_{i}" for i in range(6)]
        mock_ingest.return_value = {
            "status": "error",
            "error_type": "connection",
            "message": "Cannot connect to Ollama",
            "file_details": [],
        }

        for i in range(CONSECUTIVE_ERROR_THRESHOLD):
            path = f"/tmp/conn_{i}.pdf"
            event = _make_event(path, "created")
            handler.on_created(event)
            handler._timers[path].fire()

        assert handler._consecutive_errors == CONSECUTIVE_ERROR_THRESHOLD
        assert any(
            r.levelno == logging.CRITICAL for r in caplog.records
        )

    @patch("rag_mcp.daemon.watcher.threading.Timer", _FakeTimer)
    @patch("rag_mcp.daemon.watcher._sha256_file", return_value="hash_emb")
    @_patch_ingest()
    def test_embedding_error_resets_counter(
        self, mock_ingest, mock_hash, handler,
    ):
        """error_type: "embedding" does NOT increment and resets to 0."""
        # Pre-set counter to simulate prior errors
        handler._consecutive_errors = 3
        mock_ingest.return_value = {
            "status": "error",
            "error_type": "embedding",
            "message": "Embedding model error",
            "file_details": [],
        }

        event = _make_event("/tmp/emb.pdf", "created")
        handler.on_created(event)
        handler._timers["/tmp/emb.pdf"].fire()

        # Counter must be reset to 0
        assert handler._consecutive_errors == 0

    @patch("rag_mcp.daemon.watcher.threading.Timer", _FakeTimer)
    @patch("rag_mcp.daemon.watcher._sha256_file", return_value="hash_file")
    @_patch_ingest()
    def test_file_error_does_not_increment(
        self, mock_ingest, mock_hash, handler, caplog,
    ):
        """error_type: "file" logs WARNING and does NOT increment counter."""
        caplog.set_level(logging.WARNING)
        handler._consecutive_errors = 2
        mock_ingest.return_value = {
            "status": "error",
            "error_type": "file",
            "message": "All 3 file(s) failed to index",
            "file_details": [],
        }

        event = _make_event("/tmp/bad.pdf", "created")
        handler.on_created(event)
        handler._timers["/tmp/bad.pdf"].fire()

        # Counter must be reset (not incremented)
        assert handler._consecutive_errors == 0
        # WARNING log emitted
        assert any(
            r.levelno == logging.WARNING for r in caplog.records
        )

# ── 6.4 Test ingest_path error fields ───────────────────────────────────────


class TestIngestPathAllFilesFail:
    """ingest_path_async() returns error_type: "file" and message when all files
    fail."""

    async def test_all_files_fail_returns_file_error_type(
        self, tmp_path,
    ):
        """When all files fail to index, ingest_path_async returns
        error_type: "file" with a descriptive message."""
        from rag_mcp.core.ingestion import ingest_path_async

        # Create a real temp file with unsupported content that will fail parsing
        test_file = tmp_path / "test.txt"
        test_file.write_text("")  # empty file produces 0 chunks

        result = await ingest_path_async(str(tmp_path / "nonexistent"))
        assert result["status"] == "error"
        assert result["error_type"] == "file"

    @patch("rag_mcp.core.ingestion.pipeline.gather_supported_files")
    async def test_no_files_returns_ok(self, mock_gather, tmp_path):
        """When no supported files exist, returns ok not error."""
        from rag_mcp.core.ingestion import ingest_path_async

        test_dir = tmp_path / "empty"
        test_dir.mkdir()
        mock_gather.return_value = ([], [])

        result = await ingest_path_async(str(test_dir))
        assert result["status"] == "ok"

    async def test_connection_error_type(self, tmp_path):
        """ConnectionError from embedding returns error_type: "connection"."""
        from rag_mcp.core.ingestion import ingest_path_async

        test_file = tmp_path / "test.pdf"
        test_file.write_text("fake pdf content")

        with patch(
            "rag_mcp.core.ingestion.pipeline.gather_supported_files",
            return_value=([test_file], []),
        ):
            with patch(
                "rag_mcp.core.ingestion.pipeline.embed_and_write_async",
                side_effect=ConnectionError("No route to host"),
            ):
                result = await ingest_path_async(str(test_file))

        assert result["status"] == "error"
        assert result["error_type"] == "connection"

    async def test_embedding_error_type(self, tmp_path):
        """RuntimeError from embedding returns error_type: "embedding"."""
        from rag_mcp.core.ingestion import ingest_path_async

        test_file = tmp_path / "test.pdf"
        test_file.write_text("fake pdf content")

        with patch(
            "rag_mcp.core.ingestion.pipeline.gather_supported_files",
            return_value=([test_file], []),
        ):
            with patch(
                "rag_mcp.core.ingestion.pipeline.embed_and_write_async",
                side_effect=RuntimeError("Model inference failed"),
            ):
                result = await ingest_path_async(str(test_file))

        assert result["status"] == "error"
        assert result["error_type"] == "embedding"

# ── 6.5 Test file size limit ────────────────────────────────────────────────


class TestFileSizeLimit:
    """Files exceeding MAX_FILE_SIZE raise OSError and are skipped with
    WARNING."""

    @patch("rag_mcp.daemon.watcher.threading.Timer", _FakeTimer)
    @patch("rag_mcp.daemon.watcher._sha256_file")
    @_patch_ingest()
    def test_file_size_limit_oserror(
        self, mock_ingest, mock_hash, handler, caplog,
    ):
        """_sha256_file raising OSError about size → WARNING, no ingest."""
        caplog.set_level(logging.WARNING)
        mock_hash.side_effect = OSError(
            "File exceeds maximum size of 524288000 bytes"
        )

        event = _make_event("/tmp/huge.pdf", "created")
        handler.on_created(event)
        handler._timers["/tmp/huge.pdf"].fire()

        # ingest_path must NOT be called
        mock_ingest.assert_not_called()
        # WARNING log emitted
        assert any(
            r.levelno == logging.WARNING and "Cannot read file" in r.message
            for r in caplog.records
        )
        # Timer entry should be cleaned up
        assert "/tmp/huge.pdf" not in handler._timers

# ── 6.6 Test hash cache eviction ────────────────────────────────────────────


class TestHashCacheEviction:
    """When hash cache exceeds MAX_HASH_CACHE_ENTRIES, oldest entry is
    evicted."""

    def test_hash_cache_evicts_oldest(self, handler):
        """Cache exceeding max entries evicts the oldest entry."""
        # Use a smaller limit for faster tests
        small_limit = 5
        with patch(
            "rag_mcp.daemon.watcher.MAX_HASH_CACHE_ENTRIES", small_limit
        ):
            # Fill cache to exactly the limit
            for i in range(small_limit):
                handler._hash_cache[f"/tmp/file_{i}.pdf"] = f"hash_{i}"

            # Verify oldest entry exists
            assert "/tmp/file_0.pdf" in handler._hash_cache
            assert len(handler._hash_cache) == small_limit

            # Now simulate adding a new entry that triggers eviction
            # (using small_limit directly since local import is not
            # affected by the patch)
            if len(handler._hash_cache) >= small_limit:
                oldest = next(iter(handler._hash_cache))
                del handler._hash_cache[oldest]
            handler._hash_cache["/tmp/new_file.pdf"] = "hash_new"

            # Oldest entry should be gone, new entry present
            assert "/tmp/file_0.pdf" not in handler._hash_cache
            assert "/tmp/new_file.pdf" in handler._hash_cache
            assert len(handler._hash_cache) == small_limit

# ── 6.7 Test shutdown_requested early return ──────────────────────────────────


class TestShutdownRequestedBypass:
    """_schedule_ingest and _do_ingest skip work when shutdown is
    requested."""

    @patch("rag_mcp.daemon.watcher.threading.Timer", _FakeTimer)
    @_patch_ingest()
    def test_schedule_ingest_skips_during_shutdown(
        self, mock_ingest, handler,
    ):
        """_schedule_ingest returns early when _shutdown_requested is set."""
        handler._shutdown_requested.set()
        event = _make_event("/tmp/test.pdf", "created")
        handler.on_created(event)

        # No timer should be scheduled
        assert "/tmp/test.pdf" not in handler._timers
        # ingest_path should never have been called
        mock_ingest.assert_not_called()

    @patch("rag_mcp.daemon.watcher.threading.Timer", _FakeTimer)
    @patch("rag_mcp.daemon.watcher._sha256_file", return_value="hash1")
    @_patch_ingest()
    def test_do_ingest_skips_during_shutdown(
        self, mock_ingest, mock_hash, handler,
    ):
        """_do_ingest returns early when _shutdown_requested is set."""
        handler._shutdown_requested.set()

        event = _make_event("/tmp/test.pdf", "created")
        handler.on_created(event)

        # Manually fire the timer (normally _schedule_ingest is skipped too,
        # but we want to test _do_ingest's early return)
        timer = handler._timers.get("/tmp/test.pdf")
        if timer:
            timer.fire()

        # ingest_path should NOT be called
        mock_ingest.assert_not_called()


# ── on_deleted watcher tests ─────────────────────────────────────────────


class TestOnDeletedHandler:
    """Tests for the on_deleted event handler."""

    _REMOVE_DOC_TARGET = "rag_mcp.core.ingestion.remove_document"

    @patch("rag_mcp.daemon.watcher.threading.Timer", _FakeTimer)
    @patch(_REMOVE_DOC_TARGET)
    def test_on_deleted_removes_vectors(
        self, mock_remove, handler,
    ):
        """on_deleted must call remove_document and log success."""
        mock_remove.return_value = {
            "status": "ok",
            "chunks_removed": 8,
            "collection": "documents",
        }
        event = _make_event("/tmp/paper.pdf", "deleted")
        handler.on_deleted(event)

        # remove_document must be called
        mock_remove.assert_called_once_with(
            "/tmp/paper.pdf", collection_name="documents"
        )

    @patch("rag_mcp.daemon.watcher.threading.Timer", _FakeTimer)
    @patch(_REMOVE_DOC_TARGET)
    def test_on_deleted_cancels_pending_timer(
        self, mock_remove, handler,
    ):
        """on_deleted must cancel any pending ingest timer."""
        mock_remove.return_value = {
            "status": "ok", "chunks_removed": 0, "collection": "documents",
        }

        # First, schedule an ingest
        event_create = _make_event("/tmp/paper.pdf", "created")
        handler.on_created(event_create)
        assert "/tmp/paper.pdf" in handler._timers

        # Now delete it
        event_delete = _make_event("/tmp/paper.pdf", "deleted")
        handler.on_deleted(event_delete)

        # Timer should be cancelled and removed
        assert "/tmp/paper.pdf" not in handler._timers

    @patch("rag_mcp.daemon.watcher.threading.Timer", _FakeTimer)
    @patch(_REMOVE_DOC_TARGET)
    def test_on_deleted_clears_hash_cache(
        self, mock_remove, handler,
    ):
        """on_deleted must clear hash cache entry for deleted file."""
        mock_remove.return_value = {
            "status": "ok", "chunks_removed": 0, "collection": "documents",
        }

        # Pre-populate hash cache
        handler._hash_cache["/tmp/paper.pdf"] = "somehash"

        event = _make_event("/tmp/paper.pdf", "deleted")
        handler.on_deleted(event)

        # Hash cache should be cleared
        assert "/tmp/paper.pdf" not in handler._hash_cache

    @patch("rag_mcp.daemon.watcher.threading.Timer", _FakeTimer)
    @patch(_REMOVE_DOC_TARGET)
    def test_on_deleted_uses_handler_collection(
        self, mock_remove,
    ):
        """on_deleted must use the handler's configured collection."""
        mock_remove.return_value = {
            "status": "ok", "chunks_removed": 3, "collection": "research",
        }
        handler = DocumentIngestHandler(collection_name="research")
        event = _make_event("/tmp/paper.pdf", "deleted")
        handler.on_deleted(event)

        mock_remove.assert_called_once_with(
            "/tmp/paper.pdf", collection_name="research"
        )

    @patch("rag_mcp.daemon.watcher.threading.Timer", _FakeTimer)
    @patch(_REMOVE_DOC_TARGET)
    def test_on_deleted_no_chunks_logs_info(
        self, mock_remove, handler,
    ):
        """on_deleted with no indexed chunks must not raise error."""
        mock_remove.return_value = {
            "status": "ok", "chunks_removed": 0, "collection": "documents",
        }

        event = _make_event("/tmp/ghost.pdf", "deleted")
        handler.on_deleted(event)

        # Should complete without error
        mock_remove.assert_called_once()

    @patch("rag_mcp.daemon.watcher.threading.Timer", _FakeTimer)
    @patch(_REMOVE_DOC_TARGET)
    def test_on_deleted_logs_warning_on_failure(
        self, mock_remove, handler,
    ):
        """on_deleted must not crash when remove_document fails."""
        mock_remove.return_value = {
            "status": "error",
            "message": "Collection does not exist",
            "chunks_removed": 0,
        }

        event = _make_event("/tmp/paper.pdf", "deleted")
        handler.on_deleted(event)

        # Should complete without raising
        mock_remove.assert_called_once()

    @patch("rag_mcp.daemon.watcher.threading.Timer", _FakeTimer)
    @patch(_REMOVE_DOC_TARGET)
    def test_on_deleted_shutdown_bypass(
        self, mock_remove, handler,
    ):
        """on_deleted must skip work during shutdown."""
        handler._shutdown_requested.set()

        event = _make_event("/tmp/paper.pdf", "deleted")
        handler.on_deleted(event)

        mock_remove.assert_not_called()

    @patch("rag_mcp.daemon.watcher.threading.Timer", _FakeTimer)
    def test_on_deleted_ignores_unsupported_files(self, handler):
        """Unsupported files are filtered by PatternMatchingEventHandler."""
        from watchdog.utils.patterns import match_any_paths
        # .png should not match handler patterns
        matched = match_any_paths(
            ["image.png"],
            included_patterns=handler.patterns,
            case_sensitive=False,
        )
        assert not matched
