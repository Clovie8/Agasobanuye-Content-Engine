import os
import json
import logging
import requests
from PIL import Image

# --- THE PILLOW 10 PATCH FOR MOVIEPY ---
if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.LANCZOS
# ---------------------------------------
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync
from google import genai
from moviepy.editor import ImageClip, CompositeVideoClip, ColorClip

# --- CONFIGURATION ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID") # e.g., "@theonemovies_test"

SITES_FILE = "sites.json"
MEMORY_FILE = "memory.json"

def get_page_content(url, selector):
    """Scrapes the website and saves a screenshot of the new movie."""
    logging.info(f"🔍 Scanning {url}...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        stealth_sync(page)
        try:
            # FIX 1: Wait for 'networkidle' instead of 'domcontentloaded'. 
            # This forces the bot to wait until all JavaScript and images finish loading!
            page.goto(url, wait_until="networkidle", timeout=60000)

            # --- NEW: CLOSE THE WHATSAPP POPUP ---
            try:
                # Target the exact class of your specific WhatsApp widget close button
                close_button = page.locator("button.wa-widget-close")
                close_button.first.click(timeout=5000)
                logging.info("🧹 Closed the WhatsApp community popup!")
                
                # Wait 1 second for the fade-out animation to finish so it isn't in the screenshot
                page.wait_for_timeout(1000) 
            except Exception:
                # If the popup isn't there, just ignore it and move on!
                pass
            # --------------------------------------
            
            # Popup Assassin
            try:
                close_button = page.locator("button.wa-widget-close")
                close_button.first.click(timeout=5000)
                page.wait_for_timeout(1000) 
            except Exception:
                pass

            # FIX 2: Give it 45 seconds to find the selector just in case the server is slow
            page.wait_for_selector(selector, timeout=45000)
            elements = page.query_selector_all(selector)
            extracted_text = "\n".join([el.inner_text() for el in elements])
            
            if len(elements) > 0:
               elements[0].screenshot(path="movie.png")
               logging.info("📸 Captured screenshot of new content!")
               
            return extracted_text
        except Exception as e:
            logging.error(f"❌ Scraping failed: {e}")
            
            # FIX 3: THE DEBUGGER. If it crashes, take a picture of the page so we can see why!
            try:
                page.screenshot(path="debug_error.png")
                logging.info("📸 Saved a debug screenshot (debug_error.png).")
            except:
                pass
                
            return None
        finally:
            browser.close()
            
def generate_seo_brain(new_text, content_type):
    """Uses Gemini 2.5 Flash to generate viral Kinyarwanda/English SEO content as JSON."""
    logging.info("🧠 Booting up Gemini Kinyarwanda SEO Brain...")
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        prompt = f"""
        Act as a viral social media marketer in Rwanda specializing in Agasobanuye movies.
        I am giving you the newest {content_type} uploaded to the streaming site.

        Your job is to extract the details and write a highly engaging caption mixing Kinyarwanda and English. 
        You MUST return the output ONLY as a valid JSON object with these exact keys:
        - "title": A short, exciting title for the video.
        - "caption": A hype description ending with a call to action to watch on the site. Use emojis.
        - "hashtags": A string of 10 trending hashtags (e.g., "#Agasobanuye #Kinyarwanda #MoviesRwanda").

        NEW WEBSITE TEXT:
        {new_text[:1500]}
        """
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        raw_json = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(raw_json)
    except Exception as e:
        logging.error(f"❌ SEO Brain failed: {e}")
        return {
            "title": "New Release! 🎬",
            "caption": "🔥 Iyi movie nshya yageze kuri site! Watch now on TheOneMovies.com!",
            "hashtags": "#TheOneMovies #Agasobanuye #Rwanda"
        }

def render_vertical_video(image_path, output_name="final_short.mp4"):
    """Converts the horizontal screenshot into a 10-second vertical video."""
    try:
        logging.info("🎬 Rendering vertical video via MoviePy...")
        main_img = ImageClip(image_path).set_duration(10)
        background = ColorClip(size=(1080, 1920), color=(15, 15, 15)).set_duration(10)
        main_img = main_img.resize(width=1000)
        final_video = CompositeVideoClip([background, main_img.set_position("center")])
        final_video.write_videofile(output_name, fps=24, codec="libx264", audio=False, logger=None)
        logging.info("✅ Video rendered successfully!")
        return output_name
    except Exception as e:
        logging.error(f"❌ Video rendering failed: {e}")
        return None

def post_to_telegram(video_path, seo_data):
    """Pushes the rendered .mp4 and Gemini caption directly to Telegram."""
    logging.info("🚀 Uplinking to Telegram Channel...")
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo"
    
    # Combine the Gemini JSON data into one beautiful text block
    formatted_caption = f"{seo_data.get('title', '')}\n\n{seo_data.get('caption', '')}\n\n{seo_data.get('hashtags', '')}"
    
    try:
        with open(video_path, "rb") as video_file:
            payload = {
                "chat_id": TELEGRAM_CHANNEL_ID,
                "caption": formatted_caption
            }
            files = {
                "video": video_file
            }
            
            response = requests.post(url, data=payload, files=files)
            response.raise_for_status()
            logging.info("✅ BOOM! Content successfully broadcasted to Telegram!")
            
    except Exception as e:
        logging.error(f"❌ Telegram upload failed: {e}")
        if 'response' in locals() and response:
            logging.error(f"Telegram Error Details: {response.text}")

def main():
    if not all([GEMINI_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID]):
        logging.error("🚨 Missing API Keys! Check your environment variables/GitHub Secrets.")
        return

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
        content_type = site.get("type", "Movie")
        memory_key = f"{url}_{selector}"

        content = get_page_content(url, selector)
        if not content:
            continue

        saved_text = memory.get(memory_key, "")

        if content != saved_text:
            logging.info(f"🚨 NEW {content_type.upper()} DETECTED! Igniting Content Engine...")
            
            # Phase 1: Brain
            seo_data = generate_seo_brain(content, content_type)
            
            # Phase 2: Studio
            video_file = render_vertical_video("movie.png")
            
            # Phase 3: Uplink
            if video_file:
                post_to_telegram(video_file, seo_data)
            
            memory[memory_key] = content
            memory_changed = True
        else:
            logging.info(f"zzz No new {content_type}s found.")

    if memory_changed:
        with open(MEMORY_FILE, "w") as f:
            json.dump(memory, f, indent=4)

if __name__ == "__main__":
    main()
