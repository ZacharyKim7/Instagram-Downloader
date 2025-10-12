from flask import Flask, request, render_template, jsonify, send_file, Response
from playwright.sync_api import sync_playwright
import requests
import os
import uuid
from urllib.parse import urljoin, urlparse
import mimetypes
import io

app = Flask(__name__)

# For local storage
# app.config['UPLOAD_FOLDER'] = 'static/images'
# os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# In-memory storage for images
image_store = {}

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

        image_urls = scrape_images(url)
        downloaded_images = download_images_to_memory(image_urls, url)

        return jsonify({
            'success': True,
            'images': downloaded_images,
            'total': len(downloaded_images)
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

def scrape_images(url):
    image_urls = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Set user agent to appear more like a real browser
        page.set_extra_http_headers({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })

        try:
            page.goto(url, wait_until='domcontentloaded', timeout=30000)

            # Wait for network to be idle
            page.wait_for_load_state('networkidle', timeout=10000)

            # Additional wait to ensure dynamic content loads
            page.wait_for_timeout(2000)

            # Scroll to trigger lazy loading
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(1000)

            img_elements = page.query_selector_all('img')
            print(f"Found {len(img_elements)} total img elements")

            for img in img_elements:
                src = img.get_attribute('src')
                alt = img.get_attribute('alt') or ''

                print(f"Image - src: {src}, alt: {alt}")

                if src and 'Photo by' in alt:
                    absolute_url = urljoin(url, src)
                    image_urls.append(absolute_url)
                    print(f"Added image: {absolute_url}")

        except Exception as e:
            print(f"Error during scraping: {e}")
        finally:
            browser.close()

    print(f"Total filtered images: {len(image_urls)}")
    return list(set(image_urls))

def download_images(image_urls, base_url):
    downloaded_images = []

    for img_url in image_urls:
        try:
            response = requests.get(img_url, stream=True, timeout=10)
            response.raise_for_status()

            content_type = response.headers.get('content-type', '')
            if not content_type.startswith('image/'):
                continue

            file_extension = mimetypes.guess_extension(content_type) or '.jpg'
            filename = f"{uuid.uuid4().hex}{file_extension}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            downloaded_images.append({
                'filename': filename,
                'original_url': img_url,
                'local_path': f"/static/images/{filename}",
                'size': os.path.getsize(filepath)
            })

        except Exception as e:
            print(f"Failed to download {img_url}: {e}")
            continue

    return downloaded_images

def download_images_to_memory(image_urls, base_url):
    downloaded_images = []

    for img_url in image_urls:
        try:
            response = requests.get(img_url, stream=True, timeout=10)
            response.raise_for_status()

            content_type = response.headers.get('content-type', '')
            if not content_type.startswith('image/'):
                continue

            # Read image data into memory
            image_data = response.content
            file_extension = mimetypes.guess_extension(content_type) or '.jpg'
            image_id = uuid.uuid4().hex
            filename = f"{image_id}{file_extension}"

            # Store in memory
            image_store[image_id] = {
                'data': image_data,
                'content_type': content_type,
                'filename': filename
            }

            downloaded_images.append({
                'filename': filename,
                'original_url': img_url,
                'local_path': f"/image/{image_id}",
                'size': len(image_data)
            })

        except Exception as e:
            print(f"Failed to download {img_url}: {e}")
            continue

    return downloaded_images

@app.route('/image/<image_id>')
def serve_image(image_id):
    if image_id not in image_store:
        return jsonify({'error': 'Image not found'}), 404

    image_info = image_store[image_id]
    return Response(
        image_info['data'],
        mimetype=image_info['content_type']
    )

@app.route('/download/<image_id>')
def download_image(image_id):
    if image_id not in image_store:
        return jsonify({'error': 'Image not found'}), 404

    image_info = image_store[image_id]
    return Response(
        image_info['data'],
        mimetype=image_info['content_type'],
        headers={'Content-Disposition': f'attachment; filename={image_info["filename"]}'}
    )


if __name__ == '__main__':
    app.run(debug=True)