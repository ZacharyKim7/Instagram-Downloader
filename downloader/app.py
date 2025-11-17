from flask import Flask, request, render_template, jsonify, send_file
from playwright.sync_api import sync_playwright
import requests
import os
import uuid
from urllib.parse import urljoin, urlparse
import mimetypes
import time
import json
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'static/images'
app.config['SESSION_FOLDER'] = 'session_data'
app.config['FILE_RETENTION_MINUTES'] = 30  # Keep files for 30 minutes

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['SESSION_FOLDER'], exist_ok=True)

# Instagram credentials from environment variables
INSTAGRAM_USERNAME = os.getenv('INSTAGRAM_USERNAME', '')
INSTAGRAM_PASSWORD = os.getenv('INSTAGRAM_PASSWORD', '')
SESSION_FILE = os.path.join(app.config['SESSION_FOLDER'], 'instagram_session.json')

def cleanup_old_files():
    """
    Removes downloaded media files older than FILE_RETENTION_MINUTES.
    This prevents storage buildup from accumulated downloads.
    """
    try:
        retention_seconds = app.config['FILE_RETENTION_MINUTES'] * 60
        current_time = time.time()
        deleted_count = 0

        for filename in os.listdir(app.config['UPLOAD_FOLDER']):
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

            # Skip directories and .gitkeep files
            if os.path.isdir(filepath) or filename == '.gitkeep':
                continue

            # Check file age
            file_age = current_time - os.path.getmtime(filepath)

            if file_age > retention_seconds:
                try:
                    os.remove(filepath)
                    deleted_count += 1
                except Exception as e:
                    print(f"Failed to delete {filename}: {e}")

        if deleted_count > 0:
            print(f"Cleaned up {deleted_count} old file(s)")

    except Exception as e:
        print(f"Error during cleanup: {e}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/extract-images', methods=['POST'])
def extract_images():
    try:
        # Clean up old files before processing new request
        cleanup_old_files()

        data = request.get_json()
        url = data.get('url')

        if not url:
            return jsonify({'error': 'URL is required'}), 400

        media_items = scrape_media(url)
        downloaded_media = download_media(media_items, url)

        return jsonify({
            'success': True,
            'media': downloaded_media,
            'total': len(downloaded_media)
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

def instagram_login(page):
    """
    Logs into Instagram using provided credentials.
    Returns True if login successful, False otherwise.
    """
    if not INSTAGRAM_USERNAME or not INSTAGRAM_PASSWORD:
        print("Warning: Instagram credentials not provided. Proceeding without login.")
        return False

    try:
        print(f"Attempting to log in as {INSTAGRAM_USERNAME}...")

        # Go to Instagram login page
        page.goto('https://www.instagram.com/accounts/login/', timeout=60000)
        page.wait_for_load_state('networkidle', timeout=30000)
        time.sleep(3)

        # Try multiple selector patterns for username input
        username_input = None
        username_selectors = [
            'input[name="username"]',
            'input[aria-label="Phone number, username, or email"]',
            'input[type="text"]'
        ]

        for selector in username_selectors:
            try:
                username_input = page.wait_for_selector(selector, timeout=5000)
                if username_input:
                    print(f"Found username input with selector: {selector}")
                    break
            except:
                continue

        if not username_input:
            print("Error: Could not find username input field")
            return False

        # Type username slowly to mimic human behavior
        username_input.click()
        username_input.fill('')
        username_input.type(INSTAGRAM_USERNAME, delay=100)
        time.sleep(1)

        # Find password input
        password_input = page.query_selector('input[name="password"]')
        if not password_input:
            password_input = page.query_selector('input[type="password"]')

        if not password_input:
            print("Error: Could not find password input field")
            return False

        # Type password slowly
        password_input.click()
        password_input.fill('')
        password_input.type(INSTAGRAM_PASSWORD, delay=100)
        time.sleep(1)

        # Find and click login button
        login_button = page.query_selector('button[type="submit"]')
        if not login_button:
            login_button = page.query_selector('button:has-text("Log in")')

        if not login_button:
            print("Error: Could not find login button")
            return False

        print("Clicking login button...")
        login_button.click()

        # Wait for navigation after login with longer timeout
        try:
            page.wait_for_url(lambda url: 'login' not in url.lower(), timeout=15000)
            print("Redirected away from login page")
        except:
            print("Still on login-related page after 15s")

        time.sleep(3)

        # Check current URL
        current_url = page.url
        print(f"Current URL after login attempt: {current_url}")

        # Check for error messages
        error_element = page.query_selector('div#slfErrorAlert, p[data-testid="login-error-message"]')
        if error_element:
            error_text = error_element.inner_text()
            print(f"Login error message: {error_text}")
            return False

        # Dismiss "Save Login Info" prompt if it appears
        try:
            save_info_selectors = [
                'button:has-text("Not now")',
                'button:has-text("Not Now")',
                '//button[contains(text(), "Not")]'
            ]
            for selector in save_info_selectors:
                not_now_button = page.query_selector(selector)
                if not_now_button and not_now_button.is_visible():
                    print("Dismissing 'Save Login Info' prompt")
                    not_now_button.click()
                    time.sleep(1)
                    break
        except Exception as e:
            print(f"Error dismissing save info prompt: {e}")

        # Dismiss "Turn on Notifications" prompt if it appears
        try:
            time.sleep(2)
            notification_selectors = [
                'button:has-text("Not Now")',
                'button:has-text("Not now")',
                '//button[contains(text(), "Not")]'
            ]
            for selector in notification_selectors:
                not_now_button = page.query_selector(selector)
                if not_now_button and not_now_button.is_visible():
                    print("Dismissing 'Turn on Notifications' prompt")
                    not_now_button.click()
                    time.sleep(1)
                    break
        except Exception as e:
            print(f"Error dismissing notifications prompt: {e}")

        # Check if we're logged in
        time.sleep(2)
        current_url = page.url

        # Multiple checks for successful login
        if 'login' not in current_url.lower() or 'instagram.com/' in current_url:
            # Additional check: look for logged-in elements
            profile_link = page.query_selector('a[href*="/accounts/activity/"]')
            home_link = page.query_selector('svg[aria-label="Home"]')

            if profile_link or home_link or 'challenge' not in current_url.lower():
                print("Login successful!")
                return True

        print(f"Login may have failed - current URL: {current_url}")
        return False

    except Exception as e:
        print(f"Login failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False

def save_session(context):
    """
    Saves browser session cookies to a file.
    """
    try:
        cookies = context.cookies()
        with open(SESSION_FILE, 'w') as f:
            json.dump(cookies, f)
        print(f"Session saved to {SESSION_FILE}")
    except Exception as e:
        print(f"Failed to save session: {e}")

def load_session(context):
    """
    Loads browser session cookies from a file.
    Returns True if session loaded successfully, False otherwise.
    """
    try:
        if os.path.exists(SESSION_FILE):
            with open(SESSION_FILE, 'r') as f:
                cookies = json.load(f)
            context.add_cookies(cookies)
            print(f"Session loaded from {SESSION_FILE}")
            return True
        return False
    except Exception as e:
        print(f"Failed to load session: {e}")
        return False

def scrape_media(url):
    """
    Scrapes both images and videos from Instagram posts.
    Handles carousel posts by navigating through all slides.
    Uses persistent login session to avoid Instagram's login wall.
    Returns a list of media items with URLs and types.
    """
    media_items = []
    seen_urls = set()
    captured_video_urls = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()

        # Try to load existing session
        session_loaded = load_session(context)

        page = context.new_page()

        # Set up request interception to capture video URLs
        def handle_request(request):
            # Capture video file requests from Instagram CDN
            url = request.url
            # Look for video files from Instagram's CDN
            is_video = (
                # Check for video file extensions
                any(ext in url for ext in ['.mp4', '.mov', '.webm']) or
                # Check for Instagram CDN domains with video in path
                ('scontent' in url and 'video' in url) or
                # Check for fbcdn (Facebook CDN used by Instagram)
                ('fbcdn' in url and 'video' in url)
            )

            if is_video and url not in captured_video_urls:
                print(f"Captured video URL from network: {url}")
                captured_video_urls.append(url)

        page.on('request', handle_request)

        # If we have credentials and no session, login
        if INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD:
            if not session_loaded:
                # Need to login
                print("No existing session found, logging in...")
                if instagram_login(page):
                    # Save session after successful login
                    save_session(context)
                else:
                    print("Warning: Login failed, continuing without authentication")
            else:
                print("Using existing session")

        # Navigate to the target post with increased timeout
        print(f"Navigating to post: {url}")
        try:
            page.goto(url, timeout=60000)
            page.wait_for_load_state('networkidle', timeout=30000)
        except Exception as e:
            print(f"Warning: Page load timeout or error: {e}")
            # Continue anyway, page might be partially loaded

        # Wait a bit for dynamic content to load
        time.sleep(3)

        # Check if this page has video content - if so, wait longer for video to load
        has_video = page.query_selector('video') is not None
        if has_video:
            print("Video detected, waiting for video to load...")
            time.sleep(5)  # Extra time for video blob to resolve

            # Check if we still have blob URLs - if so, reload the page
            video_element = page.query_selector('video')
            if video_element:
                video_src = video_element.get_attribute('src')
                if video_src and video_src.startswith('blob:'):
                    print("Video still using blob URL, reloading page to get real URL...")
                    page.reload(timeout=60000)
                    page.wait_for_load_state('networkidle', timeout=30000)
                    time.sleep(3)

        # Check if we hit a login wall
        current_url = page.url
        if 'accounts/login' in current_url:
            print("Hit Instagram login wall. Session may have expired.")
            if INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD:
                print("Attempting to login again...")
                if instagram_login(page):
                    save_session(context)
                    # Navigate to target post again
                    page.goto(url, timeout=60000)
                    page.wait_for_load_state('networkidle', timeout=30000)
                    time.sleep(3)
                else:
                    print("Login failed, cannot access post")
                    return []
            else:
                print("No credentials provided, cannot bypass login wall")
                return []

        # Check if this is a carousel post by looking for next button
        # Instagram carousel posts have next/previous buttons
        next_button_selectors = [
            'button[aria-label="Next"]',
            'button[aria-label="Go to next slide"]',
            'button._afxw._al46._al47',  # Instagram's carousel next button class
            'div._aaqg button'  # Alternative selector
        ]

        is_carousel = False
        next_button = None
        for selector in next_button_selectors:
            next_button = page.query_selector(selector)
            if next_button:
                is_carousel = True
                break

        if is_carousel:
            print("Detected carousel post, navigating through slides...")
            max_slides = 20  # Safety limit to prevent infinite loops
            slide_count = 0

            # Wait a bit to ensure first slide's images are fully loaded
            time.sleep(2)

            while slide_count < max_slides:
                print(f"Extracting media from slide {slide_count + 1}...")

                # Extract media from current slide
                current_media = extract_media_from_page(page)

                # Add new media to our collection
                new_media_count = 0
                for media in current_media:
                    if media['url'] not in seen_urls:
                        media_items.append(media)
                        seen_urls.add(media['url'])
                        new_media_count += 1

                print(f"  Found {new_media_count} new media item(s) on slide {slide_count + 1}")

                # Try to click next button
                next_button = None
                for selector in next_button_selectors:
                    next_button = page.query_selector(selector)
                    if next_button and next_button.is_visible():
                        break

                if next_button and next_button.is_visible():
                    try:
                        next_button.click()
                        time.sleep(1.5)  # Wait for next slide to load
                        slide_count += 1
                    except:
                        # Can't click anymore, we've reached the end
                        break
                else:
                    # No more next button, we've seen all slides
                    break
        else:
            # Single image/video post
            print("Detected single post")
            media_items = extract_media_from_page(page)

        context.close()
        browser.close()

    # Add captured video URLs from network requests
    for video_url in captured_video_urls:
        media_items.append({
            'url': video_url,
            'type': 'video'
        })

    # Remove duplicates while preserving order
    unique_media = []
    seen = set()
    for item in media_items:
        if item['url'] not in seen:
            unique_media.append(item)
            seen.add(item['url'])

    print(f"Total media items found: {len(unique_media)} ({sum(1 for m in unique_media if m['type'] == 'image')} images, {sum(1 for m in unique_media if m['type'] == 'video')} videos)")

    return unique_media


def extract_media_from_page(page):
    """
    Extracts both images and videos from the current page state.
    Returns a list of media dictionaries with 'url' and 'type' keys.
    """
    media_items = []

    # Try to find the main post article container to avoid sidebar/suggested images
    # Instagram typically puts the main post in an article element
    article = page.query_selector('article[role="presentation"]')
    if not article:
        article = page.query_selector('article')
    if not article:
        # Fallback to entire page if we can't find article
        article = page

    print(f"Searching for media in: {('main article' if article != page else 'entire page')}")

    # Extract images from within the article only
    img_elements = article.query_selector_all('img')
    print(f"Found {len(img_elements)} img elements in article")

    for img in img_elements:
        src = img.get_attribute('src')
        alt = img.get_attribute('alt') or ''

        # Only accept images where alt text starts with "Photo by "
        # This ensures we only get post content, not profile pictures, logos, etc.
        if src and alt.startswith('Photo by '):
            # Additional check: avoid very small images (profile pics, icons)
            # Get image dimensions if available
            try:
                width = img.evaluate('el => el.naturalWidth')
                height = img.evaluate('el => el.naturalHeight')

                # Skip small images (likely profile pics or thumbnails)
                if width and height and (width < 150 or height < 150):
                    print(f"Skipping small image: {width}x{height}")
                    continue
            except:
                # If we can't get dimensions, proceed anyway
                pass

            print(f"Found valid image: {alt[:50]}...")
            media_items.append({
                'url': src,
                'type': 'image'
            })

    # Extract videos - handle blob URLs (also only from article)
    video_elements = article.query_selector_all('video')
    print(f"Found {len(video_elements)} video elements in article")

    for video in video_elements:
        # Try to get video source from src attribute
        src = video.get_attribute('src')

        if not src:
            # Try to get from nested source tags
            source_elements = video.query_selector_all('source')
            for source in source_elements:
                src = source.get_attribute('src')
                if src:
                    break

        # If we found a video source, check if it's a blob URL
        if src:
            # Blob URLs won't work for downloading, need to get the real URL
            if src.startswith('blob:'):
                print(f"Found blob URL: {src[:50]}..., will be captured via network interception")
                # Blob URLs are useless for downloading, skip for now
                # We'll use network interception to get the real URL
                continue
            else:
                print(f"Found valid video URL")
                media_items.append({
                    'url': src,
                    'type': 'video'
                })

    return media_items

def download_media(media_items, base_url):
    """
    Downloads both images and videos from the provided media items.
    Handles both image/* and video/* content types.
    """
    downloaded_media = []

    for media in media_items:
        media_url = media['url']
        media_type = media['type']

        try:
            response = requests.get(media_url, stream=True, timeout=30)
            response.raise_for_status()

            content_type = response.headers.get('content-type', '')

            # Validate content type matches expected media type
            if media_type == 'image' and not content_type.startswith('image/'):
                # Sometimes Instagram serves images with other content types, be lenient
                if not any(ext in media_url for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                    continue

            if media_type == 'video' and not content_type.startswith('video/'):
                # Sometimes Instagram serves videos with other content types, be lenient
                if not any(ext in media_url for ext in ['.mp4', '.mov', '.webm']):
                    continue

            # Determine file extension
            file_extension = mimetypes.guess_extension(content_type)

            if not file_extension:
                # Fallback based on media type
                if media_type == 'image':
                    file_extension = '.jpg'
                elif media_type == 'video':
                    file_extension = '.mp4'
                else:
                    file_extension = '.bin'

            filename = f"{uuid.uuid4().hex}{file_extension}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

            # Download and save the file
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            downloaded_media.append({
                'filename': filename,
                'original_url': media_url,
                'local_path': f"/static/images/{filename}",
                'size': os.path.getsize(filepath),
                'type': media_type,
                'content_type': content_type
            })

            print(f"Downloaded {media_type}: {filename} ({os.path.getsize(filepath)} bytes)")

        except Exception as e:
            print(f"Failed to download {media_url}: {e}")
            continue

    return downloaded_media

@app.route('/download/<filename>')
def download_file(filename):
    try:
        return send_file(
            os.path.join(app.config['UPLOAD_FOLDER'], filename),
            as_attachment=True
        )
    except Exception as e:
        return jsonify({'error': 'File not found'}), 404

if __name__ == '__main__':
    app.run(debug=True)