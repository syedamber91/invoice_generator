from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

def create_letterhead():
    c = canvas.Canvas("sample_letterhead.pdf", pagesize=A4)
    width, height = A4
    
    # Draw a header line
    c.setLineWidth(2)
    c.line(30, height - 50, width - 30, height - 50)
    
    # Add some text
    c.setFont("Helvetica-Bold", 24)
    c.drawString(30, height - 40, "VENDOR COMPANY INC.")
    
    c.setFont("Helvetica", 10)
    c.drawString(30, height - 65, "123 Business Road, Commerce City, 90210")
    c.drawString(30, height - 77, "Phone: (555) 123-4567 | Email: billing@vendor.com")
    
    # Add a logo placeholder
    c.rect(width - 80, height - 80, 50, 50)
    c.drawString(width - 75, height - 60, "LOGO")
    
    # Draw a footer
    c.line(30, 50, width - 30, 50)
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(30, 35, "Thank you for your business. Please pay within 30 days.")
    
    c.save()
    print("Created sample_letterhead.pdf")

if __name__ == "__main__":
    create_letterhead()
