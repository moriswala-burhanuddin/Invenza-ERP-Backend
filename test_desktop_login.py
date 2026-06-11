import requests
import json

BASE_URL = "http://127.0.0.1:8000/api/v1/auth"

def test_email_login():
    login_url = f"{BASE_URL}/token/"
    # Using the credentials from the user's screenshot
    payload = {
        "email": "codecraft.burhanuddin@gmail.com",
        "password": "Invenza8325!"
    }
    
    print(f"--- Testing Desktop App Login (Email: {payload['email']}) ---")
    response = requests.post(login_url, json=payload)
    
    if response.status_code == 200:
        print("Login Successful!")
        data = response.json()
        print(f"Access Token: {data['access'][:50]}...")
        print("Sync with Electron App should now work!")
    else:
        print(f"Login Failed: {response.status_code}")
        print(response.text)

if __name__ == "__main__":
    test_email_login()
