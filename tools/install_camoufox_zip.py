#!/usr/bin/env python3
"""
install_camoufox_zip.py - install a pre-downloaded Camoufox build.

`camoufox fetch` streams ~1.2 GB straight from the GitHub release CDN, which on
a throttled connection stalls (and it has no resume). This feeds an
already-downloaded archive into Camoufox's own installer instead, so checksum
verification, version metadata and the active-version pointer all still happen
through the official code path.

Usage:
    python tools/install_camoufox_zip.py path\\to\\camoufox-<ver>-win.x86_64.zip
"""

import shutil
import sys
import types
from pathlib import Path

from camoufox.pkgman import CamoufoxFetcher


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2

    archive = Path(sys.argv[1]).expanduser().resolve()
    if not archive.is_file():
        print(f"archive not found: {archive}")
        return 2

    size_gb = archive.stat().st_size / (1024**3)
    print(f"Using local archive: {archive.name} ({size_gb:.2f} GB)")

    fetcher = CamoufoxFetcher()
    print(f"Target version: {fetcher.version} (build {fetcher.build})")

    def _local_download(self, temp_file, url, *args, **kwargs):
        """Stand in for the network download; the installer verifies the hash.

        ``temp_file`` is an already-open NamedTemporaryFile. Re-opening it by
        name fails on Windows (the handle is exclusive), so stream into the
        object itself.
        """
        with open(self._local_archive, "rb") as src:
            shutil.copyfileobj(src, temp_file, length=4 * 1024 * 1024)
        temp_file.flush()
        try:
            temp_file.seek(0)
        except Exception:
            pass

    fetcher._local_archive = str(archive)
    fetcher.download_file = types.MethodType(_local_download, fetcher)

    fetcher.install()
    print("Installed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
