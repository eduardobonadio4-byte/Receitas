"""Roda um comando mostrando a saída na tela e gravando num arquivo (o 'tee' do Windows).

Uso: python tools/tee.py <arquivo_log> -- <comando> [args...]
"""
import subprocess
import sys


def main() -> int:
    if len(sys.argv) < 4 or sys.argv[2] != "--":
        print(__doc__)
        return 1
    log_path, cmd = sys.argv[1], sys.argv[3:]
    with open(log_path, "a", encoding="utf-8") as log:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace", bufsize=1)
        for line in proc.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            log.write(line)
            log.flush()
        return proc.wait()


if __name__ == "__main__":
    sys.exit(main())
