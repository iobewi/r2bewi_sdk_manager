"""
Tests unitaires — src.k3s.headlamp

Couvre :
- interpolation correcte du message d'erreur (anti-régression bug f-string)
- succès : token affiché sur stdout
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.components.k3s.headlamp import _execute


def _make_result(returncode: int, stdout: str = "", stderr: str = "") -> SimpleNamespace:
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


# ── Cas d'échec ───────────────────────────────────────────────────────────────

class TestHeadlampTokenFailure:
    def test_error_message_contains_namespace(self):
        collected: list[str] = []

        with patch("src.components.k3s.headlamp._run_cmd", return_value=_make_result(1, stderr="not found")):
            with patch("src.components.k3s.headlamp.error", side_effect=lambda msg: collected.append(msg)):
                with pytest.raises(SystemExit):
                    _execute(namespace="my-ns", sa="my-sa")

        verify_lines = [m for m in collected if "Vérifier" in m]
        assert verify_lines, "Aucun message 'Vérifier' émis"
        assert "my-ns" in verify_lines[0], (
            f"namespace non interpolé dans le message : {verify_lines[0]!r}"
        )

    def test_error_message_contains_sa(self):
        collected: list[str] = []

        with patch("src.components.k3s.headlamp._run_cmd", return_value=_make_result(1, stderr="not found")):
            with patch("src.components.k3s.headlamp.error", side_effect=lambda msg: collected.append(msg)):
                with pytest.raises(SystemExit):
                    _execute(namespace="my-ns", sa="my-sa")

        verify_lines = [m for m in collected if "Vérifier" in m]
        assert "my-sa" in verify_lines[0], (
            f"ServiceAccount non interpolé dans le message : {verify_lines[0]!r}"
        )

    def test_error_message_no_literal_braces(self):
        collected: list[str] = []

        with patch("src.components.k3s.headlamp._run_cmd", return_value=_make_result(1)):
            with patch("src.components.k3s.headlamp.error", side_effect=lambda msg: collected.append(msg)):
                with pytest.raises(SystemExit):
                    _execute(namespace="ros", sa="headlamp-ros")

        for msg in collected:
            assert "{namespace}" not in msg, f"Accolade littérale {{namespace}} dans : {msg!r}"
            assert "{sa}" not in msg, f"Accolade littérale {{sa}} dans : {msg!r}"

    def test_stderr_included_in_error_output(self):
        collected: list[str] = []

        with patch("src.components.k3s.headlamp._run_cmd",
                   return_value=_make_result(1, stderr="serviceaccount not found")):
            with patch("src.components.k3s.headlamp.error", side_effect=lambda msg: collected.append(msg)):
                with pytest.raises(SystemExit):
                    _execute()

        assert any("serviceaccount not found" in m for m in collected)

    def test_exits_with_code_1_on_failure(self):
        with patch("src.components.k3s.headlamp._run_cmd", return_value=_make_result(1)):
            with patch("src.components.k3s.headlamp.error"):
                with pytest.raises(SystemExit) as exc_info:
                    _execute()
        assert exc_info.value.code == 1


# ── Cas de succès ─────────────────────────────────────────────────────────────

class TestHeadlampTokenSuccess:
    def test_token_printed_on_stdout(self, capsys):
        token = "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.test"

        with patch("src.components.k3s.headlamp._run_cmd", return_value=_make_result(0, stdout=token)):
            with patch("src.components.k3s.headlamp._copy_to_clipboard"):
                _execute()

        captured = capsys.readouterr()
        assert token in captured.out

    def test_no_sys_exit_on_success(self):
        with patch("src.components.k3s.headlamp._run_cmd", return_value=_make_result(0, stdout="tok")):
            with patch("src.components.k3s.headlamp._copy_to_clipboard"):
                _execute()
