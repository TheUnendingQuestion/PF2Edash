from supabase import create_client, Client

# Use your exact Supabase project URL and legacy JWT key
SUPABASE_URL = "https://dgsqiohgkkbjlgwfspwm.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImRnc3Fpb2hna2tiamxnd2ZzcHdtIiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTI1MTQwMzUsImV4cCI6MjEwODA5MDAzNX0.iJpDiVaLqi-yY-KW4aHvXz8maJ9UT2F8VsWKuI-ohXA"

def test_connection():
    try:
        print("Initializing Supabase client...")
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        
        print("Querying 'event_logs' table...")
        response = supabase.table("event_logs").select("*").limit(5).execute()
        
        print("\nSUCCESS! Connection established and data retrieved:")
        print(response.data)
    except Exception as e:
        print("\nCONNECTION FAILED:")
        print(e)

if __name__ == "__main__":
    test_connection()
