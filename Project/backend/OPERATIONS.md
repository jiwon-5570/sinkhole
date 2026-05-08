# Operations Notes

Use these switches before a real deployment:

- `SINKHOLE_ENV=production`
- `SINKHOLE_SEED_DEMO=0`
- `SINKHOLE_ENABLE_BASIC_AUTH=1`
- `SINKHOLE_BASIC_AUTH_USERNAME=<admin-user>`
- `SINKHOLE_BASIC_AUTH_PASSWORD=<strong-password>`
- `SINKHOLE_EXPOSE_GOOGLE_MAPS_KEY=0`

Only set `SINKHOLE_EXPOSE_GOOGLE_MAPS_KEY=1` when the Google Maps key is restricted for browser use by HTTP referrer and API scope.

Run the local smoke check from `Project/backend`:

```powershell
python .\scripts\smoke_check.py
```

Cloud Run and other ephemeral containers do not preserve `db/app.db` or generated PDF files across instance replacement. For production, move the database to PostgreSQL/PostGIS and report files to object storage.
