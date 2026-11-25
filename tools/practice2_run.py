"""Run a command and preserve UTF-8 output and exit status (PowerShell safe)."""
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    destination, *command = sys.argv[1:]
    if not command:
        raise SystemExit('usage: practice2_run.py OUTPUT COMMAND [ARGS...]')
    env = dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            env=env, encoding='utf-8', errors='replace')
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(result.stdout, encoding='utf-8')
    path.with_suffix('.status.json').write_text(json.dumps(
        {'command': command, 'exit_code': result.returncode}, ensure_ascii=False, indent=2),
        encoding='utf-8')
    print(result.stdout)
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
