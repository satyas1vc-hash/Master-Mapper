# Master Mapper Project

Map metrics (NLC, Sales [Units/GMV/LP + Product Title/Vertical], Live LP [incl. MRP], Sell Intervention Qty, Liquidation Qty, Vertical L1, Zone, Brand Offer) onto an input FSN list.

## Run
```
python run_mapping.py [input file or name] [--modules nlc,sales,vertical,live_lp,sell_int,liq,zone,brand_offer]
                      [--sales-mode day|avg|both] [--attr-source sales|liq|ipc] [--start YYYY-MM-DD] [--end YYYY-MM-DD]
```
- Input: `SMNM_Minutes/Master Mapper/Input Files` (no argument = numbered list of files there, newest first; Enter = newest). `.xlsx/.xls/.xlsm/.csv`, first sheet, headers in row 1.
- Output: `SMNM_Minutes/Master Mapper/Output Files/<input>_mapped_<time>_KS.xlsx|csv`. Format is asked (`--format xlsx|csv`); default is csv above 200,000 rows, else xlsx; always csv at >= 1M rows (Excel limit). CSV is UTF-8 with BOM so Excel opens it cleanly. Every file written via `common.io_utils.save` gets the `_KS` suffix.
- Anything not given on the command line is asked: input file (if not passed), module menu (1 NLC, 2 Sales, 3 Live LP, 4 Sell Intervention, 5 Liquidation, 6 All), then for Sales: day/avg/both and start/end dates.
- Progress: every chunked file scan prints `% of file | step i/N | overall % | elapsed | ETA` (overall ETA weights modules equally, so it is approximate).

## Pipeline
1. **Load input** (`common/levels.py`): header aliases are case-insensitive; level is auto-detected.

   | Level | Columns | Aliases |
   |---|---|---|
   | FSN | fsn | fsn, product id, product_id |
   | FSN x SH | + SH | sh, sh_p0, shp0, sh p0 |
   | FSN x DS | + DS | ds, store, store_id, business_zone |
   | FSN x DS x LID | + DS + LID | lid, listing_id, listing id |

   DS wins over SH if both exist. LID without DS is an error. Keys are trimmed and read as text.
2. **Run selected modules** on the unique input keys. Each returns a table that is left-merged onto the input by the key columns it shares. Unmatched rows are blank, except the zero-filled columns noted below.
3. **Append** the new columns to the original input (rows, columns and order unchanged) and save.

Large source CSVs are read in chunks and filtered to the requested FSNs (and DS/LID where applicable). Excel sources and the input file are read whole.

## Modules (columns added)
| Module | Columns | Logic |
|---|---|---|
| NLC | `NLC_w_tax` | Same logic and file priority as `smnm_reporting/main.py`: newest `Staples_nlc/*.xlsx` > `Category_WEEK*NLC*.xlsx` (latest week/version first) > `nlc_bizfin_*.csv` (latest first). First file containing the FSN wins; reading stops once all FSNs are resolved. All NLC is treated as tax-inclusive (excl-tax value used as is when incl is blank); values <= 0 are missing; duplicate rows per FSN are averaged. FSN-level, so the same at every input level. `Tax_Pct` is not output. |
| Sales | `Product_Title`, `Vertical`, then per `--sales-mode`: `Units_<dd-Mon>`, `GMV_<dd-Mon>`, `LP_<dd-Mon>` (day) and/or `Avg_Units`, `Avg_GMV`, `Avg_LP` (avg) | Latest `Sales_FSN_DS_*.csv`. Window = start..end (default: last 7 days up to the file's end date). Units/GMV = sum; LP = sum(LP_Sum) / sum(units). Avg = window total / days in window (no-sale days count as 0). Units/GMV columns are zero-filled; LP is blank when there are no sales. Title and Vertical come from a source chosen at runtime (`--attr-source sales|liq|ipc`, asked if omitted): sales file (`title`, `analytic_vertical`), liquidation raw file = latest `Liquidation_Raw_Data/ipc_DataSense_Dry_NPD_ds_npd_risk_*.csv` (`product_title`, `analytic_vertical`) or IPC raw file (`title`, `vertical`) via `modules/product_info.py`. First non-blank value for the FSN anywhere in the file (so FSNs with zero sales still map when the liquidation/IPC source has them). FSN x DS x LID uses the FSN x DS value. FSN x SH rolls DS up using the DS->SH map. |
| Vertical | `L1` (+ `Product_Title`, `Vertical` if not in input / Sales) | Latest `*_Vertical_L1_Map.csv` (Vertical -> Foods/Staples/Non-Foods). Vertical comes from the input's `Vertical` column, else the Sales module, else the chosen `--attr-source` file. Unmapped verticals stay blank. Runs after Sales. |
| Zone | `Zone`, `Pricing_Tagging` | Latest `*_Zone_Mapper.csv`, upper-cased. FSN x DS (x LID): values of the DS. FSN x SH: SH's most common value. Skipped for FSN level. |
| Brand Offer | `ABs_BO` | Latest `Brand_Offers_CN/*.xlsx` (by month in name, then `_V<n>`), Sheet1. Takes the day column = day of month on the run start date (warns if the file is for another month). Per FSN x City row: `Abs` = value as is; `Percentage` = value x FSN's `Live_MRP_Avg` (mean MRP over all live listings, latest Live_Prices file; extra scan of that file). `ABs_BO` = plain mean over the FSN's city rows, zeros included. FSN-level at every input level; FSNs with no BO found (not in the file, or no usable value) get 0. |
| (derived) | `Effective_NLC` | `NLC_w_tax - ABs_BO`, added when both the NLC and Brand Offer modules are selected; `ABs_BO` and `Effective_NLC` are placed right after `NLC_w_tax`; blank where NLC is missing. |
| Live LP | all prefixed `Live_` | Latest `*Live_Prices_Minutes.csv` (on a date tie, the `MRP_` variant). FSN x DS x LID: that listing's `Live_LP`, `Live_Anchor_Price`, `Live_MRP`. Other levels, over all live listings of the FSN in the SH / DS / all: `Live_LID_Count`, `Live_LP_Average`, `Live_LP_Min`, `Live_LP_Median`, `Live_Anchor_Price_Avg`, `Live_Anchor_Price_Min`, `Live_MRP_Avg`, `Live_MRP_Median`. MRP is mapped only here, not in Sales. |
| Sell Intervention | `Sell_Int_Qty` | Latest `*_ipc_DataSense_Dry_SMNM-Summary_SMNM_Summary.csv`. FSN x DS: the DS value. FSN x SH: sum over DS using the file's own `sh_p0`. FSN: sum over all DS. Skipped for FSN x DS x LID. |
| Liquidation | `Liq_Total_Risk_ATP`, `Liq_Risk_ATP_0_3d`, `_4_7d`, `_8_15d`, `_16_31d` | Latest `*_liquidation_output_sales_*.csv` (header on row 4). Sum rollup; FSN x DS x LID uses the FSN x DS value. |

Latest-file rule (`levels.date_key`): date in the filename (`YYYYMMDD`, else the last `DMonYY`, else `_MonYY` as the 1st of the month), then modified time. `~$*` lock files are skipped. DS->SH comes from the latest `*_DS_SH_Network_Master.csv`; DS codes missing from it get no SH-level values.

## Layout
- `run_mapping.py` - entry point (menu, merge, save)
- `modules/` - one script per metric (`product_info` helper, `nlc`, `sales`, `vertical`, `live_lp`, `sell_int_qty`, `liq_qty`, `zone`)
- `common/` - paths, level detection, DS->SH map, latest-file picking, I/O, progress
- `tasks/YYYY-MM-DD_<slug>/` - earlier one-off BAU asks (history)
- `new_task.py` - scaffolds a one-off task folder
- `data/input|output` - scratch data for one-off tasks (git-ignored)











