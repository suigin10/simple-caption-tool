"""Entry point for the console-free portable build."""
from pathlib import Path
import sys
import traceback

if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        output = Path(sys.argv[2]).resolve()
        output.mkdir(parents=True, exist_ok=True)
        with (output / "startup.log").open("w", encoding="utf8") as log:
            sys.stdout = sys.stderr = log
            log.write("Starting packaged GUI self-test\n")
            log.flush()
            try:
                from captioner.binary_smoke import run
                result = run(output)
            except Exception:
                traceback.print_exc()
                result = 1
            log.flush()
        raise SystemExit(result)
    from captioner.gui import main
    main()
