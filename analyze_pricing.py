from pypdf import PdfReader

def analyze_pdf():
    try:
        reader = PdfReader("Item_Pricing.pdf")
        print(f"Number of pages: {len(reader.pages)}")
        
        # Print first page text
        page = reader.pages[0]
        text = page.extract_text()
        print("--- PAGE 1 TEXT ---")
        print(text)
        print("-------------------")
        
    except Exception as e:
        print(f"Error reading PDF: {e}")

if __name__ == "__main__":
    analyze_pdf()
