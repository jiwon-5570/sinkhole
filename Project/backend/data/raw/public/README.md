# Public File Data

Put downloaded public-data files here. Raw data files are ignored by Git so large CSV/XLSX/ZIP files do not get committed.

## MOLIT Ground Information

Layer CSV:

```text
Project/backend/data/raw/public/molit_ground_layers/
```

Put the downloaded `국토교통부_지반정보_지층정보_*.csv` file in that folder.

Optional borehole CSV:

```text
Project/backend/data/raw/public/molit_boreholes/
```

If you also download `국토교통부_지반정보_시추공_*.csv`, put it in that folder. The layer data is more useful for map-based analysis when a borehole file supplies coordinates for each borehole.

Import command from `Project/backend`:

```powershell
python scripts/import_molit_ground_data.py
```

