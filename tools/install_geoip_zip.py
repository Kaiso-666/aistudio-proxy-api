#!/usr/bin/env python3
"""
install_geoip_zip.py - install a pre-downloaded GeoIP database bundle.

Camoufox downloads its MMDB from the same GitHub release CDN as the browser,
so it stalls for exactly the same reason. This installs an already-downloaded
archive into the location Camoufox expects and marks it active.

Usage:
    python tools/install_geoip_zip.py path\\to\\geoip-aio-all.mmdb.zip
"""

import os
import shutil
import sys
import zipfile
from pathlib import Path

from camoufox.geolocation import MMDB_DIR, load_geoip_config, save_geoip_config


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2

    archive = Path(sys.argv[1]).expanduser().resolve()
    if not archive.is_file():
        print(f"archive not found: {archive}")
        return 2

    config = load_geoip_config()
    name = config.get("name", "geolite2").lower()
    combined = "combined" in config.get("urls", {})
    target = MMDB_DIR / (f"{name}-combined.mmdb" if combined else f"{name}-ipv4.mmdb")

    MMDB_DIR.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(archive) as zf:
        members = [n for n in zf.namelist() if n.endswith(".mmdb")]
        if not members:
            print("no .mmdb inside the archive")
            return 1
        with zf.open(members[0]) as src, open(target, "wb") as dst:
            shutil.copyfileobj(src, dst)

    # download_mmdb() stamps mtime as "last checked"; needs_update() reads it.
    os.utime(target)

    # Mark this source active so get_mmdb_path() resolves to it.
    save_geoip_config(config, explicit=True)

    print(f"installed: {target} ({target.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
