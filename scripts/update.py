#!/usr/bin/env python3
"""Fetch latest Mark Six results and merge them into draws.txt.

Line format: 期數, 日期, 六個號碼, 特別號碼 | 備註(可選)
Existing lines (and their notes) are never overwritten; only new issues are added.
"""
import json, re, sys, urllib.request
from datetime import date, datetime, timedelta, timezone
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


NEXT_Q = """query nextDraw($n: Int) {
  lotteryDraws(lastNDraw: $n, drawType: All) {
    year no drawDate closeDate snowballName_ch
    lotteryPool { jackpot estimatedPrize }
  }
}"""


def to_int(v):
    try:
        v = int(float(v))
        return v if v > 0 else None
    except (TypeError, ValueError):
        return None


def fetch_next_hkjc(last_key):
    """Best-effort: look for a draw newer than the last known result."""
    body = json.dumps({"operationName": "nextDraw", "query": NEXT_Q.replace("drawType: All", "drawType: All"),
                       "variables": {"n": 5}}).encode()
    req = urllib.request.Request("https://info.cld.hkjc.com/graphql/base/", data=body,
                                 headers={**UA, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.load(r)
    best = None
    for d in payload["data"]["lotteryDraws"]:
        key = (int(d["year"]) % 100, int(d["no"]))
        if key > last_key and (best is None or key < best[0]):
            best = (key, d)
    if not best:
        return None
    key, d = best
    pool = d.get("lotteryPool") or {}
    close = str(d.get("closeDate") or "")
    return {"issue": "%02d/%03d" % key, "date": str(d["drawDate"])[:10],
            "cutoff": close[11:16] if len(close) >= 16 else "21:15",
            "jackpot": to_int(pool.get("estimatedPrize")), "snowball": None,
            "snowballName": (d.get("snowballName_ch") or "").strip()}


def computed_next(lines):
    m = re.match(r"\s*(\d{2})/(\d{2,3}),\s*(\d{4})-(\d{2})-(\d{2})", lines[0])
    yy, no = int(m.group(1)), int(m.group(2))
    last = date(int(m.group(3)), int(m.group(4)), int(m.group(5)))
    nd = last + timedelta(days=1)
    while nd.weekday() not in (1, 3, 5):      # Tue, Thu, Sat
        nd += timedelta(days=1)
    if nd.year != last.year:
        yy, no = nd.year % 100, 0
    return {"issue": "%02d/%03d" % (yy, no + 1), "date": nd.isoformat(), "cutoff": "21:15",
            "jackpot": None, "snowball": None, "snowballName": ""}


def build_next(lines, prev):
    nxt = computed_next(lines)
    m = re.match(r"\s*(\d{2})/(\d{2,3})", lines[0])
    try:
        got = fetch_next_hkjc((int(m.group(1)), int(m.group(2))))
        if got:
            nxt.update({k: v for k, v in got.items() if v not in (None, "")})
            print("next draw from HKJC:", got)
    except Exception as e:
        print("next-draw lookup failed: %r" % (e,), file=sys.stderr)
    # keep old jackpot only if it is still the same draw
    if prev and prev.get("issue") == nxt["issue"]:
        for k in ("jackpot", "snowball", "snowballName"):
            if nxt.get(k) in (None, "") and prev.get(k) not in (None, ""):
                nxt[k] = prev[k]
    stamp = (datetime.now(timezone(timedelta(hours=8)))).date().isoformat()
    base = {k: v for k, v in (prev or {}).items() if k != "updated"}
    nxt["updated"] = prev["updated"] if prev and base == nxt else stamp
    return nxt


def read_prev(text):
    m = re.search(r"^#\s*next\s*(\{.*\})\s*$", text, re.M)
    try:
        return json.loads(m.group(1)) if m else None
    except ValueError:
        return None


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
    text = DATA.read_text(encoding="utf-8") if DATA.exists() else ""
    lines, added = merge(text.splitlines(), new)
    nxt = build_next(lines, read_prev(text))
    content = "# next " + json.dumps(nxt, ensure_ascii=False, separators=(",", ":")) + "\n" + "\n".join(lines) + "\n"
    if content == text:
        print("no change")
        return
    DATA.write_text(content, encoding="utf-8")
    print("added:", ", ".join(added) if added else "(none, next-draw info updated)")


if __name__ == "__main__":
    main()
