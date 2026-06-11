import requests
import json

BASE_URL = "http://127.0.0.1:8001/api"

def test_signup_flow():
    signup_url = f"{BASE_URL}/signup/"
    payload = {
        "username": "testuser_saas",
        "email": "test@saas.com",
        "password": "Password123!",
        "company_name": "Test SaaS Company"
    }
    
    print(f"--- Attempting Signup for: {payload['email']} ---")
    response = requests.post(signup_url, json=payload)
    
    if response.status_code == 201:
        print("Signup Successful!")
        data = response.json()
        print(json.dumps(data, indent=2))
        
        # Now login to get token
        login_url = f"{BASE_URL}/login/"
        login_payload = {
            "username": payload["username"],
            "password": payload["password"]
        }
        print("--- Attempting Login ---")
        login_res = requests.post(login_url, json=login_payload)
        if login_res.status_code == 200:
            return login_res.json()['access']
        else:
            print(f"Login Failed: {login_res.status_code}")
            print(login_res.text)
            return None
    elif response.status_code == 400 and 'username' in response.text:
       print("User already exists, attempting login...")
       login_url = f"{BASE_URL}/login/"
       login_payload = {
           "username": payload["username"],
           "password": payload["password"]
       }
       login_res = requests.post(login_url, json=login_payload)
       if login_res.status_code == 200:
           return login_res.json()['access']
       return None
    else:
        print(f"Signup Failed: {response.status_code}")
        print(response.text)
        return None

def test_sync_pull(token):
    pull_url = f"{BASE_URL}/erp/sync/pull/"
    headers = {"Authorization": f"Bearer {token}"}
    
    print("\n--- Attempting Sync Pull (Electron Simulation) ---")
    response = requests.post(pull_url, headers=headers, json={"last_sync": None})
    
    if response.status_code == 200:
        print("Sync Pull Successful!")
        data = response.json()
        print(f"Company: {data.get('company_name')} (ID: {data.get('company_id')})")
        print(f"Stores Found: {len(data['changes']['stores'])}")
        print(f"Users Found: {len(data['changes']['users'])}")
        
        # Verify the admin ERPUser is there
        for user in data['changes']['users']:
            print(f" - Found ERPUser: {user['email']} (Role: {user['role']})")
            print(f" - Store Access: {user['store_ids']}")
    else:
        print(f"Sync Pull Failed: {response.status_code}")
        print(response.text)

if __name__ == "__main__":
    token = test_signup_flow()
    if token:
        test_sync_pull(token)
