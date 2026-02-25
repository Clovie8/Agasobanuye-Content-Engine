import os
import json
import time
import logging
import requests
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync
from google import genai
from moviepy.editor import ImageClip, CompositeVideoClip, ColorClip

# --- CONFIGURATION ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
AYRSHARE_API_KEY = os.environ.get("AYRSHARE_API_KEY") # Our new Social Media Gateway

SITES_FILE = "sites.json"
MEMORY_FILE = "memory.json"

def get_page_content(url, selector):
    """Scrapes the website and saves a screenshot of the new movie."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        stealth_sync(page)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            try:
                close_button = page.locator("button.wa-widget-close")
                close_button.first.click(timeout=5000)
                page.wait_for_timeout(1000) 
            except Exception:
                pass

            page.wait_for_selector(selector, timeout=30000)
            elements = page.query_selector_all(selector)
            extracted_text = "\n".join([el.inner_text() for el in elements])
            
            if len(elements) > 0:
               elements[0].screenshot(path="movie.png")
               
            return extracted_text
        except Exception as e:
            logging.error(f"Scraping failed: {e}")
            return None
        finally:
            browser.close()

def generate_seo_brain(new_text, content_type):
    """Uses Gemini to generate viral Kinyarwanda/English SEO content as JSON."""
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        prompt = f"""
        Act as a viral social media marketer in Rwanda specializing in Agasobanuye movies.
        I am giving you the newest {content_type} uploaded to TheOneMovies.com.

        Your job is to extract the details and write a highly engaging caption mixing Kinyarwanda and English. 
        You MUST return the output ONLY as a valid JSON object with these exact keys:
        - "title": A short, exciting title for the video.
        - "caption": A hype description ending with a call to action to watch on TheOneMovies.com. Use emojis.
        - "hashtags": A string of 10 trending hashtags (e.g., "#Agasobanuye #Kinyarwanda #MoviesRwanda").

        NEW WEBSITE TEXT:
        {new_text[:1500]}
        """
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        # Clean the response to ensure it's pure JSON
        raw_json = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(raw_json)
    except Exception as e:
        logging.error(f"SEO Brain failed: {e}")
        return {
            "title": "New Release! 🎬",
            "caption": "🔥 New content just dropped! Watch now on TheOneMovies.com!",
            "hashtags": "#TheOneMovies #Agasobanuye #Rwanda"
        }

def render_vertical_video(image_path, output_name="final_short.mp4"):
    """Converts the screenshot into a 10-second vertical video for Shorts/TikTok."""
    try:
        logging.info("🎬 Rendering vertical video...")
        # 1. Load the website screenshot
        main_img = ImageClip(image_path).set_duration(10)
        
        # 2. Create a vertical canvas (1080x1920 is standard TikTok/Shorts size)
        background = ColorClip(size=(1080, 1920), color=(15, 15, 15)).set_duration(10)
        
        # 3. Resize our screenshot to fit the width of the vertical canvas
        main_img = main_img.resize(width=1000)
        
        # 4. Center the screenshot on the canvas
        final_video = CompositeVideoClip([background, main_img.set_position("center")])
        
        # 5. Export the final video file!
        final_video.write_videofile(output_name, fps=24, codec="libx264", audio=False, logger=None)
        logging.info("✅ Video rendered successfully!")
        return output_name
    except Exception as e:
        logging.error(f"Video rendering failed: {e}")
        return None

def post_to_social_media(video_path, seo_data):
    """Pushes the video and Kinyarwanda caption to Ayrshare (YouTube, FB, Insta)."""
    logging.info("🚀 Uplinking to Social Media...")
    
    # First, we must upload the media file to Ayrshare's server
    media_url = "https://app.ayrshare.com/api/media"
    headers = {"Authorization": f"Bearer {AYRSHARE_API_KEY}"}
    
    try:
        with open(video_path, "rb") as file:
            files = {"file": file}
            media_response = requests.post(media_url, headers=headers, files=files)
            media_response.raise_for_status()
            media_id = media_response.json().get("url") # Get the hosted URL of our video
            
        # Now, create the actual post with the text and the video URL
        post_url = "https://app.ayrshare.com/api/post"
        payload = {
            "post": f"{seo_data['title']}\n\n{seo_data['caption']}\n\n{seo_data['hashtags']}",
            "platforms": ["youtube", "facebook", "instagram"], # Tells Ayrshare where to send it!
            "mediaUrls": [media_id]
        }
        
        post_response = requests.post(post_url, headers={"Authorization": f"Bearer {AYRSHARE_API_KEY}", "Content-Type": "application/json"}, json=payload)
        post_response.raise_for_status()
        logging.info("🔥 BOOM! Content cross-posted to all platforms!")
        
    except Exception as e:
        logging.error(f"Social media upload failed: {e}")

def main():
    with open(SITES_FILE, "r") as f:
        sites = json.load(f)

    memory = {}
    if os.path.exists(MEMORY_FILE):
        with open(MEMORY_FILE, "r") as f:
            memory = json.load(f)

    memory_changed = False

    for site in sites:
        url = site["url"]
        selector = site["selector"]
        content_type = "Movie" if "nth-of-type(1)" in selector else "Series"
        memory_key = f"{url}_{selector}"

        content = get_page_content(url, selector)
        if not content:
            continue

        saved_text = memory.get(memory_key, "")

        if content != saved_text:
            logging.info(f"🚨 NEW {content_type.upper()} DETECTED! Starting Content Engine...")
            
            # 1. Let Gemini write the Kinyarwanda SEO text
            seo_data = generate_seo_brain(content, content_type)
            
            # 2. Render the .mp4 Video
            video_file = render_vertical_video("movie.png")
            
            # 3. Post to Social Media!
            if video_file:
                post_to_social_media(video_file, seo_data)
            
            memory[memory_key] = content
            memory_changed = True
        else:
            logging.info(f"zzz No new {content_type}s.")

    if memory_changed:
        with open(MEMORY_FILE, "w") as f:
            json.dump(memory, f, indent=4)

if __name__ == "__main__":
    main()
