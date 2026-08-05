import os
import requests
from playwright.sync_api import sync_playwright
from google import genai

URL = "https://app.the-trackr.com/uk-finance/graduate-programmes"
SNAPSHOT_FILE = "previous_snapshot.txt"

def fetch_page_text():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(URL, wait_until="networkidle")
        page.wait_for_timeout(3000)
        text_content = page.evaluate("() => document.body.innerText")
        browser.close()
        return text_content[:15000]

def send_telegram(message):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("Missing Telegram credentials.")
        return
        
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    # Removed parse_mode to prevent Markdown formatting silent drops
    response = requests.post(url, json={"chat_id": chat_id, "text": message})
    
    # Print result to logs so we can see if Telegram accepted it
    if response.status_code == 200:
        print("Telegram message delivered successfully!")
    else:
        print(f"Telegram failed with status code {response.status_code}: {response.text}")

def main():
    print("Fetching page content...")
    current_text = fetch_page_text()
    
    previous_text = ""
    if os.path.exists(SNAPSHOT_FILE):
        with open(SNAPSHOT_FILE, "r", encoding="utf-8") as f:
            previous_text = f.read()
            
    if not previous_text:
        print("First run detected. Storing baseline snapshot...")
        with open(SNAPSHOT_FILE, "w", encoding="utf-8") as f:
            f.write(current_text)
        send_telegram("🚀 Trackr Bot Initialized!\nBaseline snapshot created. You'll receive daily alerts when new finance graduate schemes open.")
        return

    print("Analyzing changes using Gemini...")
    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    
    prompt = f"""
    You are an automated job tracking assistant.
    Compare these two text dumps from a UK Finance Graduate Scheme tracker page.
    
    PREVIOUS SNAPSHOT:
    {previous_text[:6000]}
    
    CURRENT SNAPSHOT:
    {current_text[:6000]}
    
    Task:
    1. Identify any NEW graduate schemes that opened, deadline updates, or status changes.
    2. STRICT FILTERING RULE: Completely IGNORE and EXCLUDE any roles falling under these subcategories:
       - Bulge Bracket
       - Elite Boutique
       - Buy-Side
       - Trading & Quant
       - Real Estate
    3. Ignore minor visual or layout updates.
    4. If there are NO new graduate programs or major updates in the remaining allowed categories, reply strictly with: "NO_CHANGES"
    5. If there ARE relevant new programs, return a concise summary listing Company, Role Title, Category, and Status/Deadline.
    """
    
    print("Querying Google AI for authorized models...")
    candidate_models = []
    try:
        for m in client.models.list():
            if "flash" in m.name.lower() or "pro" in m.name.lower():
                clean_name = m.name.replace("models/", "")
                candidate_models.append(clean_name)
    except Exception as e:
        print(f"Failed to list models from API: {e}")
        
    print(f"Discovered authorized models: {candidate_models}")
    
    response = None
    for model_name in candidate_models:
        try:
            print(f"Attempting analysis with {model_name}...")
            response = client.models.generate_content(
                model=model_name,
                contents=prompt
            )
            print(f"Successfully used model: {model_name}")
            break
        except Exception as e:
            print(f"Model {model_name} failed: {e}")
            continue
            
    if not response:
        raise RuntimeError("Could not generate content with ANY discovered model. Your API key may have text generation completely restricted.")
    
    analysis = response.text.strip()
    
    if "NO_CHANGES" in analysis:
        print("No updates detected on target page.")
    else:
        print("New updates found! Sending notification...")
        send_telegram(f"🔔 Trackr Alert: New Graduate Schemes Found!\n\n{analysis}")
        
        with open(SNAPSHOT_FILE, "w", encoding="utf-8") as f:
            f.write(current_text)

if __name__ == "__main__":
    main()
