"""Fake godot for orchestrator tests: passes every check instantly."""
import sys
import time

args = sys.argv[1:]
time.sleep(0.5)
if any("run_tests.gd" in a for a in args):
    print("TESTS: 5 passed, 0 failed")
for a in args:
    if a.startswith("--screenshot="):
        with open(a.split("=", 1)[1], "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\nfake")
print("fake godot ok")
