import os
import json
import logging
import requests
import subprocess
from PIL import Image

# --- THE PILLOW 10 PATCH FOR MOVIEPY ---
if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.LANCZOS
# ---------------------------------------

from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync
from google import genai
from moviepy.editor import ImageClip, CompositeVideoClip, ColorClip, AudioFileClip

# --- CONFIGURATION ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID") 

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
            
            try:
                close_button = page.locator("button.wa-widget-close")
                close_button.first.click(timeout=5000)
                page.wait_for_timeout(1000) 
            except Exception:
                pass

            page.wait_for_selector(selector, timeout=45000)
            elements = page.query_selector_all(selector)
            extracted_text = "\n".join([el.inner_text() for el in elements])
            
            if len(elements) > 0:
               elements[0].screenshot(path="movie.png")
               logging.info("📸 Captured screenshot of new content!")
               
            return extracted_text
        except Exception as e:
            logging.error(f"❌ Scraping failed: {e}")
            return None
        finally:
            browser.close()

def generate_seo_brain(new_text, content_type):
    """Uses Gemini to generate Kinyarwanda text AND an English Voiceover Script."""
    logging.info("🧠 Booting up Gemini Director Brain...")
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        prompt = f"""
        Act as a Hollywood movie trailer director and a Rwandan social media manager.
        I am giving you the newest {content_type} uploaded to our site.

        You MUST return the output ONLY as a valid JSON object with these exact keys:
        - "title": A short, exciting title for the Telegram post.
        - "caption": A hype description in Kinyarwanda ending with a call to action.
        - "hashtags": A string of 10 trending hashtags.
        - "voiceover_script": An epic, dramatic 15-second movie trailer script in ENGLISH (Max 30 words). Make it sound like a cinematic ad (e.g., "Get ready... The most anticipated movie is finally here..."). Do not use special characters.

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
            "caption": "🔥 Iyi movie nshya yageze kuri site!",
            "hashtags": "#Agasobanuye",
            "voiceover_script": "Get ready for the ultimate cinematic experience. The newest blockbuster is streaming now. Do not miss it."
        }

def generate_ai_voiceover(script_text, output_filename="voice.mp3"):
    """Uses Edge-TTS to generate a cinematic AI voice."""
    logging.info("🎙️ Recording AI Voiceover...")
    try:
        # en-US-ChristopherNeural is a deep, cinematic male voice
        command = f'edge-tts --voice en-US-ChristopherNeural --text "{script_text}" --write-media {output_filename}'
        subprocess.run(command, shell=True, check=True)
        logging.info("✅ AI Voiceover recorded!")
        return output_filename
    except Exception as e:
        logging.error(f"❌ Voiceover generation failed: {e}")
        return None

def render_cinematic_ad(image_path, audio_path, output_name="final_ad.mp4"):
    """Merges the movie poster and the AI voiceover into a cinematic video."""
    try:
        logging.info("🎬 Rendering cinematic video via MoviePy...")
        
        # Load the AI Voice
        voice_clip = AudioFileClip(audio_path)
        video_duration = voice_clip.duration + 1.0 # Add 1 second for a smooth ending
        
        # Load the Movie Poster
        main_img = ImageClip(image_path).set_duration(video_duration)
        
        # Create a cinematic dark background
        background = ColorClip(size=(1080, 1920), color=(10, 10, 10)).set_duration(video_duration)
        
        # Resize image to fit nicely
        main_img = main_img.resize(width=1000)
        
        # Combine them
        final_video = CompositeVideoClip([background, main_img.set_position("center")])
        
        # Attach the AI voice to the video!
        final_video = final_video.set_audio(voice_clip)
        
        final_video.write_videofile(output_name, fps=24, codec="libx264", audio_codec="aac", logger=None)
        logging.info("✅ Cinematic Ad rendered successfully!")
        return output_name
    except Exception as e:
        logging.error(f"❌ Video rendering failed: {e}")
        return None

def post_to_telegram(video_path, seo_data):
    """Pushes the video ad and Kinyarwanda caption to Telegram."""
    logging.info("🚀 Uplinking to Telegram Channel...")
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo"
    formatted_caption = f"🎬 {seo_data.get('title', '')}\n\n{seo_data.get('caption', '')}\n\n{seo_data.get('hashtags', '')}"
    
    try:
        with open(video_path, "rb") as video_file:
            payload = {"chat_id": TELEGRAM_CHANNEL_ID, "caption": formatted_caption}
            files = {"video": video_file}
            response = requests.post(url, data=payload, files=files)
            response.raise_for_status()
            logging.info("✅ BOOM! Cinematic Ad broadcasted to Telegram!")
    except Exception as e:
        logging.error(f"❌ Telegram upload failed: {e}")

def main():
    if not all([GEMINI_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID]):
        logging.error("🚨 Missing API Keys!")
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

        # To test every time, you can temporarily comment out the 'if content != saved_text:' line
        if content != saved_text:
            logging.info(f"🚨 NEW {content_type.upper()} DETECTED! Igniting Studio...")
            
            # Phase 1: Script Writing
            seo_data = generate_seo_brain(content, content_type)
            
            # Phase 2: Voice Actor
            script = seo_data.get("voiceover_script", "Get ready for the new release.")
            audio_file = generate_ai_voiceover(script)
            
            # Phase 3: Video Assembly
            if audio_file:
                video_file = render_cinematic_ad("movie.png", audio_file)
                
                # Phase 4: Distribution
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
