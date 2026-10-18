"""Run the evaluation cases through the real pipeline and score each result.

    python -m evals.run                       offline model (a smoke test: it can only do the simple cases)
    python -m evals.run --live                Gemini (needs GEMINI_API_KEY; about 1.6 cents and 30 s a case)
    python -m evals.run --live --only h1,s1   some cases;  --category sizes;  --repeat 3

Results go to evals/results/<time>-<mode>.json and a table is printed. The run uses a throwaway database.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from app.domain.design import Design  # noqa: E402
from evals.score import score, verdict  # noqa: E402


def load_cases() -> list[dict]:
    return json.loads((HERE / "prompts.json").read_text(encoding="utf-8"))


def events(resp) -> list[dict]:
    return [json.loads(line[5:]) for line in resp.iter_lines() if line.startswith("data:")]


def run_case(client, profile_id: str | None, case: dict) -> dict:
    pid = client.post("/api/projects", json={"name": case["id"]}).json()["id"]
    base_design = None
    started = time.time()
    if case.get("base"):
        with client.stream("POST", f"/api/projects/{pid}/runs", json={"prompt": case["base"], "profile_id": profile_id}) as r:
            base_evs = events(r)
        if base_evs[-1]["stage"] != "finished":
            return {"id": case["id"], "category": case["category"], "prompt": case["prompt"], "seconds": round(time.time() - started, 1), "pass": False, "score": 0.0,
                    "failed": [{"name": "the starting building", "ok": False, "detail": base_evs[-1]["message"][:200]}], "error": "base failed"}
        base_design = Design.model_validate(client.get(f"/api/projects/{pid}").json()["head"]["design"])
    body: dict = {"prompt": case["prompt"], "profile_id": profile_id}
    if base_design is not None:
        body["base_version"] = client.get(f"/api/projects/{pid}").json()["head"]["number"]
    with client.stream("POST", f"/api/projects/{pid}/runs", json=body) as r:
        evs = events(r)
    seconds = round(time.time() - started, 1)
    last = evs[-1]
    rejected = sum(1 for e in evs if e["stage"] == "move" and not e["data"].get("ok", True))
    result = {"id": case["id"], "category": case["category"], "prompt": case["prompt"], "seconds": seconds, "rejected_steps": rejected, "end": last["stage"]}
    head = client.get(f"/api/projects/{pid}").json().get("head")
    saved = last["stage"] == "finished" and head is not None
    design = Design.model_validate(head["design"]) if saved else None
    if not saved:
        result["error"] = last["message"][:240]
    if design is not None:
        result["rooms"] = [f"{r.name} ({r.kind}, {r.level}, {r.rect[2]:g}x{r.rect[3]:g})" for r in design.rooms]
        result["added_automatically"] = [n for n in head["notes"] if n.startswith("added a ")]
        result["design"] = design.model_dump()                       # kept so a failed case can be looked at and run again by hand
    cks = score(design, case, saved=saved, notes=head["notes"] if saved else [], requirements=head["requirements"] if saved else [], base=base_design)
    result.update(verdict(cks))
    result["checks"] = cks
    return result


def summarise(results: list[dict]) -> dict:
    cats: dict[str, list[dict]] = {}
    for r in results:
        cats.setdefault(r["category"], []).append(r)
    secs = sorted(r["seconds"] for r in results)
    return {
        "cases": len(results), "passed": sum(1 for r in results if r["pass"]), "mean_score": round(statistics.mean(r["score"] for r in results), 3) if results else 0,
        "saved": sum(1 for r in results if r.get("end") == "finished"),
        "seconds_median": secs[len(secs) // 2] if secs else 0, "seconds_p90": secs[int(len(secs) * 0.9) - 1] if secs else 0,
        "by_category": {c: {"passed": sum(1 for r in rs if r["pass"]), "of": len(rs)} for c, rs in cats.items()},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="use Gemini instead of the offline model")
    ap.add_argument("--only", help="comma-separated case ids")
    ap.add_argument("--category")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--out")
    args = ap.parse_args()

    tmp = Path(tempfile.mkdtemp())
    os.environ["TXT2CAD_DATA_DIR"] = str(tmp)
    os.environ["TXT2CAD_DB_PATH"] = str(tmp / "eval.sqlite3")
    from fastapi.testclient import TestClient

    from app.main import create_app

    cases = load_cases()
    if args.only:
        wanted = set(args.only.split(","))
        cases = [c for c in cases if c["id"] in wanted]
    if args.category:
        cases = [c for c in cases if c["category"] == args.category]
    cases = [c for c in cases if args.live or c.get("mock", False) or args.only]
    mode = "live" if args.live else "offline"
    results: list[dict] = []
    with TestClient(create_app()) as client:
        profiles = client.get("/api/llm/profiles").json()
        name = "Gemini" if args.live else "Practice mode"
        profile = next(p for p in profiles if p["name"] == name)
        if not profile["ready"]:
            print(f"{name} is not ready (is GEMINI_API_KEY set?)", file=sys.stderr)
            return 2
        for rep in range(args.repeat):
            for case in cases:
                r = run_case(client, profile["id"], case)
                r["repeat"] = rep + 1
                results.append(r)
                bad = "; ".join(f"{c['name']} ({c['detail']})" if c["detail"] else c["name"] for c in r["failed"])
                print(f"{'PASS' if r['pass'] else 'FAIL'} {r['id']:<4} {r['category']:<13} {r['seconds']:>6.1f}s  {r['score']:.2f}  {bad[:140]}", flush=True)
    summary = summarise(results)
    out = Path(args.out) if args.out else HERE / "results" / f"{datetime.now():%Y%m%d-%H%M%S}-{mode}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"mode": mode, "when": datetime.now().isoformat(timespec="seconds"), "summary": summary, "results": results}, indent=1), encoding="utf-8")
    print(f"\n{summary['passed']} of {summary['cases']} passed, mean score {summary['mean_score']}, median {summary['seconds_median']} s, p90 {summary['seconds_p90']} s")
    for c, v in summary["by_category"].items():
        print(f"  {c:<14} {v['passed']} of {v['of']}")
    print(f"results: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
