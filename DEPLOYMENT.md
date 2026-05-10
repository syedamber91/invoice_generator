# Deployment Guide: Streamlit Invoice Generator

This guide explains how to deploy your **Invoice Generator Application** to the web so your client can access it from anywhere.

## Recommended Platform: Streamlit Community Cloud
The easiest and most compatible way to host this application is **Streamlit Community Cloud**. It connects directly to GitHub and updates automatically when you push code changes.

### Prerequisites
1.  **GitHub Account**: You need a GitHub account to host the code.
2.  **Arabic Font File**: Since the cloud servers run Linux (not Mac), they won't have your system fonts. You **MUST** add a font file to your project.
    *   Find `Arial.ttf` or `Arial Unicode.ttf` on your computer.
    *   Copy it into this project folder (same folder as `app.py`).
    *   Rename it to `Arial.ttf` for simplicity.

---

### Step 1: Prepare the Repository
1.  **Create a GitHub Repository**:
    *   Go to [GitHub.com/new](https://github.com/new).
    *   Name it `invoice-generator` (or similar).
    *   Select **Private** (recommended for business tools) or **Public**.
    *   Click "Create repository".

2.  **Upload Files**:
    *   You can upload files via the web interface or use Git commands if you are comfortable.
    *   **Essential Files to Upload**:
        *   `app.py`
        *   `requirements.txt`
        *   `products.db` (If you want to start with your current data)
        *   `Arial.ttf` (The font file you added)
        *   `README.md`
    *   *Note: Do not upload the `venv` folder.*

### Step 2: Deploy
1.  Go to [Streamlit Community Cloud](https://streamlit.io/cloud) and sign up/login with GitHub.
2.  Click **"New app"**.
3.  Select your GitHub repository (`invoice-generator`) and branch (`main`).
4.  **Main file path**: Enter `app.py`.
5.  Click **"Deploy"**.

### Step 3: Verify & Share
1.  Wait for the app to build (it installs libraries from `requirements.txt`).
2.  Once live, you will get a URL (e.g., `https://invoice-generator.streamlit.app`).
3.  **Share this URL** with your client.
4.  **Privacy**: If you made the repo Private, only you can access the app initially. To give your client access:
    *   Click "Settings" -> "Sharing" in the Streamlit Cloud dashboard.
    *   Add your client's email address (they will need a free Google or GitHub account to login).

---

## Alternative: Local Network (No Internet)
If the client wants to run it on their own office computer without the internet:
1.  Install Python on their machine.
2.  Copy this entire folder to their computer.
3.  Double-click `run_app.bat` (you would need to create this simple script) which runs `streamlit run app.py`.

## Persistent storage for Drafts & Archive (Turso)

The app saves in-progress quotations as **Drafts** and stores every generated
PDF (with its form data) in an **Archive**, both surfaced in the left sidebar.

Locally these are kept in a SQLite file (`quotation_store.db`). On Streamlit
Cloud, that file is wiped on every redeploy, so for production you should
point the app at a hosted SQLite database via [Turso](https://turso.tech).
Turso has a generous free tier and a SQLite-compatible HTTP API.

### One-time setup

1. Sign up at [turso.tech](https://turso.tech) (GitHub login is fine).
2. Create a database:
   ```bash
   turso db create oasis-quotations
   turso db show oasis-quotations --url      # libsql://...turso.io
   turso db tokens create oasis-quotations   # eyJ...
   ```
3. In Streamlit Cloud → your app → **Settings → Secrets**, add:
   ```toml
   TURSO_DATABASE_URL = "libsql://oasis-quotations-<your-org>.turso.io"
   TURSO_AUTH_TOKEN   = "eyJ..."
   ```
4. Save and **Reboot** the app. The sidebar caption should now read
   **Storage backend: ☁️ Turso** instead of *💾 Local SQLite*.

The app creates the `drafts` and `archive` tables automatically on first run.

### Local development with the same database

To use the same Turso database from your laptop, create a
`.streamlit/secrets.toml` file (gitignored) with the same two keys, or export
them as environment variables:

```bash
export TURSO_DATABASE_URL=libsql://...
export TURSO_AUTH_TOKEN=eyJ...
streamlit run app.py
```

If neither is set, the app falls back to `quotation_store.db` in the project
folder — convenient for offline work but not shared across machines.

## Troubleshooting
*   **"Font not found"**: Ensure `Arial.ttf` is in the root folder of your GitHub repository.
*   **Sidebar shows "Local SQLite" on Streamlit Cloud**: Turso secrets aren't
    being picked up. Re-check `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN` in
    *Settings → Secrets* and click *Reboot*.
*   **`ImportError: libsql_client`**: `libsql-client` is missing from
    `requirements.txt`. Check the latest deploy log; redeploy if needed.
