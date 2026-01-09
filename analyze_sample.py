from pypdf import PdfReader

def analyze_sample_invoice():
    try:
        reader = PdfReader("sample_invoice.pdf")
        print(f"Number of pages: {len(reader.pages)}")
        
        page = reader.pages[0]
        text = page.extract_text()
        print("--- SAMPLE INVOICE TEXT ---")
        print(text)
        print("---------------------------")
        
    except Exception as e:
        print(f"Error reading PDF: {e}")

if __name__ == "__main__":
    analyze_sample_invoice()
