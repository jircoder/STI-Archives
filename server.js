const express = require('express');
const cors = require('cors');
const multer = require('multer');
const nodemailer = require('nodemailer');
const { google } = require('googleapis');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const app = express();
const PORT = process.env.PORT || 5000;

// Middleware
app.use(cors());
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Configure upload folder
const UPLOAD_FOLDER = 'uploads';
if (!fs.existsSync(UPLOAD_FOLDER)) {
    fs.mkdirSync(UPLOAD_FOLDER);
}

// Serve static files
app.use(express.static('.'));

// Handle Vercel deployment
if (process.env.VERCEL) {
    app.use('/api', (req, res, next) => {
        // Remove /api prefix for Vercel
        req.url = req.url.replace(/^\/api/, '');
        next();
    });
}

// For local development, add /api prefix handling
if (!process.env.VERCEL) {
    app.use('/api', (req, res, next) => {
        // Remove /api prefix for local development
        req.url = req.url.replace(/^\/api/, '');
        next();
    });
}

// Google Drive configuration
const GOOGLE_DRIVE_FOLDER_ID = '1MQ9ukcZ2OiQYWB_fUOG9_MKEdfl-r10N';
const SERVICE_ACCOUNT_FILE = 'service_account.json';

// Multer configuration for file uploads
const storage = multer.diskStorage({
    destination: (req, file, cb) => {
        cb(null, UPLOAD_FOLDER);
    },
    filename: (req, file, cb) => {
        const studentId = req.body.student_id || 'unknown';
        cb(null, `${studentId}_${Date.now()}_${file.originalname}`);
    }
});

const upload = multer({ storage: storage });

// Google Drive upload function
async function uploadToGoogleDrive(filePath, filename) {
    try {
        // Check if service account file exists
        if (!fs.existsSync(SERVICE_ACCOUNT_FILE)) {
            console.log("Service account file not found. Using local storage.");
            return null;
        }

        // Set up Google Drive API credentials
        const auth = new google.auth.GoogleAuth({
            keyFile: SERVICE_ACCOUNT_FILE,
            scopes: ['https://www.googleapis.com/auth/drive.file']
        });

        const drive = google.drive({ version: 'v3', auth });

        // Create file metadata
        const fileMetadata = {
            name: filename,
            parents: [GOOGLE_DRIVE_FOLDER_ID]
        };

        // Upload the file
        const media = {
            mimeType: 'application/octet-stream',
            body: fs.createReadStream(filePath)
        };

        const file = await drive.files.create({
            resource: fileMetadata,
            media: media,
            fields: 'id'
        });

        // Make the file publicly viewable
        await drive.permissions.create({
            fileId: file.data.id,
            requestBody: {
                type: 'anyone',
                role: 'reader'
            }
        });

        // Return the shareable link
        return `https://drive.google.com/file/d/${file.data.id}/view?usp=sharing`;

    } catch (error) {
        console.error('Failed to upload to Google Drive:', error);
        return null;
    }
}

// Password generation utility
function generatePassword(length = 12) {
    const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*';
    let password = '';
    for (let i = 0; i < length; i++) {
        password += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return password;
}

// Extract lastname from fullname
function extractLastname(fullname) {
    const names = fullname.trim().split(/\s+/);
    if (names.length < 2) {
        return names[0].toLowerCase();
    }
    return names[names.length - 1].toLowerCase();
}

// Generate school email
function generateSchoolEmail(fullname) {
    const lastname = extractLastname(fullname);
    return `${lastname}@clmb.sti.archives`;
}

// Email sending function
async function sendEmail(toEmail, subject, body) {
    const transporter = nodemailer.createTransporter({
        service: 'gmail',
        auth: {
            user: 'stiarchivesorg@gmail.com',
            pass: 'vyogdztvncxwxqzs'
        }
    });

    const mailOptions = {
        from: 'stiarchivesorg@gmail.com',
        to: toEmail,
        subject: subject,
        text: body
    };

    try {
        await transporter.sendMail(mailOptions);
        return true;
    } catch (error) {
        console.error('Failed to send email:', error);
        return false;
    }
}

// Routes

// Send welcome email
app.post('/send_welcome_email', async (req, res) => {
    const { fullname, personal_email } = req.body;

    if (!fullname || !personal_email) {
        return res.status(400).json({ error: 'Fullname and personal_email are required' });
    }

    const schoolEmail = generateSchoolEmail(fullname);
    const password = generatePassword();

    const subject = "Your STI Archives Account Has Been Created!";
    const body = `Hello ${fullname},

Your STI Archives account has been successfully created!

🔑 Login Credentials:
- Email: ${schoolEmail}
- Password: ${password}

You can now log in at: https://stiarchives.x10.mx

Please keep this information secure.

Best regards,
STI Archives Team`;

    if (await sendEmail(personal_email, subject, body)) {
        return res.json({ school_email: schoolEmail, password: password });
    } else {
        return res.status(500).json({ error: 'Failed to send email' });
    }
});

// Signup user
app.post('/signup_user', upload.single('raf'), async (req, res) => {
    const { fullname, personal_email, student_id, role, section } = req.body;
    const rafFile = req.file;

    if (!fullname || !personal_email || !student_id || !role || !section || !rafFile) {
        return res.status(400).json({ error: 'All fields are required' });
    }

    const filename = rafFile.filename;
    const tempFilePath = path.join(UPLOAD_FOLDER, filename);

    // Upload to Google Drive
    const driveLink = await uploadToGoogleDrive(tempFilePath, filename);

    // Clean up local file after upload
    if (fs.existsSync(tempFilePath)) {
        fs.unlinkSync(tempFilePath);
    }

    const schoolEmail = generateSchoolEmail(fullname);
    const password = generatePassword();

    // Create user data for admin panel
    const userData = {
        id: Date.now().toString(),
        user_id: student_id,
        name: fullname,
        email: schoolEmail,
        personal_email: personal_email,
        password: password,
        role: role,
        section: section,
        created_at: new Date().toISOString(),
        verified: false,
        rejected: false,
        banned: false,
        status: getStatus(new Date().toISOString()),
        raf_path: driveLink || tempFilePath
    };

    // Save to users.json file for admin panel
    try {
        let users = [];
        const usersFile = 'users.json';

        if (fs.existsSync(usersFile)) {
            users = JSON.parse(fs.readFileSync(usersFile, 'utf8'));
        }

        users.push(userData);

        fs.writeFileSync(usersFile, JSON.stringify(users, null, 2));

    } catch (error) {
        console.error('Error saving user data:', error);
        return res.status(500).json({ error: 'Failed to save user data' });
    }

    // Return success without sending email - email will be sent when admin accepts
    return res.json({
        status: 'success',
        message: 'Account created successfully! Please wait for admin verification.'
    });
});

// Send update email
app.post('/send_update_email', async (req, res) => {
    const { to_email, subject, message } = req.body;

    if (!to_email || !subject || !message) {
        return res.status(400).json({ error: 'to_email, subject, and message are required' });
    }

    if (await sendEmail(to_email, subject, message)) {
        return res.json({ message: 'Email sent successfully' });
    } else {
        return res.status(500).json({ error: 'Failed to send email' });
    }
});

// Get users
app.get('/get_users', (req, res) => {
    try {
        const usersFile = 'users.json';
        let users = [];

        if (fs.existsSync(usersFile)) {
            users = JSON.parse(fs.readFileSync(usersFile, 'utf8'));
        }

        return res.json(users);
    } catch (error) {
        console.error('Error loading users:', error);
        return res.status(500).json({ error: 'Failed to load users' });
    }
});

// Update user status
app.post('/update_user_status', (req, res) => {
    const { user_id, action } = req.body;

    if (!user_id || !['accept', 'reject', 'ban'].includes(action)) {
        return res.status(400).json({ error: 'Invalid user_id or action' });
    }

    try {
        const usersFile = 'users.json';
        let users = [];

        if (fs.existsSync(usersFile)) {
            users = JSON.parse(fs.readFileSync(usersFile, 'utf8'));
        }

        const user = users.find(u => String(u.user_id || u.id) === String(user_id));
        if (!user) {
            return res.status(404).json({ error: 'User not found' });
        }

        if (action === 'accept') {
            user.verified = true;
            user.verified_at = new Date().toISOString();
            user.rejected = false;
            user.banned = false;
            user.status = "verified";

            // Send welcome email with credentials when user is accepted
            const subject = "Your STI Archives Account Has Been Verified!";
            const body = `Hello ${user.name},

Your STI Archives account has been verified by the admin!

🔑 Login Credentials:
- Email: ${user.email}
- Password: ${user.password}

You can now log in at: https://stiarchives.x10.mx

Please keep this information secure.

Best regards,
STI Archives Team`;

            sendEmail(user.personal_email, subject, body).catch(error => {
                console.error(`Failed to send welcome email to ${user.personal_email}:`, error);
            });

        } else if (action === 'reject') {
            user.rejected = true;
            user.verified = false;
            user.banned = false;
            user.status = "rejected";
        } else if (action === 'ban') {
            user.banned = true;
            user.verified = false;
            user.rejected = false;
            user.status = "banned";
        }

        fs.writeFileSync(usersFile, JSON.stringify(users, null, 4));

        return res.json({ message: `User ${action}ed successfully` });
    } catch (error) {
        console.error('Error updating user status:', error);
        return res.status(500).json({ error: 'Failed to update user status' });
    }
});

// Get RAF file
app.get('/get_raf_file', (req, res) => {
    const filePath = req.query.path;

    if (!filePath) {
        return res.status(400).json({ error: 'File path is required' });
    }

    try {
        // If it's a Google Drive link, redirect to it
        if (filePath.startsWith('https://drive.google.com')) {
            return res.json({ redirect: filePath });
        }

        // Otherwise, serve local file
        if (fs.existsSync(filePath)) {
            return res.sendFile(path.resolve(filePath));
        } else {
            return res.status(404).json({ error: 'File not found' });
        }
    } catch (error) {
        console.error('Error serving RAF file:', error);
        return res.status(500).json({ error: 'Failed to serve file' });
    }
});

// Remove user
app.post('/remove_user', (req, res) => {
    const { user_id } = req.body;

    if (!user_id) {
        return res.status(400).json({ error: 'user_id is required' });
    }

    try {
        const usersFile = 'users.json';
        let users = [];

        if (fs.existsSync(usersFile)) {
            users = JSON.parse(fs.readFileSync(usersFile, 'utf8'));
        }

        // Find and remove the user
        users = users.filter(u => String(u.user_id || u.id) !== String(user_id));

        fs.writeFileSync(usersFile, JSON.stringify(users, null, 4));

        return res.json({ message: 'User removed successfully' });
    } catch (error) {
        console.error('Error removing user:', error);
        return res.status(500).json({ error: 'Failed to remove user' });
    }
});

// Start server
app.listen(PORT, () => {
    console.log(`Server running on port ${PORT}`);
});

module.exports = app;