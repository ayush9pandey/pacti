"""Fetch official Cello examples and convert one gate response to Pacti contracts.

Usage examples
--------------
# 1) Fetch official Cello repo snapshot into examples/_external
python examples/cello_official_to_contracts.py fetch --dest examples/_external

# 2) List UCF-like JSON files discovered in fetched repo
python examples/cello_official_to_contracts.py list --cello-root examples/_external/cello

# 3) Build M0 contracts for one gate from one official UCF file
PYTHONPATH=src python examples/cello_official_to_contracts.py build \
  --ucf-path examples/_external/cello/<path-to-ucf>.json \
  --gate-name <gate_name> \
  --segments 4
"""

from __future__ import annotations

import argparse
import io
import json
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List

import numpy as np

from pacti.contracts import PolyhedralIoContract

CELLO_ZIP_URL = "https://codeload.github.com/CIDARLAB/cello/zip/refs/heads/master"


@dataclass
class SegmentContract:
    x_lo: float
    x_hi: float
    y_lo: float
    y_hi: float
    contract: PolyhedralIoContract


def fetch_official_cello_repo(dest_dir: Path) -> Path:
    """Download official Cello repo snapshot and extract into dest_dir/cello."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(CELLO_ZIP_URL, timeout=60) as resp:
        payload = resp.read()

    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        zf.extractall(dest_dir)

    extracted = sorted(dest_dir.glob("cello-*"))
    if not extracted:
        raise RuntimeError("Could not find extracted cello-* directory")

    cello_root = dest_dir / "cello"
    if cello_root.exists():
        # clean previous extraction result
        for p in sorted(cello_root.rglob("*"), reverse=True):
            if p.is_file() or p.is_symlink():
                p.unlink()
            elif p.is_dir():
                p.rmdir()
        cello_root.rmdir()

    extracted[0].rename(cello_root)
    return cello_root


def _find_gate_records(obj: Any) -> List[Dict[str, Any]]:
    records = []
    if isinstance(obj, dict):
        keys = set(obj.keys())
        if {"name", "ymin", "ymax", "K", "n"}.issubset(keys):
            records.append(obj)
        for v in obj.values():
            records.extend(_find_gate_records(v))
    elif isinstance(obj, list):
        for item in obj:
            records.extend(_find_gate_records(item))
    return records


def _json_files(root: Path) -> Iterable[Path]:
    yield from root.rglob("*.json")


def discover_ucf_like_json_files(cello_root: Path) -> List[Path]:
    hits: List[Path] = []
    for p in _json_files(cello_root):
        try:
            obj = json.loads(p.read_text())
        except Exception:
            continue
        if _find_gate_records(obj):
            hits.append(p)
    return sorted(hits)


def load_gate_from_ucf_json(path: Path, gate_name: str) -> Dict[str, float]:
    data = json.loads(path.read_text())
    candidates = _find_gate_records(data)
    for rec in candidates:
        if rec.get("name") == gate_name:
            return {
                "name": str(rec["name"]),
                "ymin": float(rec["ymin"]),
                "ymax": float(rec["ymax"]),
                "K": float(rec["K"]),
                "n": float(rec["n"]),
            }
    names = sorted({str(r.get("name")) for r in candidates if "name" in r})
    raise ValueError(f"Gate {gate_name!r} not found in {path}. Available names: {names[:20]}")


def hill_not_response(x: np.ndarray, *, ymin: float, ymax: float, K: float, n: float) -> np.ndarray:
    return ymin + (ymax - ymin) / (1.0 + (x / K) ** n)


def build_piecewise_sound_contracts(
    gate: Dict[str, float],
    x_var: str,
    y_var: str,
    x_min: float,
    x_max: float,
    num_segments: int = 4,
) -> List[SegmentContract]:
    edges = np.linspace(x_min, x_max, num_segments + 1)
    segs: List[SegmentContract] = []

    for i in range(num_segments):
        a = float(edges[i])
        b = float(edges[i + 1])
        fa = float(hill_not_response(np.array([a]), **{k: gate[k] for k in ["ymin", "ymax", "K", "n"]})[0])
        fb = float(hill_not_response(np.array([b]), **{k: gate[k] for k in ["ymin", "ymax", "K", "n"]})[0])
        y_lo = min(fa, fb)
        y_hi = max(fa, fb)

        c = PolyhedralIoContract.from_strings(
            input_vars=[x_var],
            output_vars=[y_var],
            assumptions=[f"{x_var} <= {b}", f"-{x_var} <= {-a}"],
            guarantees=[f"{y_var} <= {y_hi}", f"-{y_var} <= {-y_lo}"],
        )
        segs.append(SegmentContract(a, b, y_lo, y_hi, c))

    return segs


def validate_enclosure(gate: Dict[str, float], segments: List[SegmentContract], n_per_segment: int = 5000) -> None:
    params = {k: gate[k] for k in ["ymin", "ymax", "K", "n"]}
    for idx, s in enumerate(segments, start=1):
        xs = np.linspace(s.x_lo, s.x_hi, n_per_segment)
        ys = hill_not_response(xs, **params)
        ok = np.all((ys >= s.y_lo - 1e-12) & (ys <= s.y_hi + 1e-12))
        if not ok:
            raise AssertionError(f"Segment {idx} failed enclosure")


def cmd_fetch(args: argparse.Namespace) -> int:
    try:
        root = fetch_official_cello_repo(Path(args.dest))
    except urllib.error.URLError as exc:
        print(f"Failed to fetch official Cello repo from {CELLO_ZIP_URL}")
        print(f"Reason: {exc}")
        print("Hint: run this command in an environment with GitHub network access.")
        return 2
    print(f"Fetched official Cello repo to: {root}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    hits = discover_ucf_like_json_files(Path(args.cello_root))
    if not hits:
        print("No UCF-like JSON files found.")
        return 1
    print("UCF-like JSON files containing gate response parameters:")
    for p in hits:
        print(p)
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    gate = load_gate_from_ucf_json(Path(args.ucf_path), args.gate_name)
    segments = build_piecewise_sound_contracts(
        gate=gate,
        x_var=args.input_var,
        y_var=args.output_var,
        x_min=args.x_min,
        x_max=args.x_max,
        num_segments=args.segments,
    )
    validate_enclosure(gate, segments, n_per_segment=args.validation_points)

    print(f"Gate: {gate['name']} from {args.ucf_path}")
    for i, s in enumerate(segments, start=1):
        print(f"\n=== Segment {i} ===")
        print(f"x in [{s.x_lo}, {s.x_hi}], y in [{s.y_lo}, {s.y_hi}]")
        print(s.contract)

    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Fetch official Cello examples and build Pacti contracts")
    sub = p.add_subparsers(dest="command", required=True)

    p_fetch = sub.add_parser("fetch", help="Download official Cello repo snapshot")
    p_fetch.add_argument("--dest", default="examples/_external", help="Extraction parent directory")
    p_fetch.set_defaults(func=cmd_fetch)

    p_list = sub.add_parser("list", help="List discovered UCF-like JSON files")
    p_list.add_argument("--cello-root", required=True, help="Path to extracted official Cello repo root")
    p_list.set_defaults(func=cmd_list)

    p_build = sub.add_parser("build", help="Build contracts from one official UCF JSON gate")
    p_build.add_argument("--ucf-path", required=True, help="Path to official Cello UCF JSON")
    p_build.add_argument("--gate-name", required=True, help="Gate name present in UCF file")
    p_build.add_argument("--input-var", default="x_in")
    p_build.add_argument("--output-var", default="x_out")
    p_build.add_argument("--x-min", type=float, default=1e-3)
    p_build.add_argument("--x-max", type=float, default=1e3)
    p_build.add_argument("--segments", type=int, default=4)
    p_build.add_argument("--validation-points", type=int, default=5000)
    p_build.set_defaults(func=cmd_build)

    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
