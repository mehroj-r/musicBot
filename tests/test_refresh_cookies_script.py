import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / "scripts" / "refresh-youtube-cookies.sh"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")

# Stand-in for `uv run ... yt-dlp`: writes a fake export to the --cookies path, with expiry
# times as yt-dlp exports them from Chromium (microseconds since 1601) and in Unix seconds
FAKE_UV = """#!/bin/sh
while [ $# -gt 0 ]; do [ "$1" = --cookies ] && out=$2; shift; done
cookie() { printf '%s\\tTRUE\\t/\\tTRUE\\t%s\\t%s\\tdummy\\n' "$1" "$2" "$3"; }
{
  echo '# Netscape HTTP Cookie File'
  cookie .youtube.com 1830000000 PREF
  if [ "$FAKE_SIGNED_IN" = 1 ]; then
    cookie .youtube.com 13470865140000000 LOGIN_INFO
    cookie '#HttpOnly_.youtube.com' 13470865200000000 __Secure-3PSID
  fi
} > "$out"
echo "Checked with: Fake video"
"""


@pytest.fixture
def home(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("chromium", "#!/bin/sh\nexit 0\n"), ("uv", FAKE_UV)):
        tool = bin_dir / name
        tool.write_text(body)
        tool.chmod(stat.S_IRWXU)

    config = tmp_path / "config" / "musicbot" / "youtube-cookies.conf"
    config.parent.mkdir(parents=True)
    config.write_text(
        f"SERVER=nowhere\nREMOTE_DIR=/x\nBROWSER=chromium\nPROFILE_DIR={tmp_path / 'profile'}\n"
    )
    return tmp_path


def run(home: Path, answers: str, *args: str, signed_in: bool = True):
    env = {
        **os.environ,
        "PATH": f"{home / 'bin'}:{os.environ['PATH']}",
        "XDG_CONFIG_HOME": str(home / "config"),
        "XDG_DATA_HOME": str(home / "data"),
        "FAKE_SIGNED_IN": "1" if signed_in else "0",
    }
    return subprocess.run(
        ["bash", str(SCRIPT), *args], input=answers, env=env, capture_output=True, text=True
    )


def exported(home: Path) -> Path:
    return home / "data" / "musicbot" / "youtube-cookies.txt"


def test_exports_and_keeps_cookies_when_upload_is_declined(home: Path):
    result = run(home, "\nN\n")

    assert result.returncode == 0, result.stderr
    assert "3 cookies in" in result.stdout
    # Chromium's expiry converted: 2027-11-16, not a date hundreds of millions of years away
    assert "expires on 2027-11-16 at the latest" in result.stdout
    assert "Not uploaded" in result.stdout
    assert result.stderr == ""
    assert stat.S_IMODE(exported(home).stat().st_mode) == 0o600
    assert [path.name for path in exported(home).parent.iterdir()] == ["youtube-cookies.txt"]


def test_refuses_a_profile_that_is_not_signed_in(home: Path):
    run(home, "\nN\n")
    previous = exported(home).read_text()

    result = run(home, "\n", signed_in=False)

    assert result.returncode == 1
    assert "isn't signed in" in result.stderr
    # The last good export is kept, and no temporary folder is left behind
    assert exported(home).read_text() == previous
    assert [path.name for path in exported(home).parent.iterdir()] == ["youtube-cookies.txt"]


def test_upload_only_without_an_export(home: Path):
    result = run(home, "", "--upload-only")
    assert result.returncode == 1
    assert "nothing exported yet" in result.stderr


def test_no_answer_means_no_upload(home: Path):
    run(home, "\nN\n")
    result = run(home, "", "--upload-only")
    assert result.returncode == 0
    assert "Not uploaded" in result.stdout
