# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```
pip install -r requirements.txt          # pandas, openpyxl, matplotlib (venv: .venv)
python run_mapping.py [input file or name] [--modules nlc,sales,vertical,live_lp,sell_int,liq,zone,brand_offer]
                      [--sales-mode day|avg|both] [--attr-source sales|liq|ipc] [--format xlsx|csv] [--start YYYY-MM-DD] [--end YYYY-MM-DD]
python new_task.py "<slug>"              # scaffold tasks/YYYY-MM-DD_<slug>/ (README.md + run.py)
```
No tests or linter are configured. Anything not passed on the command line is prompted for interactively (`ask()` in `run_mapping.py`); no input argument = numbered list of files in `MM_INPUT_DIR` (newest first, Enter = newest).

## Architecture

Windows-only tool that appends metric columns onto a user-supplied FSN list. All source data lives on a Google Drive path (`G:\.shortcut-targets-by-id\...\SMNM_Minutes`) defined once in `common/paths.py`; nothing is runnable without that drive mounted.

Flow (`run_mapping.py`):
1. `common.levels.load_input` reads the file, maps column aliases (`fsn/product id`, `SH/SH_P0`, `DS/store/business_zone`, `LID/listing_id`) to canonical names, and auto-detects level: `FSN | FSN_SH | FSN_DS | FSN_DS_LID`. Returns `(raw, keys, level)`.
2. For each selected module in `modules/` (`nlc`, `sales`, `vertical`, `live_lp`, `sell_int_qty`, `liq_qty`, `zone`, `brand_offer`): `run(unique_keys, level[, **opts]) -> (DataFrame, zero_fill_cols)`. The result is left-merged onto the keys on whichever key columns it shares; `zero_fill_cols` are `fillna(0)`ed (everything else stays NaN when unmatched).
3. New columns are concatenated to the original raw frame (original rows/columns/order preserved; `assert len(res) == len(raw)`), saved via `common.io_utils.save` as `<input>_mapped_<timestamp>_KS.xlsx|csv` (`save` appends `_KS` to every output name; format asked / `--format`, csv default above `CSV_ROWS`=200k, forced at ≥1M rows; csv is utf-8-sig).

Conventions to keep when adding/changing a module:
- Module `run` must return columns named after the key columns it supports; it's the module's job to roll source data up to the input level. `levels.agg_keys(level)` collapses `FSN_DS_LID` to `FSN_DS` because sales/liquidation have no LID granularity.
- Source files are picked "latest wins" via `levels.latest_file` / `date_key` (date parsed from filename as `YYYYMMDD` or trailing `DMonYY`, else mtime). `~$*` Excel lock files are skipped.
- `nlc.py` resolves per FSN with source priority Staples_nlc (newest) > `Category_WEEK*NLC*.xlsx` > `nlc_bizfin_*.csv`, stops reading older files once all FSNs resolve, and treats all NLC as tax-inclusive.
- Big CSVs are read through `common.progress.scan_csv` (chunked, prints %/ETA); call `progress.report` for non-chunked steps. Live LP output columns are prefixed `Live_`. Sales also returns `Product_Title`/`Vertical` (first value in file) and returns one row per input key.
- NLC logic mirrors `smnm_reporting/main.py` (`build_nlc_lookup`); keep them in sync.
- `zone.py` maps via latest `*_Zone_Mapper.csv`; `vertical.py` maps L1 via latest `*_Vertical_L1_Map.csv` and takes Vertical from input column > Sales module > sales file (`run_mapping` runs modules in `MODULES` order so vertical follows sales).
- `modules/product_info.py` fetches FSN→Product_Title/Vertical from the user-chosen source (sales | liq = latest `Liquidation_Raw_Data/ipc_DataSense_Dry_NPD_ds_npd_risk_*.csv` | ipc, asked at runtime / `--attr-source`); used by `sales.py` and `vertical.py`.
- `brand_offer.py` -> `ABs_BO`: latest `Brand_Offers_CN/*.xlsx`, day column = `run_date.day` (captured at start of `main`), Percentage rows x FSN `MRP_Avg` from `live_lp._run`, mean over cities incl. zeros.
- `Effective_NLC = NLC_w_tax - ABs_BO` is computed in `run_mapping.py` after all modules, only if both columns exist; `ABs_BO` / `Effective_NLC` are moved right after `NLC_w_tax`.
- DS→SH mapping comes from `levels.load_ds_sh()` (latest `*_DS_SH_Network_Master.csv` in `MAPPING_DIR`).

## Keeping docs in sync

Whenever pipeline logic changes, update every affected piece in the same change: all code that depends on it (modules, `run_mapping.py`, `common/`), module docstrings, `README.md` (the pipeline/modules tables) and this file.

## One-off tasks

`tasks/YYYY-MM-DD_<slug>/` hold historical BAU asks (history only, not part of the pipeline). Their `run.py` inserts the repo root in `sys.path` and imports from `common.io_utils`. `data/input|output` is git-ignored scratch space; `.xlsx`/`.csv` are also git-ignored.








