# Google Cloud Run Deployment Guide

## Recommended target
- Google Cloud Run
- Python FastAPI container deployment
- Uses `Project/backend/Dockerfile`

## Prerequisites
- Create a Google Cloud project
- Attach a billing account
- Install Google Cloud CLI
- Sign in with `gcloud auth login`

## First-time setup
```powershell
cd Project\backend
Copy-Item cloudrun.env.example cloudrun.env
```

Set values in `cloudrun.env`:
- `GEMINI_API_KEY`
- `GOOGLE_MAPS_API_KEY`

## Deploy
```powershell
cd Project\backend
.\Deploy_Cloud_Run.ps1 -ProjectId <YOUR_PROJECT_ID> -AllowUnauthenticated
```

## Manual deploy command
```powershell
gcloud run deploy sinkhole-demo `
  --source . `
  --region asia-northeast3 `
  --port 8080 `
  --memory 1Gi `
  --cpu 1 `
  --timeout 300 `
  --env-vars-file cloudrun.env `
  --allow-unauthenticated
```

## Notes
- Cloud Run injects the `PORT` environment variable.
- Keep secrets out of source control; use `cloudrun.env` or Secret Manager.
- Cloud Run filesystem is not persistent, so `db/app.db` and `data/reports` do not survive instance replacement.
- For persistent storage, move to Cloud SQL, Firestore, and Cloud Storage.
