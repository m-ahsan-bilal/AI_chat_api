import requests
import json

# Test script to verify your API
API_BASE = "http://localhost:8000"

def test_api():
    print("🧪 Testing Trivia Game API...")
    print("=" * 50)
    
    try:
        # Test 1: Health check
        print("1️⃣ Testing health endpoint...")
        response = requests.get(f"{API_BASE}/health")
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.json()}")
        print()
        
        # Test 2: Register user
        print("2️⃣ Testing user registration...")
        register_data = {"username": "testuser123"}
        response = requests.post(f"{API_BASE}/register", json=register_data)
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            user_data = response.json()
            user_id = user_data["user_id"]
            print(f"   ✅ User registered! ID: {user_id}")
        else:
            print(f"   ❌ Registration failed: {response.text}")
            return
        print()
        
        # Test 3: Create lobby
        print("3️⃣ Testing lobby creation...")
        lobby_data = {
            "name": "Test Lobby",
            "max_humans": 5,
            "max_bots": 0,
            "is_private": False
        }
        response = requests.post(f"{API_BASE}/lobbies", json=lobby_data)
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            lobby_info = response.json()
            lobby_id = lobby_info["lobby_id"]
            invite_code = lobby_info["invite_code"]
            print(f"   ✅ Lobby created!")
            print(f"   Lobby ID: {lobby_id}")
            print(f"   Invite Code: {invite_code}")
        else:
            print(f"   ❌ Lobby creation failed: {response.text}")
            return
        print()
        
        # Test 4: List lobbies
        print("4️⃣ Testing lobby list...")
        response = requests.get(f"{API_BASE}/lobbies")
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            lobbies = response.json()
            print(f"   ✅ Found {len(lobbies)} lobbies")
            for lobby in lobbies:
                print(f"   - {lobby['name']} ({lobby['current_players']}/{lobby['max_humans']} players)")
        else:
            print(f"   ❌ Failed to get lobbies: {response.text}")
        print()
        
        # Test 5: Join lobby
        print("5️⃣ Testing lobby join...")
        join_data = {
            "invite_code": invite_code,
            "user_id": user_id
        }
        response = requests.post(f"{API_BASE}/lobbies/join-invite", json=join_data)
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            join_result = response.json()
            print(f"   ✅ {join_result['message']}")
        else:
            print(f"   ❌ Join failed: {response.text}")
        print()
        
        print("🎉 All basic API tests completed!")
        print(f"🌐 Your API is running at: {API_BASE}")
        print(f"📚 API docs available at: {API_BASE}/docs")
        
    except requests.exceptions.ConnectionError:
        print("❌ Connection Error!")
        print("Make sure your FastAPI server is running:")
        print("   uvicorn main:app --reload --host 0.0.0.0 --port 8000")
        print()
    except Exception as e:
        print(f"❌ Unexpected error: {e}")

if __name__ == "__main__":
    test_api()