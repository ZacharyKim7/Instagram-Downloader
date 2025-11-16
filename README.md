# Instagram Downloader

A paste-link downloader for Instagram that supports downloading images and videos from both single posts and carousel posts.

## Features

- ✅ Download images from Instagram posts
- ✅ Download videos from Instagram posts
- ✅ Support for carousel posts (multiple images/videos)
- ✅ Persistent login session to bypass Instagram's login wall
- ✅ Handles lazy-loaded content in carousels

## Setup

### 1. Install Dependencies

```bash
cd downloader
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure Instagram Credentials (Recommended)

To avoid Instagram's login wall after viewing a few posts, you can provide your Instagram credentials:

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and add your Instagram credentials:
   ```
   INSTAGRAM_USERNAME=your_username
   INSTAGRAM_PASSWORD=your_password
   ```

**Note:** Your credentials are stored locally and only used to log into Instagram via Playwright. The session is saved in `session_data/` so you don't need to log in every time.

### 3. Run the Application

```bash
cd downloader
python app.py
```

The app will be available at `http://localhost:5000`

## Usage

1. Open your browser and navigate to `http://localhost:5000`
2. Paste an Instagram post URL (e.g., `https://www.instagram.com/p/ABC123/`)
3. Click "Download Media"
4. View and download the extracted images/videos

## How It Works

1. Uses Playwright to visit Instagram posts in a headless browser
2. Automatically logs in with provided credentials (if available)
3. Saves login session for future requests
4. For carousel posts, navigates through all slides to capture all media
5. Extracts image and video URLs from the page
6. Downloads media files to the server
7. Serves them to the user for download

## Technical Details

- **Backend:** Python, Flask, Playwright
- **Browser:** Chromium (headless)
- **Session Management:** Cookies stored in `session_data/`
- **Media Storage:** Downloaded files temporarily saved to `static/images/`
- **Auto-Cleanup:** Files older than 30 minutes are automatically deleted

## Privacy & Security

- Instagram credentials are only stored in your local `.env` file
- Login sessions are saved locally in `session_data/`
- Both `.env` and `session_data/` are excluded from git via `.gitignore`
- Downloaded media files are temporary and automatically deleted after 30 minutes
- The app can still work without credentials, but may hit Instagram's login wall after ~3 posts