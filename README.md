# Streamlit Invoice Generator

An interactive invoice builder that manages a product database and generates professional PDFs.

## Prerequisites

- Python 3.x installed
- pip installed

## Installation

1.  Navigate to this directory (you are likely already here):
    ```bash
    # Ensure you are in 'AntiGravity - Invoice Builder'
    pwd
    ```

2.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```

## Usage

1.  **Run the App**:
    ```bash
    # Recommendation: Use venv if created
    source venv/bin/activate 
    streamlit run app.py
    ```

2.  **Workflow**:

    ### Step 1: Manage Data (One-Time Setup)
    - Go to the **"Manage Data"** tab.
    - **Option A**: Upload `Item_Pricing.pdf` directly. The app will parse Arabic names and prices.
    - **Option B**: Upload an Excel file.
    - Click **"Update"**.

    > **Note on Fonts**: This app requires a font that supports Arabic (like `Arial.ttf` or `Arial Unicode.ttf`) to be present in `/System/Library/Fonts` or `/Library/Fonts`. It attempts to find one automatically.

    ### Step 2: Create Invoice (Daily Use)
    - Go to the **"Invoice Generator"** tab.
    - Upload the **Vendor Letterhead (PDF)**.
    - You will see a list of all products from the database.
    - **Enter Quantities** for the items you want to invoice.
    - Scroll down to see the **Live Preview** of totals.
    - Click **"Generate PDF Invoice"** to download.

## Files

- `app.py`: Main application with Database and UI logic.
- `products.db`: Local SQLite database storing your products (created automatically).
- `generate_from_pdf.py`: Script to parse `Item_Pricing.pdf` into Excel.
- `requirements.txt`: Python dependencies.
