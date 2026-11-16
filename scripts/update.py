#!/usr/bin/env python3
"""Fetch latest Mark Six results and merge them into draws.txt.

Line format: 期數, 日期, 六個號碼, 特別號碼 | 備註(可選)
Existing lines (and their notes) are never overwritten; only new issues are added.
"""
import json, re, sys, urllib.request
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "draws.txt"
KEEP = 40
UA = {"User-Agent": "Mozilla/5.0 (compatible; mark6-updater/1.0)"}

QUERY = """query marksixResult($lastNDraw: Int, $drawType: LotteryDrawType) {
  lotteryDraws(lastNDraw: $lastNDraw, drawType: $drawType) {
    id year no drawDate snowballName_ch
    drawResult { drawnNo xDrawnNo }
  }
}"""


def from_hkjc(n=10):
    body = json.dumps({"operationName": "marksixResult", "query": QUERY,
                       "variables": {"lastNDraw": n, "drawType": "All"}}).encode()
    req = urllib.request.Request("https://info.cld.hkjc.com/graphql/base/", data=body,
                                 headers={**UA, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return parse_hkjc(json.load(r))


def parse_hkjc(payload):
    out = []
    for d in payload["data"]["lotteryDraws"]:
        res = d.get("drawResult")
        if not res or not res.get("drawnNo"):
            continue
        main = sorted(int(x) for x in res["drawnNo"])
        x = res.get("xDrawnNo")
        sp = int(x[0] if isinstance(x, list) else x)
        if len(main) != 6:
            continue
        issue = "%02d/%03d" % (int(d["year"]) % 100, int(d["no"]))
        out.append({"issue": issue, "date": str(d["drawDate"])[:10], "main": main, "sp": sp,
                    "note": (d.get("snowballName_ch") or "").strip()})
    return out


def from_fallback():
    req = urllib.request.Request("https://lottery.hk/en/mark-six/results/", headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        html = r.read().decode("utf-8", "ignore")
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
    out = []
    for m in re.finditer(r"(\d{2}/\d{3}) (\d{2})/(\d{2})/(\d{4}) ((?:\d{1,2} ){6}\d{1,2})(?!\d)", text):
        nums = [int(v) for v in m.group(5).split()]
        out.append({"issue": m.group(1), "date": "%s-%s-%s" % (m.group(4), m.group(3), m.group(2)),
                    "main": sorted(nums[:6]), "sp": nums[6], "note": ""})
    return out


def line_of(d):
    s = "%s, %s, %s, %d" % (d["issue"], d["date"], " ".join(map(str, d["main"])), d["sp"])
    return s + (" | " + d["note"] if d["note"] else "")


def merge(existing_lines, new):
    have = {}
    for ln in existing_lines:
        m = re.match(r"\s*(\d{2}/\d{2,3})", ln)
        if m:
            have[m.group(1)] = ln.strip()
    added = []
    for d in new:
        if d["issue"] not in have:
            have[d["issue"]] = line_of(d)
            added.append(d["issue"])
    def key(ln):
        m = re.search(r"\d{4}-\d{2}-\d{2}", ln)
        return m.group(0) if m else ""
    lines = sorted(have.values(), key=key, reverse=True)[:KEEP]
    return lines, added


def main():
    new = []
    for name, fn in (("HKJC", from_hkjc), ("lottery.hk", from_fallback)):
        try:
            new = fn()
            if new:
                print("source:", name, "->", len(new), "draws")
                break
        except Exception as e:
            print("source %s failed: %r" % (name, e), file=sys.stderr)
    if not new:
        print("ERROR: no results from any source", file=sys.stderr)
        sys.exit(1)
    old = DATA.read_text(encoding="utf-8").splitlines() if DATA.exists() else []
    lines, added = merge(old, new)
    if not added:
        print("no new draw")
        return
    DATA.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("added:", ", ".join(added))


if __name__ == "__main__":
    main()
