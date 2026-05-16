"""Unit tests for sofi_manager.cli — argparse plumbing + every subcommand.

The CLI mutates global state (Color class attrs via _strip_colors, the
CONFIG_PATH module constant) and prompts on stdin in the `add` wizard, so
each test redirects CONFIG_PATH to tmp_path, snapshots the ANSI palette,
and feeds `input()` via monkeypatch.
"""

from __future__ import annotations

import json
import queue
import signal
from pathlib import Path
from typing import Any, ClassVar

import pytest
from cryptography.fernet import Fernet

from sofi_manager import cli, crypto

# =====================================================================
# Shared fixtures
# =====================================================================


@pytest.fixture(autouse=True)
def _isolated_cipher() -> object:
    crypto.set_cipher_for_tests(Fernet(Fernet.generate_key()))
    yield
    crypto.set_cipher_for_tests(None)


@pytest.fixture(autouse=True)
def _color_snapshot() -> object:
    """`_strip_colors` mutates class attrs on cli.Color — snapshot/restore
    so a test that triggers --no-color (or the non-tty path) does not bleed
    into the next test."""
    saved = {
        name: getattr(cli.Color, name)
        for name in dir(cli.Color)
        if not name.startswith("_") and name.isupper()
    }
    yield
    for name, value in saved.items():
        setattr(cli.Color, name, value)


@pytest.fixture
def cfg_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    p = tmp_path / "bots.json"
    monkeypatch.setattr(cli, "CONFIG_PATH", p)
    return p


def _write_bots(path: Path, bots: list[dict[str, Any]]) -> None:
    """Write bots.json directly, mimicking what save_bots produces (but
    skipping encryption — load_bots's decrypt_token tolerates plaintext)."""
    path.write_text(json.dumps({"bots": bots}, indent=2), encoding="utf-8")


# =====================================================================
# Argparse plumbing
# =====================================================================


class TestPlumbing:
    def test_no_args_exits_with_required_error(self) -> None:
        with pytest.raises(SystemExit) as exc:
            cli.main([])
        assert exc.value.code == 2

    def test_unknown_subcommand_exits(self) -> None:
        with pytest.raises(SystemExit) as exc:
            cli.main(["bogus"])
        assert exc.value.code == 2

    def test_version_flag_prints_and_exits_zero(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as exc:
            cli.main(["--version"])
        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "Selfbot Manager" in out

    def test_build_parser_registers_all_subcommands(self) -> None:
        parser = cli.build_parser()
        # Argparse stores subparser names on the _SubParsersAction.choices.
        sub_action = next(a for a in parser._actions if a.__class__.__name__ == "_SubParsersAction")
        assert set(sub_action.choices) == {"list", "show", "add", "rm", "run"}

    def test_no_color_strips_ansi_from_output(
        self, cfg_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Empty bots.json → list prints the "No bots yet" hint. With
        # --no-color the gold/dimgray escapes should be absent from stdout.
        rc = cli.main(["--no-color", "list"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "No bots yet" in out
        assert "\x1b[" not in out

    def test_keyboard_interrupt_returns_130(
        self, cfg_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def boom(_args: object) -> int:
            raise KeyboardInterrupt

        # Replace cmd_list in the dispatch table so the outer main()
        # try/except catches the KeyboardInterrupt.
        monkeypatch.setattr(cli, "cmd_list", boom)
        rc = cli.main(["list"])
        assert rc == 130


# =====================================================================
# cmd_list
# =====================================================================


class TestCmdList:
    def test_empty_config_prints_hint(
        self, cfg_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc = cli.main(["list"])
        assert rc == 0
        assert "No bots yet" in capsys.readouterr().out

    def test_corrupt_json_is_recovered_silently(
        self, cfg_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        cfg_path.write_text("{not json", encoding="utf-8")
        rc = cli.main(["list"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Failed to read" in out

    def test_lists_two_bots_with_full_details(
        self, cfg_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write_bots(
            cfg_path,
            [
                {
                    "_id": "id-a",
                    "name": "alpha",
                    "token": "abcdef123456",
                    "drop_channel": 111,
                    "all_channels": [111, 222],
                    "wishlist": ["miku"],
                    "wishlist_series": ["vocaloid"],
                    "night_pause_enabled": True,
                },
                {
                    "_id": "id-b",
                    "name": "beta",
                    "token": "",  # missing → MISSING tag
                    "drop_channel": 0,
                    "all_channels": [],
                    "night_pause_enabled": False,
                },
            ],
        )
        rc = cli.main(["list"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "alpha" in out
        assert "beta" in out
        assert "…123456" in out  # token suffix tag
        assert "MISSING" in out
        assert "2 channel(s)" in out
        assert "1 chars · 1 series" in out


# =====================================================================
# cmd_show
# =====================================================================


class TestCmdShow:
    def test_unknown_name_returns_1(
        self, cfg_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write_bots(cfg_path, [{"_id": "id-a", "name": "alpha", "token": "t"}])
        rc = cli.main(["show", "ghost"])
        assert rc == 1
        assert "No bot named" in capsys.readouterr().out

    def test_show_redacts_token_and_emits_json(
        self, cfg_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write_bots(
            cfg_path,
            [
                {
                    "_id": "id-a",
                    "name": "alpha",
                    "token": "TOKENVALUEHERE0123456789",
                    "drop_channel": 111,
                }
            ],
        )
        rc = cli.main(["show", "alpha"])
        assert rc == 0
        out = capsys.readouterr().out
        # Token is redacted: prefix…suffix, full value never printed.
        assert "TOKENVALUEHERE0123456789" not in out
        # JSON must parse and carry the redacted form.
        # Strip ANSI lines (header) before the JSON body.
        json_start = out.index("{")
        parsed = json.loads(out[json_start:])
        assert parsed["name"] == "alpha"
        assert "…" in parsed["token"]

    def test_show_matches_by_id(self, cfg_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        _write_bots(cfg_path, [{"_id": "id-xyz", "name": "alpha", "token": "tok"}])
        rc = cli.main(["show", "id-xyz"])
        assert rc == 0
        json_start = capsys.readouterr().out.index("{")
        # No exception → match by id worked.
        assert json_start >= 0


# =====================================================================
# cmd_add — interactive wizard driven by monkeypatched input()
# =====================================================================


def _feed_inputs(monkeypatch: pytest.MonkeyPatch, answers: list[str]) -> list[str]:
    """Replace builtins.input with a queue of answers. Returns the same
    list so the test can append further answers (rare)."""
    it = iter(answers)

    def fake_input(_prompt: str = "") -> str:
        try:
            return next(it)
        except StopIteration as exc:  # pragma: no cover - test smell
            raise EOFError("exhausted scripted inputs") from exc

    monkeypatch.setattr("builtins.input", fake_input)
    return answers


class TestCmdAdd:
    def test_happy_path_writes_encrypted_bot(
        self,
        cfg_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _feed_inputs(
            monkeypatch,
            [
                "mybot",  # name
                "the-token",  # token
                "111",  # drop_channel
                "222",  # additional channel
                "333",  # additional channel
                "",  # finish channel list
            ],
        )
        rc = cli.main(["add"])
        assert rc == 0

        # bots.json written, token encrypted on disk, plaintext absent.
        raw = cfg_path.read_text(encoding="utf-8")
        assert "the-token" not in raw
        assert "enc:v1:" in raw
        # Round-trip via load_bots: token decrypts back to plaintext.
        bots = cli.load_bots()
        assert bots[0]["name"] == "mybot"
        assert bots[0]["token"] == "the-token"
        assert bots[0]["drop_channel"] == 111
        assert bots[0]["all_channels"] == [111, 222, 333]
        assert capsys.readouterr().out.count("OK") >= 1

    def test_duplicate_name_aborts(
        self,
        cfg_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _write_bots(cfg_path, [{"_id": "id-a", "name": "dup", "token": "x"}])
        _feed_inputs(monkeypatch, ["dup"])
        rc = cli.main(["add"])
        assert rc == 1
        assert "already exists" in capsys.readouterr().out

    def test_keyboard_interrupt_returns_130(
        self,
        cfg_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        def cancel(_prompt: str = "") -> str:
            raise KeyboardInterrupt

        monkeypatch.setattr("builtins.input", cancel)
        rc = cli.main(["add"])
        assert rc == 130
        assert "Cancelled" in capsys.readouterr().out

    def test_ask_int_retries_on_garbage(
        self,
        cfg_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # _ask_int loops on ValueError; _ask_list skips non-int entries.
        _feed_inputs(
            monkeypatch,
            [
                "named",  # name
                "tok",  # token
                "not-an-int",  # invalid drop_channel → re-prompt
                "42",  # valid drop_channel
                "bad",  # invalid extra → skip + continue
                "999",  # valid extra channel
                "",  # finish
            ],
        )
        rc = cli.main(["add"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "not a number" in out
        assert "skipping" in out
        bots = cli.load_bots()
        assert bots[0]["drop_channel"] == 42
        assert 999 in bots[0]["all_channels"]


# =====================================================================
# cmd_rm
# =====================================================================


class TestCmdRm:
    def test_unknown_name_returns_1(
        self, cfg_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write_bots(cfg_path, [{"_id": "a", "name": "alpha", "token": "x"}])
        rc = cli.main(["rm", "ghost"])
        assert rc == 1
        assert "No bot named" in capsys.readouterr().out

    def test_confirm_no_keeps_bot(self, cfg_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _write_bots(cfg_path, [{"_id": "a", "name": "alpha", "token": "x"}])
        monkeypatch.setattr("builtins.input", lambda _p="": "n")
        rc = cli.main(["rm", "alpha"])
        assert rc == 0
        assert len(cli.load_bots()) == 1

    def test_confirm_yes_deletes(self, cfg_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _write_bots(cfg_path, [{"_id": "a", "name": "alpha", "token": "x"}])
        monkeypatch.setattr("builtins.input", lambda _p="": "y")
        rc = cli.main(["rm", "alpha"])
        assert rc == 0
        assert cli.load_bots() == []

    def test_yes_flag_skips_prompt(self, cfg_path: Path) -> None:
        _write_bots(cfg_path, [{"_id": "a", "name": "alpha", "token": "x"}])
        rc = cli.main(["rm", "alpha", "--yes"])
        assert rc == 0
        assert cli.load_bots() == []


# =====================================================================
# cmd_run — heaviest path; SelfBot, signal handlers and time.sleep are
# all stubbed so the test stays within the unit-test budget.
# =====================================================================


class _FakeSelfBot:
    """Stand-in for sofi_manager.bot_core.SelfBot. cmd_run only touches:
    .config, .log_queue, .status_callback, .start(), .stop()."""

    instances: ClassVar[list[_FakeSelfBot]] = []

    def __init__(self, cfg: dict[str, Any]) -> None:
        self.config = cfg
        self.log_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        # Pre-seed two log lines so the polling loop drains them on the
        # first iteration — exercises LEVEL_COLOR lookup + prefix code.
        self.log_queue.put(("info", "hello from bot"))
        self.log_queue.put(("error", "kaboom"))
        self.status_callback: Any = None
        self.started = False
        self.stopped = False
        type(self).instances.append(self)

    def start(self) -> bool:
        self.started = True
        # Fire one status update so the test can exercise the callback.
        if self.status_callback:
            self.status_callback("running")
        return True

    def stop(self) -> None:
        self.stopped = True


@pytest.fixture
def fake_selfbot(monkeypatch: pytest.MonkeyPatch) -> type[_FakeSelfBot]:
    _FakeSelfBot.instances = []
    monkeypatch.setattr(cli, "SelfBot", _FakeSelfBot)
    # Defang signal handlers so the test process is never re-wired.
    monkeypatch.setattr(cli.signal, "signal", lambda *_a, **_k: None)
    return _FakeSelfBot


class TestCmdRun:
    def test_no_bots_returns_1(self, cfg_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        rc = cli.main(["run"])
        assert rc == 1
        assert "No bots configured" in capsys.readouterr().out

    def test_unknown_name_returns_1(
        self,
        cfg_path: Path,
        fake_selfbot: type[_FakeSelfBot],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _write_bots(cfg_path, [{"_id": "a", "name": "alpha", "token": "t"}])
        rc = cli.main(["run", "ghost"])
        assert rc == 1
        assert "Unknown bot(s)" in capsys.readouterr().out
        # Critically: no bot was instantiated when the name set is invalid.
        assert fake_selfbot.instances == []

    def test_happy_path_starts_stops_and_drains_logs(
        self,
        cfg_path: Path,
        fake_selfbot: type[_FakeSelfBot],
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _write_bots(
            cfg_path,
            [{"_id": "a", "name": "alpha", "token": "t", "drop_channel": 111}],
        )

        # Polling-loop control: first sleep raises KeyboardInterrupt to
        # break out; subsequent calls (post-stop drain) no-op.
        sleep_calls = {"n": 0}

        def fake_sleep(_seconds: float) -> None:
            sleep_calls["n"] += 1
            if sleep_calls["n"] == 1:
                raise KeyboardInterrupt

        monkeypatch.setattr(cli.time, "sleep", fake_sleep)

        rc = cli.main(["run"])
        assert rc == 0

        # Exactly one bot was instantiated, started and stopped.
        assert len(fake_selfbot.instances) == 1
        bot = fake_selfbot.instances[0]
        assert bot.started
        assert bot.stopped

        out = capsys.readouterr().out
        assert "hello from bot" in out
        assert "kaboom" in out
        assert "Stopping bots" in out
        assert "Done" in out
        # status_callback fired with "running" → green tag printed.
        assert "running" in out

    def test_partial_name_filtering(
        self,
        cfg_path: Path,
        fake_selfbot: type[_FakeSelfBot],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _write_bots(
            cfg_path,
            [
                {"_id": "a", "name": "alpha", "token": "t", "drop_channel": 1},
                {"_id": "b", "name": "beta", "token": "t", "drop_channel": 2},
                {"_id": "c", "name": "gamma", "token": "t", "drop_channel": 3},
            ],
        )

        def fake_sleep(_s: float) -> None:
            raise KeyboardInterrupt

        monkeypatch.setattr(cli.time, "sleep", fake_sleep)

        rc = cli.main(["run", "alpha", "gamma"])
        assert rc == 0
        names = sorted(b.config["name"] for b in fake_selfbot.instances)
        assert names == ["alpha", "gamma"]

    def test_status_callback_covers_all_branches(
        self,
        cfg_path: Path,
        fake_selfbot: type[_FakeSelfBot],
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # Make the fake bot fire every status code through the callback so
        # _on_status's tag dict is fully exercised (lines 324-329).
        class _StatusFiringBot(_FakeSelfBot):
            def start(self) -> bool:
                self.started = True
                if self.status_callback:
                    for status in (
                        "running",
                        "starting",
                        "stopped",
                        "error",
                        "weird-unknown",
                    ):
                        self.status_callback(status)
                return True

        _StatusFiringBot.instances = []
        monkeypatch.setattr(cli, "SelfBot", _StatusFiringBot)
        _write_bots(
            cfg_path,
            [{"_id": "a", "name": "alpha", "token": "t", "drop_channel": 1}],
        )

        def fake_sleep(_s: float) -> None:
            raise KeyboardInterrupt

        monkeypatch.setattr(cli.time, "sleep", fake_sleep)

        rc = cli.main(["run"])
        assert rc == 0
        out = capsys.readouterr().out
        # Each tag text + the passthrough for unknown status.
        for needle in ("running", "connecting", "stopped", "error", "weird-unknown"):
            assert needle in out

    def test_stop_swallows_exceptions(
        self,
        cfg_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # A bot whose stop() raises must not prevent the shutdown sequence
        # from finishing (the except Exception: pass on lines 379-382).
        class _BadStopBot(_FakeSelfBot):
            def stop(self) -> None:
                raise RuntimeError("broken stop")

        _BadStopBot.instances = []
        monkeypatch.setattr(cli, "SelfBot", _BadStopBot)
        monkeypatch.setattr(cli.signal, "signal", lambda *_a, **_k: None)
        _write_bots(
            cfg_path,
            [{"_id": "a", "name": "alpha", "token": "t", "drop_channel": 1}],
        )

        def fake_sleep(_s: float) -> None:
            raise KeyboardInterrupt

        monkeypatch.setattr(cli.time, "sleep", fake_sleep)

        # Must not propagate the RuntimeError.
        rc = cli.main(["run"])
        assert rc == 0


# =====================================================================
# Misc: signal handler wiring (covers the try/except around signal.signal)
# =====================================================================


class TestSignalWiring:
    def test_signal_registration_errors_are_swallowed(
        self,
        cfg_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        _FakeSelfBot.instances = []
        monkeypatch.setattr(cli, "SelfBot", _FakeSelfBot)

        def boom(_sig: int, _handler: Any) -> None:
            raise ValueError("signal not supported on this platform")

        monkeypatch.setattr(cli.signal, "signal", boom)
        _write_bots(
            cfg_path,
            [{"_id": "a", "name": "alpha", "token": "t", "drop_channel": 1}],
        )

        def fake_sleep(_s: float) -> None:
            raise KeyboardInterrupt

        monkeypatch.setattr(cli.time, "sleep", fake_sleep)

        rc = cli.main(["run"])
        assert rc == 0


# Module-level guard: signal constants we reference exist on this platform.
assert hasattr(signal, "SIGINT")
