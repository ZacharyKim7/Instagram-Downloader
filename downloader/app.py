from flask import Flask, request, render_template, jsonify, send_file
from playwright.sync_api import sync_playwright
import requests
import os
import uuid
from urllib.parse import urljoin, urlparse
import mimetypes

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

        image_urls = scrape_images(url)
        downloaded_images = download_images(image_urls, url)

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

        page.goto(url)
        page.wait_for_load_state('networkidle')

        img_elements = page.query_selector_all('img')

        for img in img_elements:
            src = img.get_attribute('src')
            alt = img.get_attribute('alt') or ''

            if src and 'Photo by' in alt:
                absolute_url = urljoin(url, src)
                image_urls.append(absolute_url)

        browser.close()

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