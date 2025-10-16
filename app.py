from flask import Flask, request, jsonify
from flask_cors import CORS
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import secrets
import string
import json
import os
from datetime import datetime
from werkzeug.utils import secure_filename
import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Configure upload folder
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Google Drive configuration
GOOGLE_DRIVE_FOLDER_ID = '1MQ9ukcZ2OiQYWB_fUOG9_MKEdfl-r10N'
SERVICE_ACCOUNT_FILE = 'service_account.json'  # You'll need to create this

def upload_to_google_drive(file_path, filename):
    """Upload file to Google Drive and return the file ID"""
    try:
        # Check if service account file exists
        if not os.path.exists(SERVICE_ACCOUNT_FILE):
            print("Service account file not found. Using local storage.")
            return None

        # Set up Google Drive API credentials
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE,
            scopes=['https://www.googleapis.com/auth/drive.file']
        )

        # Build the Drive API service
        service = build('drive', 'v3', credentials=creds)

        # Create file metadata
        file_metadata = {
            'name': filename,
            'parents': [GOOGLE_DRIVE_FOLDER_ID]
        }

        # Upload the file
        media = MediaFileUpload(file_path, resumable=True)
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()

        # Make the file publicly viewable
        service.permissions().create(
            fileId=file.get('id'),
            body={'type': 'anyone', 'role': 'reader'}
        ).execute()

        # Return the shareable link
        return f"https://drive.google.com/file/d/{file.get('id')}/view?usp=sharing"

    except Exception as e:
        print(f"Failed to upload to Google Drive: {e}")
        return None

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

def send_email(to_email, subject, body):
    smtp_server = "smtp.gmail.com"
    smtp_port = 587
    sender_email = "stiarchivesorg@gmail.com"  # Replace with your real sender
    sender_password = "vyogdztvncxwxqzs"  # Use App Password if 2FA enabled

    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body.strip(), "plain"))

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, to_email, msg.as_string())
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False

@app.route('/send_welcome_email', methods=['POST'])
def send_welcome_email():
    data = request.json
    fullname = data.get('fullname')
    personal_email = data.get('personal_email')

    if not fullname or not personal_email:
        return jsonify({'error': 'Fullname and personal_email are required'}), 400

    school_email = generate_school_email(fullname)
    password = generate_password()

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

    if send_email(personal_email, subject, body):
        return jsonify({'school_email': school_email, 'password': password}), 200
    else:
        return jsonify({'error': 'Failed to send email'}), 500

@app.route('/signup_user', methods=['POST'])
def signup_user():
    fullname = request.form.get('fullname')
    personal_email = request.form.get('personal_email')
    student_id = request.form.get('student_id')
    role = request.form.get('role')
    section = request.form.get('section')
    raf_file = request.files.get('raf')

    if not all([fullname, personal_email, student_id, role, section, raf_file]):
        return jsonify({'error': 'All fields are required'}), 400

    # Save the RAF file temporarily
    filename = secure_filename(f"{student_id}_{raf_file.filename}")
    temp_file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    raf_file.save(temp_file_path)

    # Upload to Google Drive
    drive_link = upload_to_google_drive(temp_file_path, filename)

    # Clean up local file after upload
    if os.path.exists(temp_file_path):
        os.remove(temp_file_path)

    school_email = generate_school_email(fullname)
    password = generate_password()

    # Create user data for admin panel (without sending email yet)
    user_data = {
        'id': str(datetime.now().timestamp()),
        'user_id': student_id,
        'name': fullname,
        'email': school_email,
        'personal_email': personal_email,
        'password': password,
        'role': role,
        'section': section,
        'created_at': datetime.now().isoformat(),
        'verified': False,
        'rejected': False,
        'banned': False,
        'raf_path': drive_link or temp_file_path  # Use drive link if available, otherwise local path
    }

    # Save to users.json file for admin panel
    try:
        users_file = 'users.json'
        if os.path.exists(users_file):
            with open(users_file, 'r') as f:
                users = json.load(f)
        else:
            users = []

        users.append(user_data)

        with open(users_file, 'w') as f:
            json.dump(users, f, indent=2)

    except Exception as e:
        print(f"Error saving user data: {e}")
        return jsonify({'error': 'Failed to save user data'}), 500

    # Return success without sending email - email will be sent when admin accepts
    return jsonify({
        'status': 'success',
        'message': 'Account created successfully! Please wait for admin verification.'
    }), 200

@app.route('/send_update_email', methods=['POST'])
def send_update_email():
    data = request.json
    to_email = data.get('to_email')
    subject = data.get('subject')
    message = data.get('message')

    if not to_email or not subject or not message:
        return jsonify({'error': 'to_email, subject, and message are required'}), 400

    if send_email(to_email, subject, message):
        return jsonify({'message': 'Email sent successfully'}), 200
    else:
        return jsonify({'error': 'Failed to send email'}), 500

@app.route('/get_users', methods=['GET'])
def get_users():
    try:
        users_file = 'users.json'
        if os.path.exists(users_file):
            with open(users_file, 'r') as f:
                users = json.load(f)
        else:
            users = []
        return jsonify(users), 200
    except Exception as e:
        print(f"Error loading users: {e}")
        return jsonify({'error': 'Failed to load users'}), 500

@app.route('/update_user_status', methods=['POST'])
def update_user_status():
    data = request.json
    user_id = data.get('user_id')
    action = data.get('action')  # 'accept', 'reject', 'ban'

    if not user_id or action not in ['accept', 'reject', 'ban']:
        return jsonify({'error': 'Invalid user_id or action'}), 400

    try:
        users_file = 'users.json'
        if os.path.exists(users_file):
            with open(users_file, 'r') as f:
                users = json.load(f)
        else:
            users = []

        user = next((u for u in users if str(u.get('user_id', u.get('id'))) == str(user_id)), None)
        if not user:
            return jsonify({'error': 'User not found'}), 404

        if action == 'accept':
            user['verified'] = True
            user['verified_at'] = datetime.now().isoformat()
            user['rejected'] = False
            user['banned'] = False

            # Send welcome email with credentials when user is accepted
            subject = "Your STI Archives Account Has Been Verified!"
            body = f"""
            Hello {user['name']},

            Your STI Archives account has been verified by the admin!

            🔑 Login Credentials:
            - Email: {user['email']}
            - Password: {user['password']}

            You can now log in at: https://stiarchives.x10.mx

            Please keep this information secure.

            Best regards,
            STI Archives Team
            """

            if not send_email(user['personal_email'], subject, body):
                print(f"Failed to send welcome email to {user['personal_email']}")

        elif action == 'reject':
            user['rejected'] = True
            user['verified'] = False
            user['banned'] = False
        elif action == 'ban':
            user['banned'] = True
            user['verified'] = False
            user['rejected'] = False

        with open(users_file, 'w') as f:
            json.dump(users, f, indent=4)

        return jsonify({'message': f'User {action}ed successfully'}), 200
    except Exception as e:
        print(f"Error updating user status: {e}")
        return jsonify({'error': 'Failed to update user status'}), 500

@app.route('/get_raf_file', methods=['GET'])
def get_raf_file():
    file_path = request.args.get('path')
    if not file_path:
        return jsonify({'error': 'File path is required'}), 400

    try:
        # If it's a Google Drive link, redirect to it
        if file_path.startswith('https://drive.google.com'):
            return jsonify({'redirect': file_path}), 200

        # Otherwise, serve local file
        if os.path.exists(file_path):
            from flask import send_file
            return send_file(file_path)
        else:
            return jsonify({'error': 'File not found'}), 404
    except Exception as e:
        print(f"Error serving RAF file: {e}")
        return jsonify({'error': 'Failed to serve file'}), 500

@app.route('/remove_user', methods=['POST'])
def remove_user():
    data = request.json
    user_id = data.get('user_id')

    if not user_id:
        return jsonify({'error': 'user_id is required'}), 400

    try:
        users_file = 'users.json'
        if os.path.exists(users_file):
            with open(users_file, 'r') as f:
                users = json.load(f)
        else:
            users = []

        # Find and remove the user
        users = [u for u in users if str(u.get('user_id', u.get('id'))) != str(user_id)]

        with open(users_file, 'w') as f:
            json.dump(users, f, indent=4)

        return jsonify({'message': 'User removed successfully'}), 200
    except Exception as e:
        print(f"Error removing user: {e}")
        return jsonify({'error': 'Failed to remove user'}), 500

if __name__ == '__main__':
    app.run(debug=True)