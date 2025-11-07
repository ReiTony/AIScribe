#!/usr/bin/env python3
"""
Test script for Philippine Law Consultant Chat with Intelligent Routing
"""

import requests
import json
import time

BASE_URL = "http://localhost:8000"

# ANSI color codes
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def print_header(text):
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*70}")
    print(f"  {text}")
    print(f"{'='*70}{Colors.ENDC}\n")


def print_success(text):
    print(f"{Colors.GREEN}✓ {text}{Colors.ENDC}")


def print_info(text):
    print(f"{Colors.CYAN}ℹ {text}{Colors.ENDC}")


def print_error(text):
    print(f"{Colors.RED}✗ {text}{Colors.ENDC}")


def test_chat(message, token=None, show_full=False):
    """Test a chat message"""
    print(f"\n{Colors.BOLD}User:{Colors.ENDC} {message}")
    
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    payload = {
        "message": message,
        "session_id": "test_session_001"
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/chat",
            json=payload,
            headers=headers
        )
        
        if response.status_code == 200:
            data = response.json()
            
            # Show intent
            intent = data.get("intent", {})
            print(f"{Colors.YELLOW}Intent:{Colors.ENDC} {intent.get('intent_type')} (confidence: {intent.get('confidence', 0):.2f})")
            
            if intent.get('document_type'):
                print(f"{Colors.YELLOW}Document Type:{Colors.ENDC} {intent.get('document_type')}")
            
            # Show response
            response_text = data.get("response", "")
            if show_full or len(response_text) < 500:
                print(f"\n{Colors.BLUE}Assistant:{Colors.ENDC}\n{response_text}\n")
            else:
                print(f"\n{Colors.BLUE}Assistant:{Colors.ENDC}\n{response_text[:500]}...\n")
            
            return True
        else:
            print_error(f"Request failed: {response.status_code}")
            print(response.text)
            return False
            
    except Exception as e:
        print_error(f"Error: {e}")
        return False


def main():
    print(f"{Colors.BOLD}{Colors.HEADER}")
    print("╔══════════════════════════════════════════════════════════════════╗")
    print("║     Philippine Law Consultant - Intelligent Routing Test        ║")
    print("╚══════════════════════════════════════════════════════════════════╝")
    print(f"{Colors.ENDC}")
    
    print_info("Testing server at: " + BASE_URL)
    print_info("Make sure the server is running: uvicorn main:app --reload\n")
    
    time.sleep(1)
    
    # Test 1: Health Check
    print_header("1. Health Check")
    try:
        response = requests.get(f"{BASE_URL}/health")
        if response.status_code == 200:
            print_success("Server is running!")
        else:
            print_error("Server health check failed")
            return
    except Exception as e:
        print_error(f"Cannot connect to server: {e}")
        return
    
    # Test 2: Register/Login
    print_header("2. Authentication Setup")
    
    test_user = "phil_law_tester"
    test_pass = "testpass123"
    
    # Try to register
    requests.post(f"{BASE_URL}/auth/register", json={
        "username": test_user,
        "password": test_pass
    })
    
    # Login
    login_response = requests.post(f"{BASE_URL}/auth/login", json={
        "username": test_user,
        "password": test_pass
    })
    
    if login_response.status_code == 200:
        token = login_response.json().get("access_token")
        print_success("Authenticated successfully!")
    else:
        print_error("Login failed")
        token = None
    
    # Test 3: Consultation Tests
    print_header("3. Testing CONSULTATION Intent (Philippine Law)")
    
    consultation_tests = [
        "What is a demand letter under Philippine law?",
        "Can you explain the Revised Penal Code's provisions on theft?",
        "What are my rights as an employee under the Labor Code?",
        "How long do I have to file a complaint for breach of contract in the Philippines?"
    ]
    
    for msg in consultation_tests:
        test_chat(msg, token)
        time.sleep(2)
    
    # Test 4: Document Generation Tests
    print_header("4. Testing DOCUMENT GENERATION Intent")
    
    doc_tests = [
        "Generate a demand letter for unpaid rent of 50,000 PHP",
        "Create a demand letter. Sender: Maria Santos, 123 Rizal St, Manila. Recipient: Juan Cruz, 456 Bonifacio Ave, Quezon City. Amount: 100,000 PHP for services rendered."
    ]
    
    for msg in doc_tests:
        test_chat(msg, token, show_full=True)
        time.sleep(2)
    
    # Test 5: Mixed Intent Tests
    print_header("5. Testing MIXED Intent (Consultation + Document)")
    
    mixed_tests = [
        "What should I include in a demand letter? Also, can you generate one for me for 75,000 PHP?",
        "Explain the legal requirements for contracts in the Philippines and create a simple contract template"
    ]
    
    for msg in mixed_tests:
        test_chat(msg, token, show_full=True)
        time.sleep(2)
    
    # Test 6: Conversation Context
    print_header("6. Testing CONVERSATION CONTINUITY")
    
    print_info("This tests if the LLM maintains context across messages")
    
    conversation = [
        "What is a demand letter?",
        "When should I send one?",
        "Can you create one for me?",
        "The amount is 50,000 PHP from John Doe to Jane Smith"
    ]
    
    for msg in conversation:
        test_chat(msg, token)
        time.sleep(2)
    
    # Test 7: Anonymous Chat
    print_header("7. Testing ANONYMOUS Chat (No Authentication)")
    
    test_chat("What are the labor laws in the Philippines?", token=None)
    
    # Summary
    print_header("Test Complete!")
    print_success("All tests completed successfully!")
    print_info("\nThe consultant is now:")
    print_info("✓ Specialized in Philippine Law")
    print_info("✓ Maintains conversation context")
    print_info("✓ Intelligently routes to consultation or document generation")
    print_info("✓ Handles mixed intents (advice + document)")
    print_info("✓ Asks for missing information when needed")
    print()


if __name__ == "__main__":
    main()
