from flask import Flask, request, render_template, jsonify, send_file
from playwright.sync_api import sync_playwright
import requests
import os
import uuid
from urllib.parse import urljoin, urlparse
import mimetypes
import time

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'static/images'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/extract-images', methods=['POST'])
def extract_images():
    try:
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

def scrape_media(url):
    """
    Scrapes both images and videos from Instagram posts.
    Handles carousel posts by navigating through all slides.
    Returns a list of media items with URLs and types.
    """
    media_items = []
    seen_urls = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.goto(url)
        page.wait_for_load_state('networkidle')

        # Wait a bit for dynamic content to load
        time.sleep(2)

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

            while slide_count < max_slides:
                # Extract media from current slide
                current_media = extract_media_from_page(page)

                # Add new media to our collection
                for media in current_media:
                    if media['url'] not in seen_urls:
                        media_items.append(media)
                        seen_urls.add(media['url'])

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

        browser.close()

    # Remove duplicates while preserving order
    unique_media = []
    seen = set()
    for item in media_items:
        if item['url'] not in seen:
            unique_media.append(item)
            seen.add(item['url'])

    return unique_media


def extract_media_from_page(page):
    """
    Extracts both images and videos from the current page state.
    Returns a list of media dictionaries with 'url' and 'type' keys.
    """
    media_items = []

    # Extract images
    img_elements = page.query_selector_all('img')
    for img in img_elements:
        src = img.get_attribute('src')
        alt = img.get_attribute('alt') or ''

        # Only accept images where alt text starts with "Photo by "
        # This ensures we only get post content, not profile pictures, logos, etc.
        if src and alt.startswith('Photo by '):
            media_items.append({
                'url': src,
                'type': 'image'
            })

    # Extract videos
    video_elements = page.query_selector_all('video')
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

        if src:
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