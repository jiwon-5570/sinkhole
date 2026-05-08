# Public File Data

Put downloaded public-data files here. Raw data files are ignored by Git so large CSV/XLSX/ZIP files do not get committed.

## MOLIT Ground Information

Layer CSV:

```text
Project/backend/data/raw/public/molit_ground_layers/
```

Put the downloaded `국토교통부_지반정보_지층정보_*.csv` file in that folder.

The borehole dataset is collected through the approved OpenAPI with `PUBLIC_DATA_API_KEY`, so you usually do not need to place a borehole CSV manually.

Fallback borehole CSV:

```text
Project/backend/data/raw/public/molit_boreholes/
```

Use that folder only if the OpenAPI is unavailable and you downloaded `국토교통부_지반정보_시추공_*.csv` separately.

Import command from `Project/backend`:

```powershell
python scripts/import_molit_ground_data.py
```
