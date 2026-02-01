import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
import os

def send_email_with_pdf(sender_email, sender_password, recipient_email, subject, body, pdf_bytes, pdf_filename="Quotation.pdf", smtp_server="smtp.gmail.com", smtp_port=587):
    """
    Sends an email with a PDF attachment using SMTP.
    
    Args:
        sender_email (str): The sender's email address.
        sender_password (str): The sender's app password.
        recipient_email (str): The recipient's email address.
        subject (str): The email subject.
        body (str): The email body (text).
        pdf_bytes (bytes): The PDF content in bytes.
        pdf_filename (str): The filename for the attachment.
        smtp_server (str): SMTP server address (default: smtp.gmail.com).
        smtp_port (int): SMTP server port (default: 587 for TLS).
        
    Returns:
        tuple: (success (bool), message (str))
    """
    try:
        if not sender_email or not sender_password or not recipient_email:
            return False, "Missing email credentials or recipient address."

        # Create message container
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = recipient_email
        msg['Subject'] = subject

        # Add body to email
        msg.attach(MIMEText(body, 'plain'))

        # Attach PDF
        if pdf_bytes:
            pdf_attachment = MIMEApplication(pdf_bytes, _subtype="pdf")
            pdf_attachment.add_header('Content-Disposition', 'attachment', filename=pdf_filename)
            msg.attach(pdf_attachment)

        # Setup server connection
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls() # Secure the connection
        
        # Login
        try:
            server.login(sender_email, sender_password)
        except smtplib.SMTPAuthenticationError:
            server.quit()
            return False, "Authentication failed. Check your email and App Password."
        
        # Send email
        server.send_message(msg)
        server.quit()
        
        return True, "Email sent successfully!"
        
    except Exception as e:
        return False, f"Failed to send email: {str(e)}"
