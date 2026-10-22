"""``.env`` is read from the directory the command starts in.

``load_dotenv()`` with no path searches upward from the calling module's
file when the program is a script, so an installed ``omrs`` would never see
the user's ``.env``. Settings read straight from the environment, such as
``WEB_MAX_UPLOAD_MIB``, depend on this.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

_PROBE = "import os\nimport {module}\nprint(os.environ.get('OMRS_DOTENV_PROBE'))\n"


@pytest.mark.parametrize("module", ["omrs.config", "omrs.transports.mcp"])
def test_dotenv_in_the_working_directory_is_loaded(tmp_path: Path, module: str) -> None:
    (tmp_path / ".env").write_text("OMRS_DOTENV_PROBE=from-cwd\n", encoding="utf-8")
    script = tmp_path / "probe.py"
    script.write_text(_PROBE.format(module=module), encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k != "OMRS_DOTENV_PROBE"}

    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )

    assert result.stdout.strip().splitlines()[-1] == "from-cwd"
