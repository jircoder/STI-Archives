# send_welcome_email.py
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import secrets
import string

def generate_password(length=12):
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def extract_lastname(fullname):
    names = fullname.strip().split()
    if len(names) < 2:
        return names[0].lower()  # fallback to first name if only one name
    return names[-1].lower()

def generate_school_email(fullname):
    lastname = extract_lastname(fullname)
    return f"{lastname}@sti.archives.clmb"

def send_account_email(personal_email, fullname):
    # Generate credentials
    school_email = generate_school_email(fullname)
    password = generate_password()

    # Email content
    subject = "Your STI Archives Account Has Been Created!"
    body = f"""
    Hello {fullname},

    Your STI Archives account has been successfully created!

    🔑 Login Credentials:
    - Email: {school_email}
    - Password: {password}

    You can now log in at: https://stiarchives.x10.mx

    Please keep this information secure.

    Best regards,
    STI Archives Team
    """

    # SMTP Configuration (Use your own email service)
    smtp_server = "smtp.gmail.com"  # Example: Gmail
    smtp_port = 587
    sender_email = "stiarchivesorg@gmail.com"  # Replace with your real sender
    sender_password = "your_app_password"  # Use App Password if 2FA enabled

    # Build email
    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = personal_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body.strip(), "plain"))

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, personal_email, msg.as_string())
        print(f"✅ Email sent to {personal_email}")
        return school_email, password
    except Exception as e:
        print(f"❌ Failed to send email: {e}")
        return None, None

# Example usage
if __name__ == "__main__":
    # Simulate data from signup form
    fullname = "Juan Delos Santos"
    personal_email = "juandelossantos.personal@gmail.com"

    email, pwd = send_account_email(personal_email, fullname)
    if email and pwd:
        print(f"Generated email: {email}")
        print(f"Generated password: {pwd}")