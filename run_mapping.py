"""Map metrics onto an input FSN list. Level auto-detected from columns:
FSN | FSN x SH | FSN x DS | FSN x DS x LID (column names: fsn, SH/SH_P0, DS/store, LID/listing_id).

  python run_mapping.py <input.xlsx|csv> [--modules nlc,sales,vertical,live_lp,sell_int,liq,zone,brand_offer]
                        [--sales-mode day|avg|both] [--start YYYY-MM-DD] [--end YYYY-MM-DD]
Anything not given on the command line is asked for (incl. which input file).
Input: SMNM_Minutes/Master Mapper/Input Files. Output: Master Mapper/Output Files/<input>_mapped_<time>.xlsx|csv
Original rows/columns/order are kept; new columns are appended."""
import argparse
from datetime import datetime
from pathlib import Path
import pandas as pd
from common import progress
from common.io_utils import save
from common.levels import load_input, latest_file
from common.paths import MM_INPUT_DIR, MM_OUTPUT_DIR
from modules.product_info import SOURCES as ATTR_SOURCES
from modules import nlc, sales, live_lp, sell_int_qty, liq_qty, zone, vertical, brand_offer

CSV_ROWS = 200_000  # above this, csv is the default output (xlsx writing is slow/large)

MODULES = {
    "nlc": "NLC",
    "sales": "Sales (day-wise / average Units, GMV, LP)",
    "vertical": "Vertical -> L1 (Foods / Staples / Non-Foods)",
    "live_lp": "Live LP (incl. MRP)",
    "sell_int": "Sell Intervention Qty",
    "liq": "Liquidation Qty",
    "zone": "Zone (from Zone Mapper)",
    "brand_offer": "Brand Offer CN (ABs_BO)",
}


def ask(prompt, default=None, choices=None):
    while True:
        v = input(f"{prompt}{f' [{default}]' if default else ''}: ").strip() or (default or "")
        if v and (not choices or v in choices):
            return v


def main():
    run_date = datetime.now()  # brand-offer day column = day of month when the run began
    ap = argparse.ArgumentParser()
    ap.add_argument("input", nargs="?", help="file path, or a file name inside Master Mapper/Input Files "
                                             "(blank = pick from a numbered list)")
    ap.add_argument("--modules")
    ap.add_argument("--sales-mode", choices=["day", "avg", "both"])
    ap.add_argument("--start")
    ap.add_argument("--end")
    ap.add_argument("--format", choices=["xlsx", "csv"], help="output format (default: asked; csv suggested for big data)")
    ap.add_argument("--attr-source", choices=list(ATTR_SOURCES),
                    help="where Product_Title / Vertical are mapped from: sales | liq | ipc")
    a = ap.parse_args()

    if a.input and Path(a.input).exists():
        inp = Path(a.input)
    elif a.input:
        inp = MM_INPUT_DIR / a.input
    else:
        files = sorted((p for p in MM_INPUT_DIR.glob("*.[xc][ls][sv]*") if not p.name.startswith("~$")),
                       key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            raise SystemExit(f"No input files in {MM_INPUT_DIR}")
        print("Input files (newest first):")
        for i, p in enumerate(files, 1):
            print(f"  {i}. {p.name}  ({datetime.fromtimestamp(p.stat().st_mtime):%d-%b %H:%M})")
        pick = ask("Which input file? (number)", "1", [str(i) for i in range(1, len(files) + 1)])
        inp = files[int(pick) - 1]
    print("Input file:", inp)
    raw, keys, level = load_input(inp)
    print(f"Input: {len(raw):,} rows | level: {level}")
    if a.modules:
        mods = [m.strip() for m in a.modules.split(",")]
    else:
        names = list(MODULES)
        for i, (k, v) in enumerate(MODULES.items(), 1):
            print(f"  {i}. {v}")
        print(f"  {len(names) + 1}. All of the above")
        sel = ask("What do you want to map? (numbers, comma separated, e.g. 1,3)", str(len(names) + 1))
        picks = [x.strip() for x in sel.split(",")]
        mods = names if str(len(names) + 1) in picks or "all" in picks else [
            names[int(x) - 1] if x.isdigit() and 1 <= int(x) <= len(names) else x for x in picks]
    bad = [m for m in mods if m not in MODULES]
    if bad:
        raise SystemExit(f"Unknown module(s): {bad}")

    mods = [m for m in MODULES if m in mods]  # fixed order: vertical runs after sales
    vcol = next((c for c in raw.columns if str(c).strip().lower() == "vertical"), None)
    attr_src = "sales"
    if "sales" in mods or ("vertical" in mods and vcol is None):
        for k, v in ATTR_SOURCES.items():
            print(f"  {k}: {v}")
        attr_src = a.attr_source or ask("Map Product_Title / Vertical from which file? (sales/liq/ipc)", "sales", list(ATTR_SOURCES))
    opts = {}
    if "sales" in mods:
        mode = a.sales_mode or ask("Sales: day-wise, average or both? (day/avg/both)", "both", ["day", "avg", "both"])
        opts = dict(mode=mode, attr_source=attr_src, start=a.start or ask("Sales start date YYYY-MM-DD (blank = last 7 days of file)", "last7") ,
                    end=a.end or ask("Sales end date YYYY-MM-DD (blank = latest in file)", "latest"))
        opts["start"] = None if opts["start"] == "last7" else opts["start"]
        opts["end"] = None if opts["end"] == "latest" else opts["end"]

    uniq = keys.drop_duplicates()
    res = keys.copy()
    progress.start(len(mods))
    for i, m in enumerate(mods, 1):
        progress.step(i)
        print(f"\n== [{i}/{len(mods)}] {m}", flush=True)
        if m == "nlc":
            t, zero = nlc.run(uniq, level)
        elif m == "sales":
            t, zero = sales.run(uniq, level, **opts)
        elif m == "vertical":
            if vcol is not None:  # input already has Vertical: use it
                known = pd.DataFrame({"fsn": keys.fsn, "Vertical": raw[vcol].values})
            elif "Vertical" in res.columns:  # Sales ran earlier
                known = pd.DataFrame({"fsn": res.fsn, "Vertical": res.Vertical})
            else:
                known = None
            t, zero = vertical.run(uniq, level, known, attr_src)
        elif m == "live_lp":
            t, zero = live_lp.run(uniq, level)
        elif m == "sell_int":
            t, zero = sell_int_qty.run(uniq, level)
        elif m == "brand_offer":
            t, zero = brand_offer.run(uniq, level, run_date)
        elif m == "zone":
            t, zero = zone.run(uniq, level)
        else:
            t, zero = liq_qty.run(uniq, level)
        on = [c for c in keys.columns if c in t.columns]
        new = [c for c in t.columns if c not in keys.columns]
        res = res.merge(t[on + new].drop_duplicates(on), on=on, how="left")
        for c in zero:
            res[c] = res[c].fillna(0)
        progress.report(f"{m} complete")
        print("   " + (
            f"+{len(new)} columns | matched rows: {res[new[0]].notna().sum():,} of {len(res):,}" if new else "nothing matched"), flush=True)

    if {"NLC_w_tax", "ABs_BO"} <= set(res.columns):  # derived column: needs both nlc and brand_offer
        res["Effective_NLC"] = res.NLC_w_tax - res.ABs_BO  # blank where NLC is missing
    if "NLC_w_tax" in res.columns:  # keep NLC, ABs_BO and Effective_NLC side by side
        side = [c for c in ("ABs_BO", "Effective_NLC") if c in res.columns]
        rest = [c for c in res.columns if c not in side]
        i = rest.index("NLC_w_tax") + 1
        res = res[rest[:i] + side + rest[i:]]
    print("\nWriting output file...", flush=True)
    assert len(res) == len(raw)
    out = pd.concat([raw.reset_index(drop=True), res.drop(columns=[c for c in keys.columns]).reset_index(drop=True)], axis=1)
    fmt = a.format or ask(f"Output format? (xlsx/csv; csv recommended above {CSV_ROWS:,} rows)", "csv" if len(out) > CSV_ROWS else "xlsx", ["xlsx", "csv"])
    if fmt == "xlsx" and len(out) >= 1_000_000:
        print("Over Excel's 1M row limit -> writing csv"); fmt = "csv"
    name = f"{inp.stem}_mapped_{datetime.now():%Y%m%d_%H%M}.{fmt}"
    print("\nSaved:", save(out, name, MM_OUTPUT_DIR))


if __name__ == "__main__":
    main()









