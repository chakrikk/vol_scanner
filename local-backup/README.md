# Public Volume Scanner HH / LL

This credential-free Streamlit edition displays sanitized CSV snapshots. It does not contain or call the Schwab backend, OAuth token, application key, secret, or local private paths.

## Update the public data

From this folder, run:

```powershell
python publish_snapshot.py --source "C:\path\to\volume-scanner-hh-ll"
```

Commit and push the changed files under `data/`. Streamlit Community Cloud watches the repository and updates the deployed app. The browser checks the deployed files every 30 seconds, but new market data appears only after a new snapshot is published to the repository.

## Deploy on Streamlit Community Cloud

1. Create a GitHub repository containing this folder.
2. Do not add `.env`, token JSON, the private backend, or Schwab credential files.
3. In Streamlit Community Cloud, create an app from the repository.
4. Set the entry point to `streamlit_app.py`.
5. Make the app public and deploy it.

No Streamlit secrets are required for this read-only version.
