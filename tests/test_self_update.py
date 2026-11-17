"""The launchers bring the code up to date before starting, so a restart can never run an old version again."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "update.sh"
ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
       "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"}
ENV.pop("BACKTEST_NO_UPDATE", None)


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env=ENV, check=True).stdout.strip()


@pytest.fixture
def world(tmp_path):
    """A 'GitHub' (bare repo), the developer's clone that pushes new commits, and the user's clone with the launcher scripts."""
    bare = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True, env=ENV)
    dev = tmp_path / "dev"
    subprocess.run(["git", "clone", "-q", str(bare), str(dev)], check=True, env=ENV, capture_output=True)
    git(dev, "checkout", "-q", "-b", "main")
    (dev / "scripts").mkdir()
    shutil.copy(SCRIPT, dev / "scripts" / "update.sh")
    (dev / "app.txt").write_text("v1\n")
    (dev / "notes.txt").write_text("mine\n")
    git(dev, "add", "-A")
    git(dev, "commit", "-qm", "v1")
    git(dev, "push", "-q", "-u", "origin", "main")
    user = tmp_path / "user"
    subprocess.run(["git", "clone", "-q", str(bare), str(user)], check=True, env=ENV, capture_output=True)

    def release(text="v2\n"):
        (dev / "app.txt").write_text(text)
        git(dev, "commit", "-qam", "release")
        git(dev, "push", "-q")
    return dev, user, release


def update(user, **extra):
    r = subprocess.run(["bash", str(user / "scripts" / "update.sh")], capture_output=True, text=True, env={**ENV, **extra})
    return r.returncode, (r.stdout + r.stderr).strip()


def test_a_clone_on_main_is_brought_up_to_date(world):
    dev, user, release = world
    release()
    code, out = update(user)
    assert code == 0 and "Updated the program" in out and (user / "app.txt").read_text() == "v2\n"


def test_nothing_to_do_is_silent(world):
    dev, user, release = world
    assert update(user) == (0, "")


def test_a_stale_stage_branch_is_replaced_by_main(world):
    dev, user, release = world
    git(user, "checkout", "-q", "-b", "stage-8-browser")          # the situation of an old merged pull request branch
    git(user, "push", "-q", "-u", "origin", "stage-8-browser")
    release()
    code, out = update(user)
    assert code == 0 and "Switched from 'stage-8-browser' to 'main'" in out
    assert git(user, "branch", "--show-current") == "main" and (user / "app.txt").read_text() == "v2\n"


def test_unpublished_local_commits_are_never_abandoned(world):
    dev, user, release = world
    git(user, "checkout", "-q", "-b", "my-work")
    (user / "mine.txt").write_text("work\n")
    git(user, "add", "-A")
    git(user, "commit", "-qm", "local only")
    release()
    code, out = update(user)
    assert code == 0 and "has commits that are only on this computer" in out and git(user, "branch", "--show-current") == "my-work"
    assert (user / "mine.txt").exists()


def test_local_edits_that_conflict_do_not_stop_the_start_and_are_kept(world):
    dev, user, release = world
    (user / "app.txt").write_text("edited by the user\n")
    release()
    code, out = update(user)
    assert code == 0 and "Could not update automatically" in out and "git stash" in out
    assert (user / "app.txt").read_text() == "edited by the user\n"


def test_local_edits_to_other_files_survive_an_update(world):
    dev, user, release = world
    (user / "notes.txt").write_text("my notes\n")
    release()
    code, out = update(user)
    assert code == 0 and "Updated the program" in out and (user / "notes.txt").read_text() == "my notes\n"


def test_no_network_just_starts(world, tmp_path):
    dev, user, release = world
    git(user, "remote", "set-url", "origin", str(tmp_path / "gone.git"))
    code, out = update(user)
    assert code == 0 and "Could not check for updates" in out


def test_opt_out_and_non_git_folders(world, tmp_path):
    dev, user, release = world
    release()
    assert update(user, BACKTEST_NO_UPDATE="1") == (0, "") and (user / "app.txt").read_text() == "v1\n"
    plain = tmp_path / "plain"
    (plain / "scripts").mkdir(parents=True)
    shutil.copy(SCRIPT, plain / "scripts" / "update.sh")
    assert update(plain) == (0, "")


def test_launchers_update_first_and_restart_themselves():
    sh, bat = (ROOT / "start.sh").read_text(encoding="utf-8"), (ROOT / "start.bat").read_text(encoding="utf-8")
    assert "scripts/update.sh" in sh and 'exec bash "$0"' in sh and "BACKTEST_UPDATED" in sh
    assert sh.index("update.sh") < sh.index(".venv/bin/python")                    # before packages are installed
    assert "scripts\\update.bat" in bat and "BACKTEST_UPDATED" in bat and bat.index("update.bat") < bat.index(".venv\\Scripts\\python")
    assert (ROOT / "scripts" / "update.bat").exists()


def test_it_works_in_a_clone_whose_remote_has_no_fetch_setting(world):
    dev, user, release = world
    subprocess.run(["git", "config", "--unset-all", "remote.origin.fetch"], cwd=user, env=ENV, check=True)
    release()
    code, out = update(user)
    assert code == 0 and "Updated the program" in out and (user / "app.txt").read_text() == "v2\n"
