import subprocess

from app.processes import terminate_process_tree


def test_process_group_handles_already_exited_process():
    process = subprocess.Popen(["cmd", "/c", "exit", "0"])
    process.wait()
    terminate_process_tree(process)


def test_process_group_force_kills_when_graceful_termination_times_out(monkeypatch):
    class FakeProcess:
        pid = 123
        returncode = None

        def poll(self):
            return self.returncode

        def terminate(self):
            pass

        def wait(self, timeout):
            raise subprocess.TimeoutExpired(["fake"], timeout)

        def kill(self):
            self.returncode = -9

    process = FakeProcess()
    calls = []
    monkeypatch.setattr("app.processes.os.name", "nt")
    monkeypatch.setattr(
        "app.processes.subprocess.run",
        lambda args, **kwargs: calls.append((args, kwargs)),
    )
    terminate_process_tree(process)
    assert calls[0][0][:4] == ["taskkill", "/PID", "123", "/T"]
