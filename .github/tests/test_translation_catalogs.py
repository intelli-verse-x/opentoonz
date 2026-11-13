#!/usr/bin/env python3
"""Compile changed Qt catalogs to owned temporary outputs; no wording/GUI claim."""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
CATALOGS = ('toonz/sources/translations/chinese/tnztools.ts', 'toonz/sources/translations/chinese/toonz.ts', 'toonz/sources/translations/czech/tnztools.ts', 'toonz/sources/translations/czech/toonz.ts', 'toonz/sources/translations/french/tnztools.ts', 'toonz/sources/translations/french/toonz.ts', 'toonz/sources/translations/german/tnztools.ts', 'toonz/sources/translations/german/toonz.ts', 'toonz/sources/translations/italian/tnztools.ts', 'toonz/sources/translations/italian/toonz.ts', 'toonz/sources/translations/japanese/tnztools.ts', 'toonz/sources/translations/japanese/toonz.ts', 'toonz/sources/translations/korean/tnztools.ts', 'toonz/sources/translations/korean/toonz.ts', 'toonz/sources/translations/portuguese_brazil/tnztools.ts', 'toonz/sources/translations/portuguese_brazil/toonz.ts', 'toonz/sources/translations/russian/tnztools.ts', 'toonz/sources/translations/russian/toonz.ts', 'toonz/sources/translations/spanish/tnztools.ts', 'toonz/sources/translations/spanish/toonz.ts', 'toonz/sources/translations/traditional_chinese/colorfx.ts', 'toonz/sources/translations/traditional_chinese/image.ts', 'toonz/sources/translations/traditional_chinese/tnzcore.ts', 'toonz/sources/translations/traditional_chinese/tnztools.ts', 'toonz/sources/translations/traditional_chinese/toonz.ts', 'toonz/sources/translations/traditional_chinese/toonzlib.ts', 'toonz/sources/translations/traditional_chinese/toonzqt.ts')


def main():
    compiler = shutil.which("lrelease")
    if compiler is None:
        raise SystemExit("Qt lrelease is required; install qttools5-dev-tools")
    with tempfile.TemporaryDirectory(prefix="ot-catalogs-") as directory:
        for index, relative in enumerate(CATALOGS):
            source = ROOT / relative
            if not source.is_file() or source.is_symlink():
                raise SystemExit("Missing or symlinked expected catalog: " + relative)
            output = Path(directory) / (str(index) + ".qm")
            subprocess.run([compiler, str(source), "-qm", str(output)],
                           check=True, timeout=60)
            if not output.is_file() or output.stat().st_size == 0:
                raise SystemExit("Compiler produced no catalog: " + relative)
    print(str(len(CATALOGS)) + " Qt catalogs compiled; wording and GUI behavior not assessed")


if __name__ == "__main__":
    main()
