# MOLIT Borehole CSV Fallback

The program now collects `국토교통부_지반정보_시추공` through the approved OpenAPI using `PUBLIC_DATA_API_KEY`.

Use this folder only as a fallback when the OpenAPI is unavailable. Put `국토교통부_지반정보_시추공_*.csv` here, then run:

```powershell
python scripts/import_molit_ground_data.py
```
