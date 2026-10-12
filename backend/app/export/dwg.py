"""DXF -> DWG through an external converter. DWG is Autodesk's proprietary format; there is no open writer we would trust, so the app
drives the free ODA File Converter if the user has installed it (https://www.opendesign.com/guestfiles/oda_file_converter, separate
download under ODA's terms; it is not bundled and not downloaded by this app).

Set TXT2CAD_ODA_CONVERTER to the converter .exe, or install it in the default location and it is found.
"""

from __future__ import annotations

import glob
import os
import subprocess
import tempfile
from pathlib import Path

from ..domain.spec import BuildingSpec
from .dxf import dxf_text

OUTPUT_VERSION = "ACAD2018"
TIMEOUT_S = 120
DEFAULT_GLOBS = (r"C:\Program Files\ODA\ODAFileConverter*\ODAFileConverter.exe", r"C:\Program Files (x86)\ODA\ODAFileConverter*\ODAFileConverter.exe")


class DwgUnavailable(RuntimeError):
    """The converter is missing or failed. The message tells the user what to do."""


def find_converter() -> str | None:
    env = os.environ.get("TXT2CAD_ODA_CONVERTER", "")
    if env and Path(env).is_file():
        return env
    for pattern in DEFAULT_GLOBS:
        hits = sorted(glob.glob(pattern))
        if hits:
            return hits[-1]
    return None


def dwg_bytes(spec: BuildingSpec) -> bytes:
    exe = find_converter()
    if exe is None:
        raise DwgUnavailable("DWG needs the free ODA File Converter, which is not installed. Install it, or set TXT2CAD_ODA_CONVERTER to its path. "
                             "The DXF opens in AutoCAD, BricsCAD and LibreCAD without it.")
    with tempfile.TemporaryDirectory() as tmp:
        src, out = Path(tmp, "in"), Path(tmp, "out")
        src.mkdir()
        out.mkdir()
        (src / "plan.dxf").write_bytes(dxf_text(spec).encode("utf-8"))      # bytes, so Windows does not rewrite the line endings
        try:
            # arguments: input folder, output folder, output version, output type, recurse, audit, input filter
            done = subprocess.run([exe, str(src), str(out), OUTPUT_VERSION, "DWG", "0", "1", "*.DXF"], capture_output=True, stdin=subprocess.DEVNULL, timeout=TIMEOUT_S, check=False,
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))   # never wait on our stdin, never flash a console
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise DwgUnavailable(f"the DWG converter could not run: {exc}") from exc
        produced = out / "plan.dwg"
        if not produced.is_file():
            tail = (done.stderr or done.stdout or b"").decode("utf-8", "replace")[-300:]
            raise DwgUnavailable(f"the DWG converter produced no file (exit {done.returncode}). {tail}".strip())
        return produced.read_bytes()
