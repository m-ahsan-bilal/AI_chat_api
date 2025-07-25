import requests
import json
import time
import websocket
import threading
from datetime import datetime

# Configuration - Update this URL after Railway deployment
API_BASE = "http://localhost:8000"  # For local testing
# API_BASE = "https://your-app-name.up.railway.app"  # For Railway testing

class APITester:
    def __init__(self):
        self.user_id = None
        self.lobby_id = None
        self.invite_code = None
        self.ws = None
        
    def print_header(self, title):
        print(f"\n{'='*60}")
        print(f"🧪 {title}")
        print(f"{'='*60}")
    
    def print_test(self, test_num, description):
        print(f"\n{test_num} {description}")
        print("-" * 40)
    
    def test_health(self):
        """Test 1: Health check endpoint"""
        self.print_test("1️⃣", "Testing health endpoint...")
        
        try:
            response = requests.get(f"{API_BASE}/health", timeout=10)
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                health_data = response.json()
                print(f"   ✅ Server is healthy!")
                print(f"   📊 Stats:")
                print(f"      - Users: {health_data.get('users', 0)}")
                print(f"      - Lobbies: {health_data.get('lobbies', 0)}")
                print(f"      - Active WebSockets: {health_data.get('active_ws', 0)}")
                
                ai_config = health_data.get('ai_config', {})
                print(f"   🤖 AI Configuration:")
                print(f"      - Hugging Face: {'✅' if ai_config.get('huggingface_available') else '❌'}")
                print(f"      - Ollama: {'✅' if ai_config.get('ollama_available') else '❌'}")
                print(f"      - Enhanced Rules: {'✅' if ai_config.get('enhanced_rules') else '❌'}")
                return True
            else:
                print(f"   ❌ Health check failed: {response.text}")
                return False
                
        except requests.exceptions.ConnectionError:
            print("   ❌ Connection Error! Server not running.")
            return False
        except Exception as e:
            print(f"   ❌ Error: {e}")
            return False
    
    def test_register(self):
        """Test 2: User registration"""
        self.print_test("2️⃣", "Testing user registration...")
        
        try:
            # Try to register a user
            username = f"testuser_{int(time.time())}"
            register_data = {"username": username}
            
            response = requests.post(f"{API_BASE}/register", json=register_data, timeout=10)
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                user_data = response.json()
                self.user_id = user_data["user_id"]
                print(f"   ✅ User registered successfully!")
                print(f"   👤 Username: {username}")
                print(f"   🆔 User ID: {self.user_id}")
                
                # Test duplicate username
                print(f"   🔄 Testing duplicate username...")
                duplicate_response = requests.post(f"{API_BASE}/register", json=register_data, timeout=10)
                if duplicate_response.status_code == 400:
                    print(f"   ✅ Duplicate username properly rejected")
                else:
                    print(f"   ⚠️  Duplicate username not handled properly")
                
                return True
            else:
                print(f"   ❌ Registration failed: {response.text}")
                return False
                
        except Exception as e:
            print(f"   ❌ Error: {e}")
            return False
    
    def test_lobby_creation(self):
        """Test 3: Lobby creation"""
        self.print_test("3️⃣", "Testing lobby creation...")
        
        try:
            lobby_data = {
                "name": f"Test Lobby - {datetime.now().strftime('%H:%M:%S')}",
                "max_humans": 5,
                "max_bots": 2,
                "is_private": False
            }
            
            response = requests.post(f"{API_BASE}/lobbies", json=lobby_data, timeout=10)
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                lobby_info = response.json()
                self.lobby_id = lobby_info["lobby_id"]
                self.invite_code = lobby_info["invite_code"]
                
                print(f"   ✅ Lobby created successfully!")
                print(f"   🏠 Lobby Name: {lobby_info['name']}")
                print(f"   🆔 Lobby ID: {self.lobby_id}")
                print(f"   🎫 Invite Code: {self.invite_code}")
                return True
            else:
                print(f"   ❌ Lobby creation failed: {response.text}")
                return False
                
        except Exception as e:
            print(f"   ❌ Error: {e}")
            return False
    
    def test_lobby_list(self):
        """Test 4: Lobby listing"""
        self.print_test("4️⃣", "Testing lobby list...")
        
        try:
            response = requests.get(f"{API_BASE}/lobbies", timeout=10)
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                lobbies = response.json()
                print(f"   ✅ Retrieved {len(lobbies)} lobbies")
                
                for i, lobby in enumerate(lobbies[:3], 1):  # Show first 3 lobbies
                    print(f"   🏠 Lobby {i}:")
                    print(f"      - Name: {lobby['name']}")
                    print(f"      - Players: {lobby['current_players']}/{lobby['max_humans']}")
                    print(f"      - Bots: {lobby.get('current_bots', 0)}/{lobby.get('max_bots', 0)}")
                    print(f"      - Private: {lobby['is_private']}")
                    print(f"      - Trivia Active: {lobby.get('has_trivia_active', False)}")
                
                if len(lobbies) > 3:
                    print(f"   ... and {len(lobbies) - 3} more lobbies")
                
                return True
            else:
                print(f"   ❌ Failed to get lobbies: {response.text}")
                return False
                
        except Exception as e:
            print(f"   ❌ Error: {e}")
            return False
    
    def test_lobby_join(self):
        """Test 5: Lobby joining"""
        self.print_test("5️⃣", "Testing lobby join...")
        
        if not self.user_id or not self.invite_code:
            print("   ❌ Cannot test join - missing user_id or invite_code")
            return False
        
        try:
            # Test join by invite code
            join_data = {
                "invite_code": self.invite_code,
                "user_id": self.user_id
            }
            
            response = requests.post(f"{API_BASE}/lobbies/join-invite", json=join_data, timeout=10)
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                join_result = response.json()
                print(f"   ✅ {join_result['message']}")
                
                # Test lobby info endpoint
                print(f"   🔍 Getting detailed lobby info...")
                info_response = requests.get(f"{API_BASE}/lobbies/{self.lobby_id}/info", timeout=10)
                if info_response.status_code == 200:
                    lobby_info = info_response.json()
                    print(f"   📊 Lobby Details:")
                    print(f"      - Active Users: {lobby_info.get('active_users', [])}")
                    print(f"      - Active Bots: {lobby_info.get('bots', [])}")
                    print(f"      - Message Count: {lobby_info.get('message_count', 0)}")
                
                return True
            else:
                print(f"   ❌ Join failed: {response.text}")
                return False
                
        except Exception as e:
            print(f"   ❌ Error: {e}")
            return False
    
    def test_bot_management(self):
        """Test 6: Bot management"""
        self.print_test("6️⃣", "Testing bot management...")
        
        if not self.lobby_id:
            print("   ❌ Cannot test bots - missing lobby_id")
            return False
        
        try:
            # Get available bots
            print("   🤖 Getting available bots...")
            bots_response = requests.get(f"{API_BASE}/bots", timeout=10)
            
            if bots_response.status_code == 200:
                bots_data = bots_response.json()
                available_bots = bots_data.get('available_bots', [])
                print(f"   📋 Available bots: {len(available_bots)}")
                
                for bot in available_bots:
                    print(f"      - {bot['name']}: {bot['personality']}")
            
            # Add a bot
            print(f"   ➕ Adding ChatBot to lobby...")
            add_bot_data = {"bot_name": "ChatBot"}
            add_response = requests.post(
                f"{API_BASE}/lobbies/{self.lobby_id}/add-bot", 
                json=add_bot_data, 
                timeout=10
            )
            
            if add_response.status_code == 200:
                result = add_response.json()
                print(f"   ✅ {result['message']}")
                print(f"   🤖 Bot count: {result.get('bot_count', 'unknown')}")
                
                # Add another bot
                print(f"   ➕ Adding QuizMaster to lobby...")
                add_bot_data2 = {"bot_name": "QuizMaster"}
                add_response2 = requests.post(
                    f"{API_BASE}/lobbies/{self.lobby_id}/add-bot", 
                    json=add_bot_data2, 
                    timeout=10
                )
                
                if add_response2.status_code == 200:
                    result2 = add_response2.json()
                    print(f"   ✅ {result2['message']}")
                
                return True
            else:
                print(f"   ❌ Failed to add bot: {add_response.text}")
                return False
                
        except Exception as e:
            print(f"   ❌ Error: {e}")
            return False
    
    def test_trivia_answer(self):
        """Test 7: Trivia answer submission"""
        self.print_test("7️⃣", "Testing trivia answer submission...")
        
        if not self.lobby_id or not self.user_id:
            print("   ❌ Cannot test trivia - missing lobby_id or user_id")
            return False
        
        try:
            # Try to submit a trivia answer (this will fail if no trivia is active)
            trivia_data = {
                "user_id": self.user_id,
                "answer": 0  # First option
            }
            
            response = requests.post(
                f"{API_BASE}/lobbies/{self.lobby_id}/trivia-answer", 
                json=trivia_data, 
                timeout=10
            )
            
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                print(f"   ✅ {result['message']}")
                return True
            elif response.status_code == 400:
                print(f"   ℹ️  No active trivia round (this is expected)")
                print(f"   💡 Trivia questions appear automatically every 8 messages in chat")
                return True
            else:
                print(f"   ❌ Trivia submission failed: {response.text}")
                return False
                
        except Exception as e:
            print(f"   ❌ Error: {e}")
            return False
    
    def test_websocket_basic(self):
        """Test 8: Basic WebSocket connection"""
        self.print_test("8️⃣", "Testing WebSocket connection...")
        
        if not self.lobby_id or not self.user_id:
            print("   ❌ Cannot test WebSocket - missing lobby_id or user_id")
            return False
        
        try:
            # Convert HTTP URL to WebSocket URL
            ws_base = API_BASE.replace("http://", "ws://").replace("https://", "wss://")
            ws_url = f"{ws_base}/ws/{self.lobby_id}/{self.user_id}"
            
            print(f"   🔌 Connecting to: {ws_url}")
            
            # Simple WebSocket test
            messages_received = []
            connection_success = False
            
            def on_message(ws, message):
                try:
                    data = json.loads(message)
                    messages_received.append(data)
                    print(f"   📨 Received: {data.get('type', 'unknown')} - {data.get('username', 'system')}")
                except:
                    print(f"   📨 Raw message: {message}")
            
            def on_open(ws):
                nonlocal connection_success
                connection_success = True
                print(f"   ✅ WebSocket connected!")
                
                # Send a test message
                test_message = {
                    "type": "message",
                    "message": "Hello from API test! 🧪"
                }
                ws.send(json.dumps(test_message))
                print(f"   📤 Sent test message")
                
                # Wait a bit then close
                time.sleep(2)
                ws.close()
            
            def on_error(ws, error):
                print(f"   ❌ WebSocket error: {error}")
            
            def on_close(ws, close_status_code, close_msg):
                print(f"   🔌 WebSocket closed")
            
            # Create WebSocket connection with timeout
            ws = websocket.WebSocketApp(
                ws_url,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close
            )
            
            # Run WebSocket in a separate thread with timeout
            ws_thread = threading.Thread(target=ws.run_forever)
            ws_thread.daemon = True
            ws_thread.start()
            
            # Wait for connection or timeout
            timeout = 10
            start_time = time.time()
            while not connection_success and (time.time() - start_time) < timeout:
                time.sleep(0.1)
            
            if connection_success:
                # Wait a bit more for messages
                time.sleep(3)
                print(f"   📊 Received {len(messages_received)} messages")
                return True
            else:
                print(f"   ❌ WebSocket connection timeout")
                return False
                
        except Exception as e:
            print(f"   ❌ WebSocket error: {e}")
            return False
    
    def run_all_tests(self):
        """Run complete API test suite"""
        self.print_header("AI TRIVIA CHAT API TEST SUITE")
        print(f"🌐 Testing API at: {API_BASE}")
        print(f"🕐 Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        tests = [
            ("Health Check", self.test_health),
            ("User Registration", self.test_register),
            ("Lobby Creation", self.test_lobby_creation),
            ("Lobby Listing", self.test_lobby_list),
            ("Lobby Joining", self.test_lobby_join),
            ("Bot Management", self.test_bot_management),
            ("Trivia Answers", self.test_trivia_answer),
            ("WebSocket Connection", self.test_websocket_basic),
        ]
        
        results = []
        
        for test_name, test_func in tests:
            try:
                success = test_func()
                results.append((test_name, success))
                
                if not success and test_name in ["Health Check", "User Registration"]:
                    print(f"\n❌ Critical test failed: {test_name}")
                    print("   Cannot continue with remaining tests.")
                    break
                    
            except KeyboardInterrupt:
                print(f"\n⏹️  Test interrupted by user")
                break
            except Exception as e:
                print(f"\n💥 Unexpected error in {test_name}: {e}")
                results.append((test_name, False))
        
        # Print summary
        self.print_header("TEST RESULTS SUMMARY")
        
        passed = sum(1 for _, success in results if success)
        total = len(results)
        
        print(f"📊 Tests Run: {total}")
        print(f"✅ Passed: {passed}")
        print(f"❌ Failed: {total - passed}")
        print(f"📈 Success Rate: {(passed/total)*100:.1f}%")
        
        print(f"\n📋 Detailed Results:")
        for test_name, success in results:
            status = "✅ PASS" if success else "❌ FAIL"
            print(f"   {status} - {test_name}")
        
        if passed == total:
            print(f"\n🎉 ALL TESTS PASSED! Your API is working perfectly!")
        elif passed >= total * 0.8:
            print(f"\n👍 Most tests passed! Your API is mostly functional.")
        else:
            print(f"\n⚠️  Several tests failed. Check your API configuration.")
        
        print(f"\n📚 API Documentation: {API_BASE}/docs")
        print(f"🔍 Interactive API: {API_BASE}/redoc")

def main():
    print("🚀 AI Trivia Chat API Tester")
    print("=" * 60)
    
    # Check if we should use Railway URL
    print("🔧 Configuration:")
    print(f"   Current API URL: {API_BASE}")
    print(f"   💡 To test Railway deployment, update API_BASE in this script")
    print()
    
    # Ask user if they want to continue
    try:
        user_input = input("Press Enter to start testing, or Ctrl+C to exit: ")
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
        return
    
    # Run tests
    tester = APITester()
    tester.run_all_tests()

if __name__ == "__main__":
    main()
