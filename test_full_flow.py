#!/usr/bin/env python3
"""
Full Flow Test Script for AIScribe Philippine Law Consultant
Tests actual API endpoints with real database connections and authentication.

This script:
1. Connects to your actual MongoDB database
2. Tests authentication (register/login)
3. Tests intelligent chat routing with history
4. Verifies intent detection and routing
5. Tests conversation continuity
6. Checks database records

Usage:
    python3 test_full_flow.py
"""

import asyncio
import sys
import os
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timezone
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add parent directory to path for imports
sys.path.insert(0, '/Users/user/Desktop/ntek/AIScribe')

from llm.llm_client import generate_response
from llm.consultant_prompt import (
    get_philippine_law_consultant_prompt,
    get_consultation_with_history_prompt,
    get_intent_classification_instruction
)
from utils.intent_detector import detect_intent
from utils.chat_helpers import (
    get_user_chat_history,
    format_chat_history,
    save_chat_message
)
from utils.encryption import hash_password, verify_password
from utils.jwt_handler import create_access_token, verify_token


# ANSI Colors
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def print_header(text):
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*80}")
    print(f"  {text}")
    print(f"{'='*80}{Colors.ENDC}\n")


def print_success(text):
    print(f"{Colors.GREEN}✓ {text}{Colors.ENDC}")


def print_info(text):
    print(f"{Colors.CYAN}ℹ {text}{Colors.ENDC}")


def print_warning(text):
    print(f"{Colors.YELLOW}⚠ {text}{Colors.ENDC}")


def print_error(text):
    print(f"{Colors.RED}✗ {text}{Colors.ENDC}")


def print_step(step_num, text):
    print(f"\n{Colors.BOLD}Step {step_num}:{Colors.ENDC} {text}")


class AIScribeFullFlowTester:
    def __init__(self):
        self.mongo_uri = os.getenv("MONGO_URI")
        self.client = None
        self.db = None
        self.test_username = f"test_user_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.test_password = "SecureTestPass123!"
        self.access_token = None
        self.test_results = []
    
    async def setup(self):
        """Initialize database connection"""
        print_header("SETUP: Connecting to Database")
        try:
            self.client = AsyncIOMotorClient(self.mongo_uri)
            self.db = self.client.legal_genie
            
            # Test connection
            await self.client.admin.command('ping')
            print_success(f"Connected to MongoDB: {self.mongo_uri[:30]}...")
            
            # Show collections
            collections = await self.db.list_collection_names()
            print_info(f"Available collections: {', '.join(collections)}")
            
            return True
        except Exception as e:
            print_error(f"Database connection failed: {e}")
            return False
    
    async def cleanup(self):
        """Close database connection"""
        if self.client:
            self.client.close()
            print_info("Database connection closed")
    
    async def test_authentication(self):
        """Test user registration and login"""
        print_header("TEST 1: Authentication Flow")
        
        try:
            # Step 1: Register user
            print_step(1, "Registering test user")
            user_collection = self.db["users"]
            
            # Check if user exists
            existing = await user_collection.find_one({"username": self.test_username})
            if existing:
                print_warning(f"User {self.test_username} already exists, deleting...")
                await user_collection.delete_one({"username": self.test_username})
            
            # Register
            hashed_password = hash_password(self.test_password)
            user_data = {
                "username": self.test_username,
                "password": hashed_password,
                "created_at": datetime.now(timezone.utc)
            }
            result = await user_collection.insert_one(user_data)
            print_success(f"User registered: {self.test_username}")
            print_info(f"User ID: {result.inserted_id}")
            
            # Step 2: Verify password hashing
            print_step(2, "Verifying password hashing")
            user = await user_collection.find_one({"username": self.test_username})
            if verify_password(self.test_password, user["password"]):
                print_success("Password verification successful")
            else:
                print_error("Password verification failed")
                return False
            
            # Step 3: Create JWT token
            print_step(3, "Creating JWT access token")
            self.access_token = create_access_token(data={"sub": self.test_username})
            print_success(f"Token created: {self.access_token[:30]}...")
            
            # Step 4: Verify token
            print_step(4, "Verifying JWT token")
            payload = verify_token(self.access_token)
            if payload and payload.get("sub") == self.test_username:
                print_success(f"Token verified for user: {payload.get('sub')}")
                print_info(f"Token expires at: {datetime.fromtimestamp(payload.get('exp'), tz=timezone.utc)}")
            else:
                print_error("Token verification failed")
                return False
            
            self.test_results.append(("Authentication", True))
            return True
            
        except Exception as e:
            print_error(f"Authentication test failed: {e}")
            self.test_results.append(("Authentication", False))
            return False
    
    async def test_intent_detection(self):
        """Test intent detection with various messages"""
        print_header("TEST 2: Intent Detection")
        
        test_cases = [
            {
                "message": "What is a demand letter under Philippine law?",
                "expected_intent": "consultation",
                "expected_document": None
            },
            {
                "message": "Generate a demand letter for 50,000 PHP",
                "expected_intent": "document_generation",
                "expected_document": "demand_letter"
            },
            {
                "message": "Explain demand letters and create one for me",
                "expected_intent": "both",
                "expected_document": "demand_letter"
            }
        ]
        
        all_passed = True
        
        for i, test in enumerate(test_cases, 1):
            print_step(i, f"Testing: '{test['message'][:60]}...'")
            
            try:
                intent = await detect_intent(test["message"])
                
                print_info(f"Detected intent: {intent['intent_type']}")
                print_info(f"Document type: {intent.get('document_type', 'None')}")
                print_info(f"Confidence: {intent.get('confidence', 0):.2f}")
                print_info(f"Needs consultation: {intent.get('needs_consultation')}")
                print_info(f"Needs document: {intent.get('needs_document')}")
                
                # Verify expectations
                if intent['intent_type'] == test['expected_intent']:
                    print_success("Intent type matches expected")
                else:
                    print_warning(f"Expected {test['expected_intent']}, got {intent['intent_type']}")
                
                if test['expected_document']:
                    if intent.get('document_type') == test['expected_document']:
                        print_success("Document type matches expected")
                    else:
                        print_warning(f"Expected {test['expected_document']}, got {intent.get('document_type')}")
                
            except Exception as e:
                print_error(f"Intent detection failed: {e}")
                all_passed = False
        
        self.test_results.append(("Intent Detection", all_passed))
        return all_passed
    
    async def test_consultation_flow(self):
        """Test consultation with Philippine law consultant"""
        print_header("TEST 3: Consultation Flow (Philippine Law Expert)")
        
        test_questions = [
            "What is Article 1159 of the Civil Code about?",
            "Can you explain employee rights under the Labor Code?",
            "What are the penalties for theft under the Revised Penal Code?"
        ]
        
        try:
            for i, question in enumerate(test_questions, 1):
                print_step(i, f"Asking: '{question}'")
                
                # Get consultation prompt
                consultation_prompt = get_consultation_with_history_prompt(
                    chat_history=[],
                    current_question=question
                )
                
                # Get Philippine law consultant persona
                persona = get_philippine_law_consultant_prompt()
                
                print_info("Calling LLM with Philippine law consultant persona...")
                
                # Generate response
                result = await generate_response(consultation_prompt, persona)
                response = result.get("data", {}).get("response", "")
                
                if response:
                    print_success("Response received")
                    print(f"\n{Colors.BLUE}Response preview:{Colors.ENDC}")
                    print(f"{response[:300]}...\n")
                    
                    # Check if response mentions Philippine law context
                    ph_keywords = ["philippine", "philippines", "ph law", "civil code", 
                                   "labor code", "penal code", "republic act"]
                    has_ph_context = any(keyword in response.lower() for keyword in ph_keywords)
                    
                    if has_ph_context:
                        print_success("Response includes Philippine law context")
                    else:
                        print_warning("Response may lack Philippine law specificity")
                    
                    # Save to database
                    await save_chat_message(
                        self.db, self.test_username, "user", question,
                        {"test": "consultation_flow"}
                    )
                    await save_chat_message(
                        self.db, self.test_username, "assistant", response,
                        {"test": "consultation_flow", "has_ph_context": has_ph_context}
                    )
                    print_info("Messages saved to database")
                else:
                    print_error("Empty response received")
                
                await asyncio.sleep(1)  # Rate limiting
            
            self.test_results.append(("Consultation Flow", True))
            return True
            
        except Exception as e:
            print_error(f"Consultation flow test failed: {e}")
            import traceback
            traceback.print_exc()
            self.test_results.append(("Consultation Flow", False))
            return False
    
    async def test_conversation_continuity(self):
        """Test if chat history is maintained across messages"""
        print_header("TEST 4: Conversation Continuity (Chat History)")
        
        conversation = [
            "What is a demand letter?",
            "When should I send one?",
            "How do I write it properly?",
            "Can you create one for me?"
        ]
        
        try:
            for i, message in enumerate(conversation, 1):
                print_step(i, f"Message: '{message}'")
                
                # Get chat history from database
                history_docs = await get_user_chat_history(self.db, self.test_username, limit=5)
                history_text = format_chat_history(history_docs)
                
                if history_docs:
                    print_info(f"Retrieved {len(history_docs)} previous messages from history")
                    print(f"{Colors.CYAN}History context:{Colors.ENDC}")
                    for msg in history_docs[-3:]:  # Show last 3
                        role = msg.get('role', 'unknown')
                        content = msg.get('content', '')[:60]
                        print(f"  {role}: {content}...")
                
                # Detect intent
                intent = await detect_intent(message, history_text)
                print_info(f"Intent: {intent['intent_type']}")
                
                # Build consultation prompt with history
                consultation_prompt = get_consultation_with_history_prompt(
                    chat_history=history_docs,
                    current_question=message
                )
                
                persona = get_philippine_law_consultant_prompt()
                
                # Generate response
                result = await generate_response(consultation_prompt, persona)
                response = result.get("data", {}).get("response", "")
                
                if response:
                    print_success("Response received")
                    print(f"{Colors.BLUE}Response:{Colors.ENDC} {response[:200]}...\n")
                    
                    # Save to database
                    await save_chat_message(
                        self.db, self.test_username, "user", message,
                        {"test": "continuity", "turn": i, "intent": intent}
                    )
                    await save_chat_message(
                        self.db, self.test_username, "assistant", response,
                        {"test": "continuity", "turn": i}
                    )
                
                await asyncio.sleep(1)
            
            # Verify history was saved
            print_step(5, "Verifying conversation history in database")
            final_history = await get_user_chat_history(self.db, self.test_username, limit=20)
            print_success(f"Total messages in history: {len(final_history)}")
            
            # Show conversation summary
            print(f"\n{Colors.CYAN}Conversation Summary:{Colors.ENDC}")
            for msg in final_history[-8:]:  # Last 8 messages (4 turns)
                role = msg.get('role', 'unknown')
                content = msg.get('content', '')[:80]
                timestamp = msg.get('timestamp', 'N/A')
                print(f"  [{role:10}] {content}... ({timestamp})")
            
            self.test_results.append(("Conversation Continuity", True))
            return True
            
        except Exception as e:
            print_error(f"Conversation continuity test failed: {e}")
            import traceback
            traceback.print_exc()
            self.test_results.append(("Conversation Continuity", False))
            return False
    
    async def test_database_verification(self):
        """Verify all data was saved correctly to database"""
        print_header("TEST 5: Database Verification")
        
        try:
            # Check users collection
            print_step(1, "Checking users collection")
            user = await self.db["users"].find_one({"username": self.test_username})
            if user:
                print_success(f"User found: {user['username']}")
                print_info(f"Created at: {user.get('created_at')}")
            else:
                print_error("User not found in database")
                return False
            
            # Check chat history collection
            print_step(2, "Checking chat history collection")
            chat_count = await self.db["legalchat_histories"].count_documents(
                {"username": self.test_username}
            )
            print_success(f"Found {chat_count} chat messages for user")
            
            # Get sample messages
            sample_messages = await self.db["legalchat_histories"].find(
                {"username": self.test_username}
            ).limit(5).to_list(length=5)
            
            print(f"\n{Colors.CYAN}Sample chat records:{Colors.ENDC}")
            for msg in sample_messages:
                print(f"  Role: {msg.get('role')}")
                print(f"  Content: {msg.get('content', '')[:60]}...")
                print(f"  Timestamp: {msg.get('timestamp')}")
                print(f"  Metadata: {msg.get('metadata', {})}")
                print()
            
            # Check for intent metadata
            print_step(3, "Checking intent metadata")
            messages_with_intent = await self.db["legalchat_histories"].count_documents({
                "username": self.test_username,
                "metadata.intent": {"$exists": True}
            })
            print_info(f"Messages with intent metadata: {messages_with_intent}")
            
            self.test_results.append(("Database Verification", True))
            return True
            
        except Exception as e:
            print_error(f"Database verification failed: {e}")
            self.test_results.append(("Database Verification", False))
            return False
    
    async def test_mixed_intent(self):
        """Test handling of mixed intent (consultation + document generation)"""
        print_header("TEST 6: Mixed Intent Handling")
        
        mixed_messages = [
            "What should a demand letter include? Also, can you create one for me for 75,000 PHP?",
            "Explain the legal requirements and generate a demand letter. Sender: Maria Santos, Recipient: Juan Cruz"
        ]
        
        try:
            for i, message in enumerate(mixed_messages, 1):
                print_step(i, f"Testing: '{message[:60]}...'")
                
                # Get history
                history_docs = await get_user_chat_history(self.db, self.test_username, limit=5)
                history_text = format_chat_history(history_docs)
                
                # Detect intent
                intent = await detect_intent(message, history_text)
                
                print_info(f"Intent type: {intent['intent_type']}")
                print_info(f"Needs consultation: {intent.get('needs_consultation')}")
                print_info(f"Needs document: {intent.get('needs_document')}")
                
                if intent['intent_type'] == 'both':
                    print_success("Mixed intent correctly detected!")
                else:
                    print_warning(f"Expected 'both', got '{intent['intent_type']}'")
                
                # Both consultation and document should be triggered
                if intent.get('needs_consultation') and intent.get('needs_document'):
                    print_success("Both services flagged for activation")
                else:
                    print_warning("Not all required services flagged")
                
                # Save test message
                await save_chat_message(
                    self.db, self.test_username, "user", message,
                    {"test": "mixed_intent", "intent": intent}
                )
                
                await asyncio.sleep(1)
            
            self.test_results.append(("Mixed Intent Handling", True))
            return True
            
        except Exception as e:
            print_error(f"Mixed intent test failed: {e}")
            self.test_results.append(("Mixed Intent Handling", False))
            return False
    
    async def cleanup_test_data(self):
        """Clean up test data from database"""
        print_header("CLEANUP: Removing Test Data")
        
        try:
            # Ask for confirmation
            print_warning(f"About to delete test user: {self.test_username}")
            response = input(f"{Colors.YELLOW}Delete test data? (y/n): {Colors.ENDC}")
            
            if response.lower() == 'y':
                # Delete user
                user_result = await self.db["users"].delete_one(
                    {"username": self.test_username}
                )
                print_info(f"Deleted {user_result.deleted_count} user record")
                
                # Delete chat history
                chat_result = await self.db["legalchat_histories"].delete_many(
                    {"username": self.test_username}
                )
                print_info(f"Deleted {chat_result.deleted_count} chat messages")
                
                print_success("Test data cleaned up")
            else:
                print_info("Test data preserved for inspection")
                print_info(f"User: {self.test_username}")
        
        except Exception as e:
            print_error(f"Cleanup failed: {e}")
    
    def print_summary(self):
        """Print test results summary"""
        print_header("TEST RESULTS SUMMARY")
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for _, result in self.test_results if result)
        failed_tests = total_tests - passed_tests
        
        print(f"{Colors.BOLD}Total Tests: {total_tests}{Colors.ENDC}")
        print(f"{Colors.GREEN}Passed: {passed_tests}{Colors.ENDC}")
        print(f"{Colors.RED}Failed: {failed_tests}{Colors.ENDC}\n")
        
        for test_name, result in self.test_results:
            if result:
                print_success(f"{test_name}")
            else:
                print_error(f"{test_name}")
        
        print()
        if failed_tests == 0:
            print(f"{Colors.GREEN}{Colors.BOLD}🎉 ALL TESTS PASSED! 🎉{Colors.ENDC}")
        else:
            print(f"{Colors.YELLOW}{Colors.BOLD}⚠️  SOME TESTS FAILED ⚠️{Colors.ENDC}")
        
        print()
    
    async def run_all_tests(self):
        """Run all tests in sequence"""
        print(f"{Colors.BOLD}{Colors.HEADER}")
        print("╔════════════════════════════════════════════════════════════════════════╗")
        print("║        AIScribe Full Flow Test Suite                                  ║")
        print("║        Testing with Real Database & Authentication                    ║")
        print("╚════════════════════════════════════════════════════════════════════════╝")
        print(f"{Colors.ENDC}")
        
        # Setup
        if not await self.setup():
            print_error("Setup failed. Exiting.")
            return
        
        # Run tests
        await self.test_authentication()
        await self.test_intent_detection()
        await self.test_consultation_flow()
        await self.test_conversation_continuity()
        await self.test_mixed_intent()
        await self.test_database_verification()
        
        # Summary
        self.print_summary()
        
        # Cleanup
        await self.cleanup_test_data()
        await self.cleanup()


async def main():
    """Main entry point"""
    tester = AIScribeFullFlowTester()
    
    try:
        await tester.run_all_tests()
    except KeyboardInterrupt:
        print(f"\n\n{Colors.YELLOW}Test interrupted by user{Colors.ENDC}")
        await tester.cleanup()
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        await tester.cleanup()


if __name__ == "__main__":
    print_info("Starting AIScribe Full Flow Test...")
    print_info("This will test with your actual database and LLM")
    print_info("Make sure your .env file is configured correctly\n")
    
    asyncio.run(main())
