import logging
import threading
import subprocess
import sys
import time
import signal
import os

class ExecAsyncHandler(threading.Thread):
    def __init__(self, cmd, timeout):
        self.cmd = cmd
        # calling parent class constructor
        threading.Thread.__init__(self)
        self.log = logging.getLogger(__name__)
        self.stdout = None
        self.stderr = None
        self.retcode = None
        self.timeout = timeout
        self.process = None
        self.stop_flag = False
        self.timer = 0

    def run(self):
        self.log.debug(f"Executing:\n\t {' '.join(self.cmd)}")

        # Add :verbosity=1 to debug ubsan and asan
        proc_env = {
            "UBSAN_OPTIONS": "print_stacktrace=1:color=always:halt_on_error=1",
            "ASAN_OPTIONS": "print_stacktrace=1:color=always:halt_on_error=1"
        }

        self.process = subprocess.Popen(
            self.cmd,
            stdin=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=proc_env,
            encoding="utf-8"
        )

        while not self.stop_flag:
            if self.timer >= self.timeout:
                self.retcode = -1
                self.process.kill()
                self.stdout, self.stderr = self.process.communicate()

                self.log.error(
                    f"Timeout expired executing {' '.join(self.cmd)}")
                return
            try:
                self.process.wait(0.1)
                self.stdout, self.stderr = self.process.communicate()
                self.retcode = self.process.returncode

                return
            except subprocess.TimeoutExpired as ex:
                pass
            self.timer += 0.1

        # if stop flag has been set
        self.process.kill()
        self.stdout, self.stderr = self.process.communicate()
        self.retcode = self.process.returncode

    @property
    def sig_name(self):
        try:
            return signal.Signals(self.retcode).name
        except ValueError:
            return None


    def stop(self):
        self.stop_flag = True

    def print_output(self):
        self.collect()
        if self.stdout is not None:
            sys.stderr.write(self.stdout)
        if self.stderr is not None:
            sys.stderr.write(self.stderr)
        if self.retcode != 0:
            d = [os.path.basename(self.cmd[0])] + self.cmd[1:]
            sys.stderr.write(f"{self.sig_name}: Returncode {self.retcode}: ./{' '.join(d)}\n")

    def collect(self):
        while self.is_alive():
            time.sleep(0.1)

        return self.retcode, self.stderr, self.stdout



def exec_async(cmd, timeout=10):
    handler = ExecAsyncHandler(cmd, timeout)
    handler.start()
    return handler


def collect_trace(handlers: [ExecAsyncHandler]):
    traces = []

    for i, h in enumerate(handlers):
        status, out, err = h.collect()
        traces.append(f'Stdout{i}: {out} // Stderr{i}: {err}')

    return ' '.join(traces)
