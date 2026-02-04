import requests
import json
import time

BASE_URL = "http://localhost:8000"

def test_all_endpoints():
    print("🚀 Testing FastAPI Backend Endpoints")
    print("=" * 60)
    
    # 1. Test root endpoint
    print("\n1. GET /")
    try:
        response = requests.get(f"{BASE_URL}/")
        print(f"   Status: {response.status_code}")
        print(f"   Response: {json.dumps(response.json(), indent=2)}")
    except Exception as e:
        print(f"   Error: {e}")
    
    # 2. Test health endpoint
    print("\n2. GET /health")
    try:
        response = requests.get(f"{BASE_URL}/health")
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.json()}")
    except Exception as e:
        print(f"   Error: {e}")
    
    # 3. Test chat endpoint (JSON)
    print("\n3. POST /chat")
    chat_data = {
        "session_id": "test_session_123",
        "user_text": "I really enjoyed the VR experience in the exhibition!",
        "context": {
            "mode": "exhibit_feedback",
            "exhibit_id": "vr_section_1"
        }
    }
    try:
        response = requests.post(f"{BASE_URL}/chat", json=chat_data)
        print(f"   Status: {response.status_code}")
        print(f"   Response: {json.dumps(response.json(), indent=2)}")
    except Exception as e:
        print(f"   Error: {e}")
    
    # 4. Test STT endpoint (JSON version)
    print("\n4. POST /stt_json")
    stt_data = {
        "session_id": "test_session_123",
        "language": "en-US",
        "sample_rate": 16000
    }
    try:
        response = requests.post(f"{BASE_URL}/stt_json", json=stt_data)
        print(f"   Status: {response.status_code}")
        print(f"   Response: {json.dumps(response.json(), indent=2)}")
    except Exception as e:
        print(f"   Error: {e}")
    
    # 5. Test API documentation
    print("\n5. API Documentation")
    print(f"   Swagger UI: {BASE_URL}/docs")
    print(f"   ReDoc: {BASE_URL}/redoc")
    
    print("\n" + "=" * 60)
    print("✅ All tests completed!")

if __name__ == "__main__":
    print("Make sure the FastAPI server is running on port 8000")
    print("Run: uvicorn app:app --reload --host 0.0.0.0 --port 8000")
    print("-" * 60)
    
    # Give user time to start server
    input("Press Enter when server is running...")
    test_all_endpoints()
    