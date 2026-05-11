import csv
from google import genai

# Configuration
API_KEY = "xxxxxxxxxxxxxxxx"
TXT_FILENAME = "models_raw_data.txt"
CSV_FILENAME = "models_overview.csv"

# Headers for CSV - items you likely want to sort/filter by
CSV_HEADERS = [
    "display_name",
    "name",
    "version",
    "thinking",  # New field check
    "input_token_limit",
    "output_token_limit",
    "temperature",
    "top_p",
    "top_k",
    "description",
    "supported_actions"
]

def fetch_and_save_models():
    """
    Fetches models from Google GenAI, saves raw data to TXT,
    and structured summary to CSV.
    """
    try:
        client = genai.Client(api_key=API_KEY)
        
        print(f"Starting model fetch...")
        print(f" > Raw data will be saved to: {TXT_FILENAME}")
        print(f" > CSV table will be saved to: {CSV_FILENAME}")

        with open(TXT_FILENAME, "w", encoding="utf-8") as f_txt, \
             open(CSV_FILENAME, "w", encoding="utf-8", newline="") as f_csv:

            # Initialize CSV writer
            writer = csv.DictWriter(f_csv, fieldnames=CSV_HEADERS)
            writer.writeheader()

            model_count = 0
            
            # Iterate through models
            for m in client.models.list():
                model_count += 1
                
                # --- 1. Write to TXT (Raw Data as requested) ---
                # We intentionally use str(m) to keep the exact raw representation
                f_txt.write("===================\n")
                f_txt.write(str(m) + "\n")

                # --- 2. Write to CSV (Structured View) ---
                row_data = {}
                for header in CSV_HEADERS:
                    # Use getattr to safely retrieve attributes even if SDK changes
                    value = getattr(m, header, None)
                    row_data[header] = value
                
                writer.writerow(row_data)
                
                # Print simplified progress to console
                d_name = getattr(m, 'display_name', 'Unknown')
                m_name = getattr(m, 'name', 'Unknown')
                print(f"[{model_count}] Processed: {d_name:<25} ({m_name})")

        print("-" * 60)
        print(f"✅ Success! Found {model_count} models.")

    except Exception as e:
        print(f"❌ Error occurred: {e}")

if __name__ == "__main__":
    fetch_and_save_models()