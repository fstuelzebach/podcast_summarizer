import subprocess
from datetime import datetime, timedelta, timezone

import pytest

from podcast_summarizer.publish import DataRepo, LockHeld, file_lock, primary_is_alive


def _git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


@pytest.fixture
def data_repo(tmp_path):
    remote = tmp_path / "remote.git"
    _git(tmp_path, "init", "-q", "--bare", str(remote))
    work = tmp_path / "work"
    _git(tmp_path, "init", "-q", "-b", "data", str(work))
    _git(work, "config", "user.email", "t@t")
    _git(work, "config", "user.name", "t")
    _git(work, "remote", "add", "origin", str(remote))
    (work / ".gitignore").write_text("episodes/**/*.txt\n")
    _git(work, "add", ".gitignore")
    _git(work, "commit", "-q", "-m", "init")
    _git(work, "push", "-q", "origin", "data")
    return DataRepo(work), remote


def test_commit_and_push_includes_ignored_txt_but_not_audio(data_repo):
    repo, remote = data_repo
    ep = repo.root / "episodes" / "pod"
    ep.mkdir(parents=True)
    (ep / "A_pod.txt").write_text("transcript")
    (ep / "A_pod.meta.json").write_text("{}")
    (ep / "A_pod.mp3").write_bytes(b"\x00")
    repo.write_heartbeat("vps", "primary", 1)

    assert repo.commit_and_push("ingest") is True
    files = subprocess.run(["git", "--git-dir", str(remote), "ls-tree", "-r", "--name-only", "data"],
                           capture_output=True, text=True).stdout.split()
    assert "episodes/pod/A_pod.txt" in files
    assert "state/heartbeat.json" in files
    assert "episodes/pod/A_pod.mp3" not in files
    assert repo.commit_and_push("again") is False   # nothing new


def test_pull_then_heartbeat_roundtrip(data_repo):
    repo, _ = data_repo
    repo.pull()
    repo.write_heartbeat("pc", "standby", 0)
    assert repo.read_heartbeat()["host"] == "pc"


def test_file_lock_blocks_second_run(tmp_path):
    lock = tmp_path / "x.lock"
    with file_lock(lock):
        with pytest.raises(LockHeld):
            with file_lock(lock):
                pass
    assert not lock.exists()


def test_primary_is_alive():
    now = datetime.now(timezone.utc)
    fresh = {"role": "primary", "at": (now - timedelta(hours=2)).isoformat()}
    stale = {"role": "primary", "at": (now - timedelta(hours=30)).isoformat()}
    assert primary_is_alive(fresh, 24)
    assert not primary_is_alive(stale, 24)
    assert not primary_is_alive({"role": "standby", "at": now.isoformat()}, 24)
    assert not primary_is_alive(None, 24)
