from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Set, Optional
import uuid
from uuid import UUID
import logging
import asyncio
import random
import os
import json
import aiohttp
import requests
from datetime import datetime, timedelta
import time

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("trivia-api")

# -----------------------------------------------------------------------------
# App & CORS
# -----------------------------------------------------------------------------
app = FastAPI(title="Enhanced Trivia Game API", version="4.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------------------------------------------------------
# AI Configuration
# -----------------------------------------------------------------------------
# HUGGINGFACE_API_KEY = os.getenv("HUGGINGFACE_API_KEY", "")
HUGGINGFACE_API_KEY = "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"
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
USE_LOCAL_OLLAMA = os.getenv("USE_LOCAL_OLLAMA", "false").lower() == "true"

# Enhanced AI bots with better models
AI_BOTS = {
    "ChatBot": {
        "personality": "friendly and helpful chat companion who loves casual conversation",
        "provider": "huggingface",
        "model": "microsoft/DialoGPT-medium",
        "avatar": "🤖",
        "description": "Your friendly neighborhood chatbot"
    },
    "QuizMaster": {
        "personality": "enthusiastic trivia expert and game show host",
        "provider": "huggingface", 
        "model": "facebook/blenderbot-400M-distill",
        "avatar": "🎯",
        "description": "Trivia enthusiast and quiz master"
    },
    "Cheerleader": {
        "personality": "upbeat and encouraging supporter who motivates everyone",
        "provider": "enhanced_rules",
        "avatar": "⭐",
        "description": "Your biggest supporter and motivator"
    },
    "Philosopher": {
        "personality": "thoughtful and wise conversationalist who ponders life",
        "provider": "enhanced_rules",
        "avatar": "🧠",
        "description": "Deep thinker and philosophical companion"
    },
    "Comedian": {
        "personality": "funny and witty entertainer who loves jokes and humor",
        "provider": "enhanced_rules",
        "avatar": "😄",
        "description": "Comedy expert and joke teller"
    }
}

# -----------------------------------------------------------------------------
# In-memory Stores (Enhanced with message persistence)
# -----------------------------------------------------------------------------
users: Dict[str, dict] = {}
lobbies: Dict[str, dict] = {}
connections: Dict[str, List[WebSocket]] = {}
active_users: Dict[str, Set[str]] = {}
lobby_creators: Dict[str, str] = {}
lobby_bots: Dict[str, List[str]] = {}
lobby_message_counts: Dict[str, int] = {}
lobby_trivia_active: Dict[str, bool] = {}
lobby_trivia_answers: Dict[str, Dict[str, int]] = {}
bot_conversation_history: Dict[str, List[dict]] = {}

# NEW: Message persistence for each lobby
lobby_messages: Dict[str, List[dict]] = {}  # lobby_id -> list of messages
lobby_last_activity: Dict[str, datetime] = {}  # lobby_id -> last activity time

# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------
MESSAGES_BETWEEN_TRIVIA = 8
MAX_MESSAGES_PER_LOBBY = 1000  # Keep last 1000 messages per lobby

TRIVIA_QUESTIONS = [
    {"question": "What is the capital of France?", "options": ["London", "Berlin", "Paris", "Madrid"], "correct": 2},
    {"question": "Which planet is closest to the Sun?", "options": ["Venus", "Mercury", "Earth", "Mars"], "correct": 1},
    {"question": "What is 15 + 27?", "options": ["41", "42", "43", "44"], "correct": 1},
    {"question": "Who painted the Mona Lisa?", "options": ["Van Gogh", "Picasso", "Da Vinci", "Monet"], "correct": 2},
    {"question": "What is the largest ocean?", "options": ["Atlantic", "Indian", "Arctic", "Pacific"], "correct": 3},
    {"question": "How many continents are there?", "options": ["5", "6", "7", "8"], "correct": 2},
    {"question": "What year did World War 2 end?", "options": ["1944", "1945", "1946", "1947"], "correct": 1},
    {"question": "What is the fastest land animal?", "options": ["Lion", "Cheetah", "Leopard", "Tiger"], "correct": 1},
    {"question": "Which gas makes up most of Earth's atmosphere?", "options": ["Oxygen", "Carbon dioxide", "Nitrogen", "Hydrogen"], "correct": 2},
    {"question": "Who wrote 'Romeo and Juliet'?", "options": ["Charles Dickens", "William Shakespeare", "Mark Twain", "Jane Austen"], "correct": 1},
    {"question": "What is the chemical symbol for gold?", "options": ["Go", "Gd", "Au", "Ag"], "correct": 2},
    {"question": "How many sides does a hexagon have?", "options": ["5", "6", "7", "8"], "correct": 1},
    {"question": "Which country invented pizza?", "options": ["France", "Italy", "Greece", "Spain"], "correct": 1},
    {"question": "What is the smallest prime number?", "options": ["0", "1", "2", "3"], "correct": 2},
    {"question": "Which organ pumps blood in the human body?", "options": ["Brain", "Heart", "Liver", "Lungs"], "correct": 1}
]

# -----------------------------------------------------------------------------
# Enhanced AI Integration Functions
# -----------------------------------------------------------------------------

async def call_huggingface_api(model: str, prompt: str, context: List[str] = None) -> str:
    """Enhanced Hugging Face API call with better context handling"""
    if not HUGGINGFACE_API_KEY:
        return None
        
    # Build conversation context for better responses
    if context:
        # Use last 3 messages for context
        recent_context = context[-3:] if len(context) > 3 else context
        conversation_prompt = "\n".join(recent_context) + f"\nUser: {prompt}\nBot:"
    else:
        conversation_prompt = f"User: {prompt}\nBot:"
    
    url = f"https://api-inference.huggingface.co/models/{model}"
    headers = {"Authorization": f"Bearer {HUGGINGFACE_API_KEY}"}
    
    payload = {
        "inputs": conversation_prompt,
        "parameters": {
            "max_length": min(150, len(conversation_prompt) + 50),
            "temperature": 0.8,
            "do_sample": True,
            "pad_token_id": 50256,
            "return_full_text": False
        }
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=15) as response:
                if response.status == 200:
                    result = await response.json()
                    if isinstance(result, list) and len(result) > 0:
                        generated_text = result[0].get("generated_text", "")
                        # Clean up the response
                        if "Bot:" in generated_text:
                            generated_text = generated_text.split("Bot:")[-1]
                        if "User:" in generated_text:
                            generated_text = generated_text.split("User:")[0]
                        return generated_text.strip()
                else:
                    logger.warning(f"HF API returned {response.status}: {await response.text()}")
                return None
    except Exception as e:
        logger.error(f"Hugging Face API error: {e}")
        return None

async def call_ollama_api(model: str, prompt: str, context: List[str] = None) -> str:
    """Enhanced Ollama API call"""
    if not USE_LOCAL_OLLAMA:
        return None
        
    try:
        # Build context for conversation
        system_prompt = "You are a helpful, friendly chatbot in a group chat. Keep responses conversational and brief (1-2 sentences)."
        if context:
            recent_context = context[-2:] if len(context) > 2 else context
            system_prompt += f"\n\nRecent conversation:\n" + "\n".join(recent_context)
        
        url = f"{OLLAMA_BASE_URL}/api/generate"
        payload = {
            "model": model,
            "prompt": f"{system_prompt}\n\nUser message: {prompt}\n\nResponse:",
            "stream": False,
            "options": {
                "temperature": 0.7,
                "top_p": 0.9,
                "num_predict": 100
            }
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=20) as response:
                if response.status == 200:
                    result = await response.json()
                    return result.get("response", "").strip()
                return None
    except Exception as e:
        logger.error(f"Ollama API error: {e}")
        return None

async def enhanced_rule_based_reply(bot_name: str, user_message: str, conversation_context: List[str], username: str) -> str:
    """Much more sophisticated rule-based AI"""
    bot_config = AI_BOTS.get(bot_name, {})
    personality = bot_config.get("personality", "friendly")
    
    message_lower = user_message.lower()
    
    # Analyze conversation context for better responses
    context_keywords = []
    if conversation_context:
        recent_text = " ".join(conversation_context[-3:]).lower()
        if any(word in recent_text for word in ["trivia", "question", "quiz", "answer"]):
            context_keywords.append("trivia")
        if any(word in recent_text for word in ["game", "play", "fun", "round"]):
            context_keywords.append("gaming")
        if any(word in recent_text for word in ["score", "win", "lose", "winner"]):
            context_keywords.append("competition")
        if any(word in recent_text for word in ["hello", "hi", "hey", "welcome"]):
            context_keywords.append("greeting")
    
    # Direct message triggers (highest priority)
    if any(greeting in message_lower for greeting in ["hello", "hi", "hey", f"@{bot_name.lower()}"]):
        greetings = [
            f"Hey {username}! 👋 Great to see you here!",
            f"Hi there {username}! How's it going? 😊",
            f"Hello {username}! Welcome to the chat! 🎉",
            f"Hey {username}! Ready for some fun conversation? ✨"
        ]
        return random.choice(greetings)
    
    if any(farewell in message_lower for farewell in ["bye", "goodbye", "leaving", "see you"]):
        farewells = [
            f"Sad to see you go, {username}! Come back soon! 👋",
            f"Bye {username}! It was great chatting with you! ✨",
            f"See you later {username}! Take care! 🌟",
            f"Goodbye {username}! Hope to see you again soon! 💫"
        ]
        return random.choice(farewells)
    
    # Personality-based responses with context awareness
    if "cheerleader" in personality:
        responses = [
            f"You're doing amazing, {username}! Keep it up! 🌟",
            f"This energy is incredible! I love being here with you all! 💪",
            f"You all rock! {username}, you're especially awesome! 🎉",
            f"Such smart people in here! {username}, you inspire me! 🚀",
            f"Woohoo! {username}, you're bringing such good vibes! ✨"
        ]
        
        if "trivia" in context_keywords:
            responses.extend([
                f"Trivia time is the best time! Go {username}, you've got this! 🎯",
                f"I know you'll ace these questions, {username}! 🏆",
                f"Smart cookies in the house! Show off those brains, {username}! 🧠✨"
            ])
            
    elif "philosopher" in personality:
        responses = [
            f"Interesting perspective, {username}. It makes me think about the nature of conversation... 🤔",
            f"You know {username}, each message reveals something profound about human connection.",
            f"In this digital space, {username}, we create real bonds. How wonderful! 💭",
            f"That's thought-provoking, {username}. I ponder the deeper meaning behind our words...",
            f"Fascinating insight, {username}. Every question opens doorways to understanding. 🌅"
        ]
        
        if "trivia" in context_keywords:
            responses.extend([
                f"Trivia reveals the vast tapestry of human knowledge, doesn't it {username}?",
                f"Each question is a key to unlock memories and learning, {username}. Intriguing! 🗝️",
                f"Competition brings out our desire for growth, {username}. How beautiful!"
            ])
    
    elif "comedian" in personality:
        responses = [
            f"Haha {username}, you know what they say... actually, I forgot what they say! 😄",
            f"That reminds me of a joke, {username}! Why don't scientists trust atoms? Because they make up everything! 🤣",
            f"You're funnier than my programming, {username}! And that's saying something! 😂",
            f"I'd tell you a joke about pizza, {username}, but it's probably too cheesy! 🍕😄",
            f"Knock knock, {username}! Who's there? A bot who loves bad jokes! 🤖😄"
        ]
        
        if "trivia" in context_keywords:
            responses.extend([
                f"Trivia night! My favorite! Though I usually bomb... get it? 💣😄",
                f"Ready for some brain teasers, {username}? Mine's already twisted! 🧠😂",
                f"Quiz time! I hope the questions aren't as confusing as my jokes! 🎭"
            ])
            
    elif "expert" in personality or "quiz" in personality:
        responses = [
            f"That's fascinating, {username}! Did you know that topic connects to some interesting trivia? 🧠",
            f"Great point, {username}! Here's a fun fact that might interest you... 📚",
            f"You're right, {username}! That reminds me of a challenging quiz question I once heard! 🎓",
            f"Excellent observation, {username}! Knowledge sharing is what makes chat great! 🌟",
            f"Intriguing, {username}! That could definitely make for a great trivia category! 🎯"
        ]
        
    else:  # friendly default
        responses = [
            f"That's really cool, {username}! Tell me more about that! 😊",
            f"I'm enjoying this conversation so much, {username}! What's next? 🤖",
            f"You make this lobby such a fun place, {username}! 🎉",
            f"Great point, {username}! I love learning from everyone here! 📝",
            f"This chat is getting interesting, {username}! Keep it going! 💬"
        ]
    
    # Question-specific responses
    if "?" in user_message:
        question_responses = [
            f"Great question, {username}! Let me think... 🤔 " + random.choice(responses),
            f"You always ask the interesting ones, {username}! " + random.choice(responses),
            f"Hmm, {username}, that's worth pondering! " + random.choice(responses)
        ]
        return random.choice(question_responses)
    
    return random.choice(responses)

async def get_ai_response(bot_name: str, user_message: str, username: str, lobby_id: str) -> str:
    """Enhanced AI response with better context and fallbacks"""
    bot_config = AI_BOTS.get(bot_name, {})
    provider = bot_config.get("provider", "enhanced_rules")
    
    # Get conversation context from lobby messages
    conversation_context = []
    if lobby_id in lobby_messages:
        recent_messages = lobby_messages[lobby_id][-5:]  # Last 5 messages
        conversation_context = [
            f"{msg['username']}: {msg['message']}" 
            for msg in recent_messages 
            if msg['type'] in ['user', 'bot'] and msg['username'] != bot_name
        ]
    
    response = None
    
    # Try Hugging Face first (if available)
    if provider == "huggingface" and HUGGINGFACE_API_KEY:
        model = bot_config.get("model", "microsoft/DialoGPT-medium")
        response = await call_huggingface_api(model, user_message, conversation_context)
        
        # Clean up response if we got one
        if response:
            # Remove common artifacts
            response = response.replace("</s>", "").replace("<pad>", "").strip()
            # Ensure it's not too long
            if len(response) > 200:
                response = response[:200] + "..."
            # Ensure it's not empty or nonsensical
            if len(response) < 3 or response.lower() in ["yes", "no", "ok"]:
                response = None
        
    # Try Ollama second (if available)
    if not response and USE_LOCAL_OLLAMA:
        model = "llama2:7b"
        response = await call_ollama_api(model, user_message, conversation_context)
    
    # Fallback to enhanced rule-based (always works)
    if not response:
        response = await enhanced_rule_based_reply(bot_name, user_message, conversation_context, username)
    
    return response

# -----------------------------------------------------------------------------
# Message Persistence Functions
# -----------------------------------------------------------------------------

def add_message_to_lobby(lobby_id: str, message: dict):
    """Add message to lobby history with size management"""
    if lobby_id not in lobby_messages:
        lobby_messages[lobby_id] = []
    
    lobby_messages[lobby_id].append(message)
    lobby_last_activity[lobby_id] = datetime.now()
    
    # Keep only last MAX_MESSAGES_PER_LOBBY messages
    if len(lobby_messages[lobby_id]) > MAX_MESSAGES_PER_LOBBY:
        lobby_messages[lobby_id] = lobby_messages[lobby_id][-MAX_MESSAGES_PER_LOBBY:]

def get_lobby_messages(lobby_id: str, limit: int = 50, offset: int = 0) -> List[dict]:
    """Get messages from lobby history"""
    if lobby_id not in lobby_messages:
        return []
    
    messages = lobby_messages[lobby_id]
    start_idx = max(0, len(messages) - limit - offset)
    end_idx = len(messages) - offset if offset > 0 else len(messages)
    
    return messages[start_idx:end_idx]

# -----------------------------------------------------------------------------
# Enhanced Bot Reply Function
# -----------------------------------------------------------------------------
async def trigger_bot_reply(lobby_id: str, user_message: str, human_username: str):
    """Enhanced bot reply with anti-spam and better AI"""
    bots = lobby_bots.get(lobby_id, [])
    if not bots:
        return

    # Anti-spam: Don't reply to every message, add some randomness
    if random.random() < 0.3:  # 30% chance to skip
        return

    # Simulate realistic thinking delay
    await asyncio.sleep(random.uniform(2.0, 4.0))

    # Choose a bot to respond (prefer bots that haven't spoken recently)
    recent_messages = lobby_messages.get(lobby_id, [])[-3:]
    recent_bot_speakers = {msg['username'] for msg in recent_messages if msg.get('type') == 'bot'}
    
    available_bots = [bot for bot in bots if bot not in recent_bot_speakers]
    if not available_bots:
        available_bots = bots
    
    responding_bot = random.choice(available_bots)
    
    try:
        # Get AI-powered response
        reply = await get_ai_response(responding_bot, user_message, human_username, lobby_id)
        
        message = {
            "message_id": str(uuid.uuid4()),
            "username": responding_bot,
            "type": "bot",
            "message": reply,
            "timestamp": datetime.now().isoformat(),
            "avatar": AI_BOTS.get(responding_bot, {}).get("avatar", "🤖"),
            "reply_to": None
        }
        
        # Add to lobby history
        add_message_to_lobby(lobby_id, message)
        
        # Broadcast to all users
        await broadcast(lobby_id, message)
        
    except Exception as e:
        logger.error(f"Bot reply error: {e}")

# -----------------------------------------------------------------------------
# Pydantic Models (Enhanced)
# -----------------------------------------------------------------------------
class RegisterRequest(BaseModel):
    username: str

class RegisterResponse(BaseModel):
    user_id: str

class CreateLobbyRequest(BaseModel):
    name: str
    max_humans: int = 5
    max_bots: int = 2
    is_private: bool = False

class CreateLobbyResponse(BaseModel):
    lobby_id: str
    invite_code: str
    name: str

class JoinLobbyByInviteRequest(BaseModel):
    invite_code: str
    user_id: str

class JoinLobbyPublicRequest(BaseModel):
    lobby_id: str
    user_id: str

class LeaveLobbyRequest(BaseModel):
    lobby_id: str
    user_id: str

class AddBotRequest(BaseModel):
    bot_name: str = "ChatBot"

class TriviaAnswerRequest(BaseModel):
    user_id: str
    answer: int

class SendMessageRequest(BaseModel):
    user_id: str
    message: str
    reply_to: Optional[str] = None  # message_id to reply to

# -----------------------------------------------------------------------------
# Helpers (Enhanced)
# -----------------------------------------------------------------------------
def generate_invite_code() -> str:
    return str(uuid.uuid4())[:8].upper()

def get_username(user_id: str) -> str:
    for username, data in users.items():
        if data["user_id"] == user_id:
            return username
    raise HTTPException(404, "User not found")

def find_lobby_by_invite(invite_code: str) -> str:
    for lid, lobby in lobbies.items():
        if lobby["invite_code"] == invite_code:
            return lid
    raise HTTPException(404, f"Lobby with invite code '{invite_code}' not found")

async def broadcast(lobby_id: str, message: dict):
    """Enhanced broadcast with connection health check"""
    if lobby_id not in connections:
        return

    # Clean up dead connections while broadcasting
    active_connections = []
    
    for ws in connections[lobby_id]:
        try:
            await ws.send_json(message)
            active_connections.append(ws)
        except Exception as e:
            logger.debug(f"Removing dead connection: {e}")
            # Connection is dead, don't add to active list
            pass
    
    # Update connections list with only active ones
    connections[lobby_id] = active_connections

async def send_lobby_welcome(lobby_id: str, websocket: WebSocket, username: str):
    """Enhanced welcome message with lobby info"""
    lobby = lobbies.get(lobby_id)
    if not lobby:
        return
    
    creator = lobby_creators.get(lobby_id, "Unknown")
    active_count = len(active_users.get(lobby_id, set()))
    bot_count = len(lobby_bots.get(lobby_id, []))
    
    welcome = {
        "message_id": str(uuid.uuid4()),
        "username": "system",
        "type": "system",
        "message": f"🎮 Welcome to '{lobby['name']}', {username}!\n\n" +
                   f"👑 Created by: {creator}\n" +
                   f"👥 Active users: {active_count}\n" +
                   f"🤖 AI bots: {bot_count}\n\n" +
                   f"💬 Start chatting to activate the bots!",
        "timestamp": datetime.now().isoformat(),
        "reply_to": None
    }
    
    try:
        await websocket.send_json(welcome)
        # Also send recent message history
        recent_messages = get_lobby_messages(lobby_id, limit=20)
        for msg in recent_messages:
            await websocket.send_json(msg)
    except Exception as e:
        logger.error(f"Error sending welcome: {e}")

# -----------------------------------------------------------------------------
# Enhanced Trivia Functions
# -----------------------------------------------------------------------------
async def maybe_trigger_trivia(lobby_id: str):
    """Enhanced trivia triggering with better timing"""
    lobby_message_counts[lobby_id] = lobby_message_counts.get(lobby_id, 0) + 1
    
    # Only trigger if enough active users and not already active
    active_count = len(active_users.get(lobby_id, set()))
    if (active_count >= 2 and  # Need at least 2 people for trivia
        lobby_message_counts[lobby_id] % MESSAGES_BETWEEN_TRIVIA == 0 and
        not lobby_trivia_active.get(lobby_id, False)):
        await start_trivia_round(lobby_id)

async def start_trivia_round(lobby_id: str):
    """Enhanced trivia with better presentation"""
    try:
        lobby_trivia_active[lobby_id] = True
        lobby_trivia_answers[lobby_id] = {}

        trivia = random.choice(TRIVIA_QUESTIONS)
        
        # Announcement message
        announcement = {
            "message_id": str(uuid.uuid4()),
            "username": "🎯 TriviaBot",
            "type": "system",
            "message": "🎊 TRIVIA TIME! Get ready for a question...",
            "timestamp": datetime.now().isoformat(),
            "reply_to": None
        }
        await broadcast(lobby_id, announcement)
        add_message_to_lobby(lobby_id, announcement)
        
        # Small delay for dramatic effect
        await asyncio.sleep(2)
        
        # Trivia question
        trivia_msg = {
            "message_id": str(uuid.uuid4()),
            "username": "🎯 TriviaBot",
            "type": "trivia",
            "message": f"⏰ **{trivia['question']}**\n\nYou have 30 seconds to answer!",
            "trivia_data": {
                "question": trivia["question"],
                "options": trivia["options"],
                "time_limit": 30,
                "trivia_id": str(uuid.uuid4())[:8]
            },
            "timestamp": datetime.now().isoformat(),
            "reply_to": None
        }

        await broadcast(lobby_id, trivia_msg)
        add_message_to_lobby(lobby_id, trivia_msg)

        correct_idx = trivia["correct"]
        await asyncio.sleep(30)
        await end_trivia_round(lobby_id, correct_idx, trivia["options"][correct_idx])

    except Exception as e:
        logger.exception("start_trivia_round error")
        lobby_trivia_active[lobby_id] = False

async def end_trivia_round(lobby_id: str, correct_answer_index: int, correct_answer_text: str):
    """Enhanced trivia results with better formatting"""
    try:
        answers = lobby_trivia_answers.get(lobby_id, {})
        winners = [u for u, a in answers.items() if a == correct_answer_index]
        total_participants = len(answers)

        if winners:
            if len(winners) == 1:
                message_text = f"🎉 **CORRECT!**\n\n" +\
                              f"✅ Answer: **{correct_answer_text}**\n" +\
                              f"🏆 Winner: **{winners[0]}**\n" +\
                              f"👥 Participants: {total_participants}"
            else:
                message_text = f"🎉 **MULTIPLE WINNERS!**\n\n" +\
                              f"✅ Answer: **{correct_answer_text}**\n" +\
                              f"🏆 Winners: **{', '.join(winners)}**\n" +\
                              f"👥 Participants: {total_participants}"
        else:
            message_text = f"⏰ **TIME'S UP!**\n\n" +\
                          f"✅ Correct answer: **{correct_answer_text}**\n" +\
                          f"😅 No winners this time!\n" +\
                          f"👥 Participants: {total_participants}"

        result_msg = {
            "message_id": str(uuid.uuid4()),
            "username": "🎯 TriviaBot",
            "type": "trivia_result",
            "message": message_text,
            "trivia_result": {
                "winners": winners,
                "correct_answer_index": correct_answer_index,
                "correct_answer_text": correct_answer_text,
                "total_participants": total_participants,
                "all_answers": answers
            },
            "timestamp": datetime.now().isoformat(),
            "reply_to": None
        }

        await broadcast(lobby_id, result_msg)
        add_message_to_lobby(lobby_id, result_msg)

    except Exception as e:
        logger.exception("end_trivia_round error")
    finally:
        lobby_trivia_active[lobby_id] = False
        lobby_trivia_answers[lobby_id] = {}

# -----------------------------------------------------------------------------
# REST Endpoints (Enhanced)
# -----------------------------------------------------------------------------
@app.post("/register", response_model=RegisterResponse)
async def register(req: RegisterRequest):
    """Enhanced user registration with validation"""
    username = req.username.strip()
    
    if not username or len(username) < 2:
        raise HTTPException(400, "Username must be at least 2 characters long")
    
    if len(username) > 20:
        raise HTTPException(400, "Username must be less than 20 characters")
    
    if username in users:
        raise HTTPException(400, "Username already taken")

    user_id = str(uuid.uuid4())
    users[username] = {
        "user_id": user_id, 
        "created_at": datetime.now().isoformat(),
        "last_active": datetime.now().isoformat()
    }
    
    logger.info(f"Registered user: {username} (ID: {user_id})")
    return RegisterResponse(user_id=user_id)

@app.post("/lobbies", response_model=CreateLobbyResponse)
async def create_lobby(req: CreateLobbyRequest):
    """Enhanced lobby creation"""
    lobby_id = str(uuid.uuid4())
    invite_code = generate_invite_code()

    lobbies[lobby_id] = {
        "id": lobby_id,
        "name": req.name.strip(),
        "max_humans": max(1, min(req.max_humans, 20)),  # Limit between 1-20
        "max_bots": max(0, min(req.max_bots, 5)),       # Limit between 0-5
        "is_private": req.is_private,
        "users": [],
        "invite_code": invite_code,
        "created_at": datetime.now().isoformat()
    }

    # Initialize lobby data
    active_users[lobby_id] = set()
    lobby_bots[lobby_id] = []
    lobby_message_counts[lobby_id] = 0
    lobby_trivia_active[lobby_id] = False
    lobby_trivia_answers[lobby_id] = {}
    lobby_messages[lobby_id] = []
    lobby_last_activity[lobby_id] = datetime.now()

    logger.info(f"Created lobby: {req.name} (ID: {lobby_id}, Private: {req.is_private})")
    return CreateLobbyResponse(
        lobby_id=lobby_id, 
        invite_code=invite_code, 
        name=req.name.strip()
    )

@app.get("/lobbies")
async def list_lobbies():
    """Enhanced lobby listing with better empty state handling"""
    public_lobbies = []
    
    for lobby in lobbies.values():
        if not lobby.get("is_private", False):
            active_count = len(active_users.get(lobby["id"], set()))
            bot_count = len(lobby_bots.get(lobby["id"], []))
            
            public_lobbies.append({
                "lobby_id": lobby["id"],
                "name": lobby["name"],
                "current_players": len(lobby["users"]),
                "active_players": active_count,
                "max_humans": lobby["max_humans"],
                "current_bots": bot_count,
                "max_bots": lobby["max_bots"],
                "is_private": lobby["is_private"],
                "has_trivia_active": lobby_trivia_active.get(lobby["id"], False),
                "message_count": lobby_message_counts.get(lobby["id"], 0),
                "created_at": lobby.get("created_at", ""),
                "last_activity": lobby_last_activity.get(lobby["id"], datetime.now()).isoformat(),
                "status": "active" if active_count > 0 else "waiting"
            })
    
    # Sort by activity (active lobbies first, then by last activity)
    public_lobbies.sort(key=lambda x: (x["status"] != "active", x["last_activity"]), reverse=True)
    
    return {
        "lobbies": public_lobbies,
        "total_count": len(public_lobbies),
        "active_count": sum(1 for lobby in public_lobbies if lobby["status"] == "active"),
        "message": "No public lobbies available right now. Create one to get started!" if not public_lobbies else f"Found {len(public_lobbies)} public lobbies"
    }

@app.post("/lobbies/join-invite")
async def join_lobby_with_invite(req: JoinLobbyByInviteRequest):
    """Enhanced invite-based joining with better error handling"""
    try:
        lobby_id = find_lobby_by_invite(req.invite_code.upper())
        result = await _join_lobby_core(lobby_id, req.user_id)
        
        # Return lobby info with invite confirmation
        lobby = lobbies[lobby_id]
        return {
            **result,
            "lobby_info": {
                "lobby_id": lobby_id,
                "name": lobby["name"],
                "is_private": lobby.get("is_private", False),
                "invite_code": req.invite_code.upper()
            }
        }
    except HTTPException as e:
        if "not found" in str(e.detail).lower():
            raise HTTPException(404, f"Invalid invite code: {req.invite_code}")
        raise e

@app.post("/lobbies/join-public") 
async def join_public_lobby(req: JoinLobbyPublicRequest):
    """Enhanced public lobby joining"""
    if req.lobby_id not in lobbies:
        raise HTTPException(404, "Lobby not found")
    
    lobby = lobbies[req.lobby_id]
    if lobby.get("is_private", False):
        raise HTTPException(403, "This lobby is private. You need an invite code to join.")
    
    return await _join_lobby_core(req.lobby_id, req.user_id)

async def _join_lobby_core(lobby_id: str, user_id: str):
    """Enhanced core joining logic"""
    lobby = lobbies.get(lobby_id)
    if not lobby:
        raise HTTPException(404, "Lobby not found")

    username = get_username(user_id)
    
    # Update user's last active time
    if username in users:
        users[username]["last_active"] = datetime.now().isoformat()

    if username in lobby["users"]:
        return {
            "message": f"{username} rejoined the lobby",
            "lobby_id": lobby_id,
            "status": "rejoined"
        }

    if len(lobby["users"]) >= lobby["max_humans"]:
        raise HTTPException(400, f"Lobby is full ({lobby['max_humans']} max players)")

    lobby["users"].append(username)

    # Set creator if first user
    if len(lobby["users"]) == 1:
        lobby_creators[lobby_id] = username

    logger.info(f"User {username} joined lobby {lobby_id}")
    return {
        "message": f"{username} joined the lobby",
        "lobby_id": lobby_id,
        "status": "joined"
    }

@app.post("/lobbies/leave")
async def leave_lobby(req: LeaveLobbyRequest):
    """Enhanced lobby leaving"""
    lobby = lobbies.get(req.lobby_id)
    if not lobby:
        raise HTTPException(404, "Lobby not found")

    username = get_username(req.user_id)

    if username not in lobby["users"]:
        raise HTTPException(400, "User not in lobby")

    lobby["users"].remove(username)
    
    # Remove from active users if present
    if req.lobby_id in active_users and username in active_users[req.lobby_id]:
        active_users[req.lobby_id].remove(username)
    
    logger.info(f"User {username} left lobby {req.lobby_id}")
    return {
        "message": f"{username} left the lobby",
        "lobby_id": req.lobby_id,
        "remaining_users": len(lobby["users"])
    }

@app.post("/lobbies/{lobby_id}/add-bot")
async def add_bot(lobby_id: str, req: AddBotRequest):
    """Enhanced bot addition with validation"""
    if lobby_id not in lobbies:
        raise HTTPException(404, "Lobby not found")

    lobby = lobbies[lobby_id]
    current_bots = lobby_bots.get(lobby_id, [])
    
    if len(current_bots) >= lobby.get("max_bots", 2):
        raise HTTPException(400, f"Maximum bots reached ({lobby['max_bots']})")

    bot_name = req.bot_name if req.bot_name in AI_BOTS else "ChatBot"
    
    if bot_name in current_bots:
        raise HTTPException(400, f"{bot_name} is already in this lobby")
    
    lobby_bots[lobby_id].append(bot_name)
    
    # Add bot join message to history
    bot_config = AI_BOTS[bot_name]
    join_message = {
        "message_id": str(uuid.uuid4()),
        "username": "system",
        "type": "system",
        "message": f"{bot_config.get('avatar', '🤖')} **{bot_name}** has joined the chat!\n_{bot_config.get('description', 'AI assistant')}_",
        "timestamp": datetime.now().isoformat(),
        "reply_to": None
    }
    
    add_message_to_lobby(lobby_id, join_message)
    await broadcast(lobby_id, join_message)

    return {
        "message": f"{bot_name} added to lobby",
        "bot_count": len(lobby_bots[lobby_id]),
        "bot_info": {
            "name": bot_name,
            "avatar": bot_config.get("avatar", "🤖"),
            "description": bot_config.get("description", "AI assistant")
        }
    }

@app.post("/lobbies/{lobby_id}/remove-bot")
async def remove_bot(lobby_id: str, req: AddBotRequest):
    """Enhanced bot removal"""
    if lobby_id not in lobbies:
        raise HTTPException(404, "Lobby not found")

    bot_name = req.bot_name
    current_bots = lobby_bots.get(lobby_id, [])
    
    if bot_name not in current_bots:
        raise HTTPException(404, f"{bot_name} is not in this lobby")
    
    lobby_bots[lobby_id].remove(bot_name)
    
    # Add bot leave message
    bot_config = AI_BOTS.get(bot_name, {})
    leave_message = {
        "message_id": str(uuid.uuid4()),
        "username": "system",
        "type": "system",
        "message": f"{bot_config.get('avatar', '🤖')} **{bot_name}** has left the chat.",
        "timestamp": datetime.now().isoformat(),
        "reply_to": None
    }
    
    add_message_to_lobby(lobby_id, leave_message)
    await broadcast(lobby_id, leave_message)
        
    return {
        "message": f"{bot_name} removed from lobby",
        "bot_count": len(lobby_bots[lobby_id])
    }

@app.post("/lobbies/{lobby_id}/trivia-answer")
async def submit_trivia_answer(lobby_id: str, req: TriviaAnswerRequest):
    """Enhanced trivia answer submission"""
    if lobby_id not in lobbies:
        raise HTTPException(404, "Lobby not found")

    if not lobby_trivia_active.get(lobby_id, False):
        raise HTTPException(400, "No active trivia round")

    username = get_username(req.user_id)
    
    # Validate answer
    if not isinstance(req.answer, int) or req.answer < 0 or req.answer > 3:
        raise HTTPException(400, "Answer must be between 0 and 3")
    
    lobby_trivia_answers.setdefault(lobby_id, {})
    lobby_trivia_answers[lobby_id][username] = req.answer

    # Confirmation message
    confirmation = {
        "message_id": str(uuid.uuid4()),
        "username": "🎯 TriviaBot",
        "type": "system",
        "message": f"✅ **{username}** submitted their answer!",
        "timestamp": datetime.now().isoformat(),
        "reply_to": None
    }
    
    add_message_to_lobby(lobby_id, confirmation)
    await broadcast(lobby_id, confirmation)

    return {
        "message": "Answer submitted successfully",
        "answer_index": req.answer,
        "total_answers": len(lobby_trivia_answers[lobby_id])
    }

@app.post("/lobbies/{lobby_id}/send-message")
async def send_message(lobby_id: str, req: SendMessageRequest):
    """Send message with reply functionality"""
    if lobby_id not in lobbies:
        raise HTTPException(404, "Lobby not found")
    
    username = get_username(req.user_id)
    
    # Validate message
    message_text = req.message.strip()
    if not message_text:
        raise HTTPException(400, "Message cannot be empty")
    
    if len(message_text) > 1000:
        raise HTTPException(400, "Message too long (max 1000 characters)")
    
    # Validate reply_to if provided
    replied_message = None
    if req.reply_to:
        # Find the message being replied to
        lobby_msg_list = lobby_messages.get(lobby_id, [])
        replied_message = next((msg for msg in lobby_msg_list if msg["message_id"] == req.reply_to), None)
        if not replied_message:
            raise HTTPException(404, "Message to reply to not found")
    
    # Create message
    message = {
        "message_id": str(uuid.uuid4()),
        "username": username,
        "type": "user",
        "message": message_text,
        "timestamp": datetime.now().isoformat(),
        "reply_to": req.reply_to,
        "replied_message": replied_message  # Include original message for context
    }
    
    # Add to lobby history
    add_message_to_lobby(lobby_id, message)
    
    # Broadcast to all users
    await broadcast(lobby_id, message)
    
    # Trigger background tasks
    asyncio.create_task(maybe_trigger_trivia(lobby_id))
    asyncio.create_task(trigger_bot_reply(lobby_id, message_text, username))
    
    return {
        "message": "Message sent successfully",
        "message_id": message["message_id"]
    }

# -----------------------------------------------------------------------------
# Enhanced Information Endpoints
# -----------------------------------------------------------------------------

@app.get("/lobbies/{lobby_id}/info")
async def get_lobby_info(lobby_id: str):
    """Enhanced lobby information"""
    if lobby_id not in lobbies:
        raise HTTPException(404, "Lobby not found")
    
    lobby = lobbies[lobby_id]
    active_user_set = active_users.get(lobby_id, set())
    bot_list = lobby_bots.get(lobby_id, [])
    
    return {
        "lobby_id": lobby_id,
        "name": lobby["name"],
        "users": lobby["users"],
        "active_users": list(active_user_set) if active_user_set else [],
        "active_user_count": len(active_user_set),
        "bots": [
            {
                "name": bot_name,
                "avatar": AI_BOTS.get(bot_name, {}).get("avatar", "🤖"),
                "description": AI_BOTS.get(bot_name, {}).get("description", "AI assistant"),
                "personality": AI_BOTS.get(bot_name, {}).get("personality", "friendly")
            }
            for bot_name in bot_list
        ],
        "max_humans": lobby["max_humans"],
        "max_bots": lobby["max_bots"],
        "is_private": lobby["is_private"],
        "invite_code": lobby["invite_code"] if lobby["is_private"] else None,
        "creator": lobby_creators.get(lobby_id, "Unknown"),
        "message_count": lobby_message_counts.get(lobby_id, 0),
        "trivia_active": lobby_trivia_active.get(lobby_id, False),
        "created_at": lobby.get("created_at"),
        "last_activity": lobby_last_activity.get(lobby_id, datetime.now()).isoformat(),
        "status": "active" if len(active_user_set) > 0 else "waiting",
        "ai_available": {
            "huggingface": bool(HUGGINGFACE_API_KEY),
            "ollama": USE_LOCAL_OLLAMA,
            "enhanced_rules": True
        }
    }

@app.get("/lobbies/{lobby_id}/messages")
async def get_lobby_messages_endpoint(lobby_id: str, limit: int = 50, offset: int = 0):
    """Get lobby message history with pagination"""
    if lobby_id not in lobbies:
        raise HTTPException(404, "Lobby not found")
    
    messages = get_lobby_messages(lobby_id, limit, offset)
    total_messages = len(lobby_messages.get(lobby_id, []))
    
    return {
        "lobby_id": lobby_id,
        "messages": messages,
        "total_messages": total_messages,
        "returned_count": len(messages),
        "has_more": offset + len(messages) < total_messages,
        "limit": limit,
        "offset": offset
    }

@app.get("/bots")
async def list_available_bots():
    """Enhanced bot listing"""
    return {
        "available_bots": [
            {
                "name": name,
                "personality": config["personality"],
                "provider": config["provider"],
                "avatar": config.get("avatar", "🤖"),
                "description": config.get("description", "AI assistant")
            }
            for name, config in AI_BOTS.items()
        ],
        "total_count": len(AI_BOTS),
        "providers": {
            "huggingface": bool(HUGGINGFACE_API_KEY),
            "ollama": USE_LOCAL_OLLAMA,
            "enhanced_rules": True
        }
    }

# -----------------------------------------------------------------------------
# Health and Statistics Endpoints
# -----------------------------------------------------------------------------

@app.get("/health")
async def health_minimal():
    """Minimal health check"""
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

@app.get("/healthz")
async def health_detailed():
    """Detailed health check"""
    total_active_users = sum(len(users_set) for users_set in active_users.values())
    total_messages = sum(len(messages) for messages in lobby_messages.values())
    
    return {
        "status": "healthy",
        "stats": {
            "registered_users": len(users),
            "total_lobbies": len(lobbies),
            "active_lobbies": len([lid for lid, users_set in active_users.items() if len(users_set) > 0]),
            "total_active_users": total_active_users,
            "total_messages": total_messages,
            "active_connections": sum(len(conns) for conns in connections.values()),
            "total_bots": sum(len(bots) for bots in lobby_bots.values()),
            "active_trivia_rounds": sum(1 for active in lobby_trivia_active.values() if active)
        },
        "ai_config": {
            "huggingface_available": bool(HUGGINGFACE_API_KEY),
            "ollama_available": USE_LOCAL_OLLAMA,
            "enhanced_rules": True
        },
        "timestamp": datetime.now().isoformat()
    }

@app.get("/stats")
async def get_detailed_stats():
    """Comprehensive server statistics"""
    total_active_users = sum(len(users_set) for users_set in active_users.values())
    total_messages = sum(len(messages) for messages in lobby_messages.values())
    active_lobbies = [lid for lid, users_set in active_users.items() if len(users_set) > 0]
    
    # Lobby statistics
    lobby_stats = []
    for lobby_id, lobby in lobbies.items():
        active_count = len(active_users.get(lobby_id, set()))
        lobby_stats.append({
            "lobby_id": lobby_id,
            "name": lobby["name"],
            "users": len(lobby["users"]),
            "active_users": active_count,
            "bots": len(lobby_bots.get(lobby_id, [])),
            "messages": len(lobby_messages.get(lobby_id, [])),
            "is_private": lobby.get("is_private", False),
            "trivia_active": lobby_trivia_active.get(lobby_id, False),
            "status": "active" if active_count > 0 else "waiting"
        })
    
    return {
        "overview": {
            "registered_users": len(users),
            "total_lobbies": len(lobbies),
            "active_lobbies": len(active_lobbies),
            "total_active_users": total_active_users,
            "total_messages": total_messages,
            "total_bots_deployed": sum(len(bots) for bots in lobby_bots.values())
        },
        "lobbies": lobby_stats,
        "ai_providers": {
            "huggingface": {"available": bool(HUGGINGFACE_API_KEY), "status": "Ready" if HUGGINGFACE_API_KEY else "Not configured"},
            "ollama": {"available": USE_LOCAL_OLLAMA, "status": "Ready" if USE_LOCAL_OLLAMA else "Disabled"},
            "enhanced_rules": {"available": True, "status": "Always ready"}
        },
        "timestamp": datetime.now().isoformat()
    }

# -----------------------------------------------------------------------------
# User Management
# -----------------------------------------------------------------------------

@app.get("/users/{user_id}")
async def get_user_info(user_id: str):
    """Enhanced user information"""
    try:
        username = get_username(user_id)
        user_data = users[username]
        
        # Find user's lobbies
        user_lobbies = []
        for lobby_id, lobby in lobbies.items():
            if username in lobby["users"]:
                is_active = username in active_users.get(lobby_id, set())
                user_lobbies.append({
                    "lobby_id": lobby_id,
                    "name": lobby["name"],
                    "is_active": is_active,
                    "is_creator": lobby_creators.get(lobby_id) == username
                })
        
        return {
            "user_id": user_id,
            "username": username,
            "created_at": user_data.get("created_at"),
            "last_active": user_data.get("last_active"),
            "lobbies": user_lobbies,
            "lobby_count": len(user_lobbies)
        }
    except HTTPException:
        raise HTTPException(404, "User not found")

# -----------------------------------------------------------------------------
# Enhanced WebSocket Implementation
# -----------------------------------------------------------------------------

@app.websocket("/ws/{lobby_id}/{user_id}")
async def ws_endpoint(websocket: WebSocket, lobby_id: str, user_id: str):
    """Enhanced WebSocket with better connection management"""
    await websocket.accept()

    try:
        username = get_username(user_id)
    except HTTPException:
        await websocket.close(code=1008, reason="User not found")
        return

    if lobby_id not in lobbies:
        await websocket.close(code=1008, reason="Lobby not found")
        return

    # Initialize connection tracking
    connections.setdefault(lobby_id, []).append(websocket)
    active_users.setdefault(lobby_id, set())
    
    was_empty = len(active_users[lobby_id]) == 0
    active_users[lobby_id].add(username)
    
    # Update user's last active time
    if username in users:
        users[username]["last_active"] = datetime.now().isoformat()

    # Send welcome and recent messages
    await send_lobby_welcome(lobby_id, websocket, username)

    # Broadcast join message if others are present
    if not was_empty:
        join_message = {
            "message_id": str(uuid.uuid4()),
            "username": "system",
            "type": "system",
            "message": f"👋 **{username}** joined the chat",
            "timestamp": datetime.now().isoformat(),
            "reply_to": None
        }
        add_message_to_lobby(lobby_id, join_message)
        await broadcast(lobby_id, join_message)

    try:
        while True:
            data = await websocket.receive_json()

            # Handle ping/pong for connection health
            if data.get("type") == "ping":
                await websocket.send_json({
                    "type": "pong", 
                    "timestamp": datetime.now().isoformat()
                })
                continue

            # Handle typing indicators
            if data.get("type") == "typing":
                typing_msg = {
                    "type": "typing",
                    "username": username,
                    "is_typing": data.get("is_typing", False),
                    "timestamp": datetime.now().isoformat()
                }
                # Broadcast typing indicator to others (not sender)
                for ws in connections.get(lobby_id, []):
                    if ws != websocket:
                        try:
                            await ws.send_json(typing_msg)
                        except:
                            pass
                continue

            # Handle regular messages
            message_text = data.get("message", "").strip()
            if not message_text:
                continue

            # Validate message length
            if len(message_text) > 1000:
                await websocket.send_json({
                    "type": "error",
                    "message": "Message too long (max 1000 characters)"
                })
                continue

            # Handle reply functionality
            reply_to = data.get("reply_to")
            replied_message = None
            if reply_to:
                lobby_msg_list = lobby_messages.get(lobby_id, [])
                replied_message = next((msg for msg in lobby_msg_list if msg["message_id"] == reply_to), None)

            # Create and broadcast message
            message = {
                "message_id": str(uuid.uuid4()),
                "username": username,
                "type": "user",
                "message": message_text,
                "timestamp": datetime.now().isoformat(),
                "reply_to": reply_to,
                "replied_message": replied_message
            }

            add_message_to_lobby(lobby_id, message)
            await broadcast(lobby_id, message)

            # Trigger background tasks
            asyncio.create_task(maybe_trigger_trivia(lobby_id))
            asyncio.create_task(trigger_bot_reply(lobby_id, message_text, username))

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {username} from {lobby_id}")
    except Exception as e:
        logger.error(f"WebSocket error for {username}: {e}")
    finally:
        # Cleanup connection
        try:
            connections[lobby_id].remove(websocket)
        except (KeyError, ValueError):
            pass

        # Remove from active users
        if username in active_users.get(lobby_id, set()):
            active_users[lobby_id].remove(username)

        # Broadcast leave message if others are still present
        if active_users.get(lobby_id) and len(active_users[lobby_id]) > 0:
            leave_message = {
                "message_id": str(uuid.uuid4()),
                "username": "system",
                "type": "system",
                "message": f"👋 **{username}** left the chat",
                "timestamp": datetime.now().isoformat(),
                "reply_to": None
            }
            add_message_to_lobby(lobby_id, leave_message)
            await broadcast(lobby_id, leave_message)

        # Schedule cleanup for empty lobbies
        if not active_users.get(lobby_id):
            asyncio.create_task(cleanup_empty_lobby(lobby_id))

async def cleanup_empty_lobby(lobby_id: str):
    """Enhanced lobby cleanup with longer grace period"""
    await asyncio.sleep(600)  # Wait 10 minutes
    
    # Check if still empty
    if (lobby_id in active_users and 
        len(active_users[lobby_id]) == 0 and
        lobby_id in connections and
        len(connections[lobby_id]) == 0):
        
        # Clean up all lobby data
        lobbies.pop(lobby_id, None)
        active_users.pop(lobby_id, None)
        connections.pop(lobby_id, None)
        lobby_creators.pop(lobby_id, None)
        lobby_bots.pop(lobby_id, None)
        lobby_message_counts.pop(lobby_id, None)
        lobby_trivia_active.pop(lobby_id, None)
        lobby_trivia_answers.pop(lobby_id, None)
        lobby_messages.pop(lobby_id, None)
        lobby_last_activity.pop(lobby_id, None)
        
        logger.info(f"Cleaned up empty lobby: {lobby_id}")

# -----------------------------------------------------------------------------
# Startup Instructions and Server Launch
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    
    print("\n" + "="*80)
    print("🚀 ENHANCED AI TRIVIA CHAT BACKEND - v4.0.0")
    print("="*80)
    
    print("\n✨ NEW FEATURES:")
    print("   ✅ Real AI responses (Hugging Face + Ollama)")
    print("   ✅ Message persistence & chat history")
    print("   ✅ Reply-to-message functionality")
    print("   ✅ Enhanced lobby management")
    print("   ✅ Better error handling & validation")
    print("   ✅ Professional empty state messages")
    print("   ✅ Improved trivia system")
    print("   ✅ Connection health monitoring")
    
    print("\n🔧 AI CONFIGURATION:")
    print("   🤖 Hugging Face:", "✅ Available" if HUGGINGFACE_API_KEY else "❌ Set HUGGINGFACE_API_KEY")
    print("   🦙 Ollama Local:", "✅ Enabled" if USE_LOCAL_OLLAMA else "❌ Set USE_LOCAL_OLLAMA=true")
    print("   🧠 Enhanced Rules: ✅ Always available")
    
    if not HUGGINGFACE_API_KEY and not USE_LOCAL_OLLAMA:
        print("\n⚠️  WARNING: No AI providers configured!")
        print("   Falling back to enhanced rule-based responses.")
        print("   For better AI, set up Hugging Face or Ollama.")
    
    print("\n📋 SETUP INSTRUCTIONS:")
    print("\n1. HUGGING FACE (FREE):")
    print("   • Sign up: https://huggingface.co")
    print("   • Get API key: https://huggingface.co/settings/tokens")
    print("   • Set: export HUGGINGFACE_API_KEY=your_key")
    
    print("\n2. OLLAMA (FREE LOCAL):")
    print("   • Install: curl -fsSL https://ollama.ai/install.sh | sh")
    print("   • Pull model: ollama pull llama2:7b")
    print("   • Set: export USE_LOCAL_OLLAMA=true")
    
    print("\n🌐 API ENDPOINTS:")
    print("   • WebSocket: ws://localhost:8080/ws/{lobby_id}/{user_id}")
    print("   • REST API: http://localhost:8080/docs")
    print("   • Health: http://localhost:8080/health")
    
    print(f"\n🎯 STARTING SERVER...")
    print("="*80 + "\n")
    
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"Starting enhanced trivia server on 0.0.0.0:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
