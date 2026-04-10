import os
from groq import Groq

def test_groq():
    api_key = os.environ.get("GROQ_API_KEY", "test_key")
    try:
        client = Groq(api_key=api_key)
        print("Groq client initialized successfully")
    except Exception as e:
        print(f"Error initializing Groq client: {e}")

if __name__ == "__main__":
    test_groq()
