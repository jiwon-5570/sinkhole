param(
    [string]$ProjectId,
    [string]$Region = "asia-northeast3",
    [string]$ServiceName = "sinkhole-demo",
    [string]$EnvFile = ".\\cloudrun.env",
    [switch]$AllowUnauthenticated
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    throw "gcloud CLI is not installed. Install Google Cloud CLI first: https://cloud.google.com/sdk/docs/install"
}

if (-not $ProjectId) {
    throw "ProjectId is required. Example: .\\Deploy_Cloud_Run.ps1 -ProjectId my-gcp-project"
}

Set-Location -LiteralPath $PSScriptRoot

Write-Host "[INFO] Using project: $ProjectId"
Write-Host "[INFO] Using region: $Region"
Write-Host "[INFO] Service name: $ServiceName"

gcloud config set project $ProjectId | Out-Null
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com | Out-Null

$args = @(
    "run", "deploy", $ServiceName,
    "--source", ".",
    "--region", $Region,
    "--port", "8080",
    "--memory", "1Gi",
    "--cpu", "1",
    "--timeout", "300"
)

if (Test-Path -LiteralPath $EnvFile) {
    $args += @("--env-vars-file", $EnvFile)
}

if ($AllowUnauthenticated) {
    $args += "--allow-unauthenticated"
} else {
    $args += "--no-allow-unauthenticated"
}

Write-Host "[INFO] Deploying to Cloud Run..."
& gcloud @args
