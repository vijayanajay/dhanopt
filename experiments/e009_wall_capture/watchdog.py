"""e009 crash-restart supervisor.

The capture loop already survives *request* failures (it writes an outage row
and carries on, PREREG s2). What it cannot survive is the process dying — a
lost socket, a Windows update, the laptop suspending. A 09:00-15:35 session is
6.6h of quotes; one death at 11:00 silently truncates it below kill-1's 95%
coverage bar and the whole day is lost.

So run the collector under this instead. It re-launches capture_chains until the
session ends or a clean exit occurs. Restarting is safe because capture_session
resumes from the seconds already on disk (see _existing_stamps), so the watchdog
costs at most the in-flight snapshot, never the session.

    python -m experiments.e009_wall_capture.watchdog

Point the scheduled task at THIS, not at capture_chains.
"""
from __future__ import annotations

import subprocess
import sys
import time
from datetime import date as _date
from datetime import datetime, timedelta

# A capture process that dies immediately, repeatedly, is not going to recover
# on the next try either. Bail rather than spin all morning.
MAX_RESTARTS = 10
BACKOFF_SECS = 15


def _session_end(d: _date) -> datetime:
    end = datetime.combine(d, datetime.min.time())
    return end + timedelta(hours=15, minutes=35)


def main() -> int:
    d = _date.today()
    if d.weekday() >= 5:
        print(f"{d.isoformat()} is not a weekday — nothing to supervise.")
        return 3
    end = _session_end(d)
    restarts = 0
    cmd = [sys.executable, "-m", "experiments.e009_wall_capture.capture_chains"]
    while datetime.now() < end:
        rc = subprocess.call(cmd)
        if rc == 0:
            print(f"capture exited clean after {restarts} restart(s).")
            return 0
        restarts += 1
        print(f"[watchdog] capture exited rc={rc}; restart {restarts}/{MAX_RESTARTS} "
              f"at {datetime.now():%H:%M:%S}", flush=True)
        if restarts > MAX_RESTARTS or datetime.now() >= end:
            print("[watchdog] giving up for today — session will be short and "
                  "will fail kill 1 on coverage.")
            return 1
        time.sleep(BACKOFF_SECS)
    print("[watchdog] session window closed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
