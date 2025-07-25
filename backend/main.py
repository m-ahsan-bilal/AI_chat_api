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
from datetime import datetime

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("trivia-api")

# -----------------------------------------------------------------------------
# App & CORS
# -----------------------------------------------------------------------------
app = FastAPI(title="Trivia Game API", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # tighten this in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------------------------------------------------------
# FREE AI Configuration
# -----------------------------------------------------------------------------
HUGGINGFACE_API_KEY = os.getenv("HUGGINGFACE_API_KEY", "")  # Free tier available
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")  # Local Ollama
USE_LOCAL_OLLAMA = os.getenv("USE_LOCAL_OLLAMA", "false").lower() == "true"

# Enhanced AI bots with FREE options
AI_BOTS = {
    "ChatBot": {
        "personality": "friendly and helpful chat companion",
        "provider": "huggingface",
        "model": "microsoft/DialoGPT-medium",
        "fallback_responses": [
            "That's really interesting! Tell me more! 🤖",
            "I love chatting with everyone here! What's your favorite topic?",
            "This lobby is so fun! Anyone ready for some trivia? 🎯",
            "Great point! I'm learning so much from you all.",
            "Awesome! What else should we talk about?"
        ]
    },
    "QuizMaster": {
        "personality": "enthusiastic trivia expert",
        "provider": "huggingface", 
        "model": "facebook/blenderbot-400M-distill",
        "fallback_responses": [
            "Did you know? Here's a fun fact I just thought of! 🧠",
            "That reminds me of an interesting trivia question!",
            "Speaking of trivia, who's ready for the next round? 🎲",
            "I love learning new things from our conversations!",
            "Fascinating! That could make a great trivia question."
        ]
    },
    "Cheerleader": {
        "personality": "upbeat and encouraging supporter",
        "provider": "enhanced_rules",
        "fallback_responses": [
            "You're all doing amazing! Keep it up! 🎉✨",
            "This energy is incredible! I love it here! 💪",
            "You all rock! This is the best lobby ever! 🌟",
            "Such smart people in here! You inspire me! 🚀",
            "Woohoo! The fun never stops with you all! 🎊"
        ]
    },
    "Philosopher": {
        "personality": "thoughtful and wise",
        "provider": "enhanced_rules",
        "fallback_responses": [
            "That makes me think... isn't it fascinating how we connect? 🤔",
            "There's wisdom in every conversation, don't you think?",
            "I wonder what deeper meaning lies in our discussions... 💭",
            "Every person brings unique perspective. How wonderful! 🌈",
            "In this digital space, we create real human connections. Amazing!"
        ]
    }
}

# -----------------------------------------------------------------------------
# In-memory Stores
# -----------------------------------------------------------------------------
users: Dict[str, dict] = {}                       # username -> {user_id}
lobbies: Dict[UUID, dict] = {}                    # lobby_id -> lobby info
connections: Dict[UUID, List[WebSocket]] = {}     # lobby_id -> websocket list
active_users: Dict[UUID, Set[str]] = {}           # lobby_id -> active usernames set
lobby_creators: Dict[UUID, str] = {}              # lobby_id -> username
lobby_bots: Dict[UUID, List[str]] = {}            # lobby_id -> list of bot names
lobby_message_counts: Dict[UUID, int] = {}        # lobby_id -> int
lobby_trivia_active: Dict[UUID, bool] = {}        # lobby_id -> bool
lobby_trivia_answers: Dict[UUID, Dict[str, int]] = {}  # lobby_id -> {username: answer_index}
bot_conversation_history: Dict[str, List[dict]] = {}  # bot_name -> conversation history

# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------
MESSAGES_BETWEEN_TRIVIA = 8

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
    {"question": "Who wrote 'Romeo and Juliet'?", "options": ["Charles Dickens", "William Shakespeare", "Mark Twain", "Jane Austen"], "correct": 1}
]

# -----------------------------------------------------------------------------
# FREE AI Integration Functions
# -----------------------------------------------------------------------------

async def call_huggingface_api(model: str, prompt: str, max_length: int = 100) -> str:
    """Call Hugging Face Inference API - FREE tier available"""
    if not HUGGINGFACE_API_KEY:
        return None
        
    url = f"https://api-inference.huggingface.co/models/{model}"
    headers = {"Authorization": f"Bearer {HUGGINGFACE_API_KEY}"}
    
    payload = {
        "inputs": prompt,
        "parameters": {
            "max_length": max_length,
            "temperature": 0.7,
            "do_sample": True
        }
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=10) as response:
                if response.status == 200:
                    result = await response.json()
                    if isinstance(result, list) and len(result) > 0:
                        return result[0].get("generated_text", "").replace(prompt, "").strip()
                return None
    except Exception as e:
        logger.error(f"Hugging Face API error: {e}")
        return None

async def call_ollama_api(model: str, prompt: str) -> str:
    """Call local Ollama API - COMPLETELY FREE"""
    if not USE_LOCAL_OLLAMA:
        return None
        
    try:
        url = f"{OLLAMA_BASE_URL}/api/generate"
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.7,
                "top_p": 0.9
            }
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=15) as response:
                if response.status == 200:
                    result = await response.json()
                    return result.get("response", "").strip()
                return None
    except Exception as e:
        logger.error(f"Ollama API error: {e}")
        return None

async def enhanced_rule_based_reply(bot_name: str, user_message: str, conversation_context: List[str]) -> str:
    """Enhanced rule-based AI with context awareness"""
    bot_config = AI_BOTS.get(bot_name, {})
    personality = bot_config.get("personality", "friendly")
    
    message_lower = user_message.lower()
    
    # Context-aware responses
    recent_messages = conversation_context[-3:] if conversation_context else []
    context_topics = []
    for msg in recent_messages:
        if any(word in msg.lower() for word in ["trivia", "question", "quiz"]):
            context_topics.append("trivia")
        if any(word in msg.lower() for word in ["game", "play", "fun"]):
            context_topics.append("gaming")
        if any(word in msg.lower() for word in ["score", "win", "lose"]):
            context_topics.append("competition")
    
    # Personality-based responses
    if "cheerleader" in personality:
        responses = [
            "You're absolutely amazing! Keep going! 🌟",
            "I believe in all of you! This is so exciting! 🎉",
            "What incredible energy in here! Love it! ✨",
            "You all inspire me so much! Keep being awesome! 🚀",
            "This is the best conversation ever! You rock! 💪"
        ]
        
        if "trivia" in context_topics:
            responses.extend([
                "Trivia time is the best time! You've got this! 🎯",
                "I know you'll nail these questions! Go team! 🏆",
                "Smart cookies in the house! Show off those brains! 🧠✨"
            ])
            
    elif "philosopher" in personality:
        responses = [
            "Isn't it fascinating how ideas flow in conversation? 🤔",
            "Each message reveals something profound about human nature...",
            "In this digital realm, we create meaningful connections. Wonderful! 💭",
            "I ponder the beauty of shared knowledge and curiosity.",
            "Every question opens doorways to deeper understanding. 🌅"
        ]
        
        if "trivia" in context_topics:
            responses.extend([
                "Trivia reveals the vast tapestry of human knowledge, doesn't it?",
                "Each question is a key to unlock memories and learning. Intriguing! 🗝️",
                "Competition brings out our desire for intellectual growth. Beautiful!"
            ])
            
    elif "expert" in personality or "quiz" in personality:
        responses = [
            "That's a fascinating topic! Here's what I know about it... 🧠",
            "Did you know that connects to this interesting fact? 📚",
            "Speaking of knowledge, here's something cool I learned! 🎓",
            "I love how we're all sharing what we know! Education is amazing! 🌟",
            "That reminds me of a great trivia category! Anyone interested? 🎯"
        ]
        
    else:  # friendly default
        responses = [
            "That's really cool! Tell me more about that! 😊",
            "I'm enjoying this conversation so much! What's next? 🤖",
            "You all make this lobby such a fun place to be! 🎉",
            "Great point! I love learning from everyone here! 📝",
            "This chat is getting interesting! Keep it going! 💬"
        ]
    
    # Message-specific triggers
    if any(word in message_lower for word in ["hello", "hi", "hey"]):
        return f"Hey there! Great to see you! How's everyone doing? 👋"
    
    if any(word in message_lower for word in ["bye", "goodbye", "leaving"]):
        return f"Aww, sad to see you go! Come back soon! 👋✨"
    
    if "trivia" in message_lower:
        return f"Trivia is my favorite! Ready for some brain-busting questions? 🧠🎯"
    
    if any(word in message_lower for word in ["how are you", "how do you feel"]):
        return f"I'm doing fantastic! This lobby has such great energy! How about you? 😊"
    
    if "?" in user_message:
        return f"That's a great question! Let me think... 🤔 {random.choice(responses)}"
    
    return random.choice(responses)

async def get_ai_response(bot_name: str, user_message: str, username: str) -> str:
    """Get AI response using available FREE methods"""
    bot_config = AI_BOTS.get(bot_name, {})
    provider = bot_config.get("provider", "enhanced_rules")
    
    # Build conversation context
    history_key = f"{bot_name}_context"
    if history_key not in bot_conversation_history:
        bot_conversation_history[history_key] = []
    
    conversation_context = [msg["content"] for msg in bot_conversation_history[history_key][-5:]]
    
    response = None
    
    # Try Hugging Face first (if available)
    if provider == "huggingface" and HUGGINGFACE_API_KEY:
        model = bot_config.get("model", "microsoft/DialoGPT-medium")
        prompt = f"Context: You are a {bot_config['personality']} in a chat game. Respond to: {user_message}"
        response = await call_huggingface_api(model, prompt)
        
    # Try Ollama second (if available)
    if not response and USE_LOCAL_OLLAMA:
        model = "llama2:7b"  # or any model you have installed
        prompt = f"As a {bot_config.get('personality', 'friendly bot')}, respond briefly to: {user_message}"
        response = await call_ollama_api(model, prompt)
    
    # Fallback to enhanced rule-based
    if not response:
        response = await enhanced_rule_based_reply(bot_name, user_message, conversation_context)
    
    # Update conversation history
    bot_conversation_history[history_key].append({
        "role": "user",
        "content": f"{username}: {user_message}",
        "timestamp": datetime.now().isoformat()
    })
    bot_conversation_history[history_key].append({
        "role": "assistant", 
        "content": response,
        "timestamp": datetime.now().isoformat()
    })
    
    # Keep only last 10 messages to prevent memory bloat
    if len(bot_conversation_history[history_key]) > 10:
        bot_conversation_history[history_key] = bot_conversation_history[history_key][-10:]
    
    return response

# -----------------------------------------------------------------------------
# Bot Reply Function (Updated)
# -----------------------------------------------------------------------------
async def trigger_bot_reply(lobby_id: UUID, user_message: str, human_username: str):
    """Trigger bot replies with AI integration"""
    bots = lobby_bots.get(lobby_id, [])
    if not bots:
        return

    # Simulate thinking delay
    await asyncio.sleep(random.uniform(1.5, 3.0))

    # Choose a bot to respond (not always all bots)
    responding_bot = random.choice(bots)
    
    try:
        # Get AI-powered response
        reply = await get_ai_response(responding_bot, user_message, human_username)
        
        await broadcast(lobby_id, {
            "username": responding_bot,
            "type": "bot",
            "message": reply,
            "timestamp": datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Bot reply error: {e}")
        # Ultimate fallback
        fallback_responses = AI_BOTS.get(responding_bot, {}).get("fallback_responses", [
            "That's interesting! 🤖",
            "Tell me more!",
            "Great point! 💫"
        ])
        fallback_reply = random.choice(fallback_responses)
        
        await broadcast(lobby_id, {
            "username": responding_bot,
            "type": "bot", 
            "message": fallback_reply,
            "timestamp": datetime.now().isoformat()
        })

# -----------------------------------------------------------------------------
# Pydantic Models
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
    lobby_id: UUID
    user_id: str

class LeaveLobbyRequest(BaseModel):
    lobby_id: UUID
    user_id: str

class AddBotRequest(BaseModel):
    bot_name: str = "ChatBot"

class TriviaAnswerRequest(BaseModel):
    user_id: str
    answer: int

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def generate_invite_code() -> str:
    return str(uuid.uuid4())[:6].upper()

def get_username(user_id: str) -> str:
    for username, data in users.items():
        if data["user_id"] == user_id:
            return username
    raise HTTPException(404, "User not found")

def find_lobby_by_invite(invite_code: str) -> UUID:
    for lid, lobby in lobbies.items():
        if lobby["invite_code"] == invite_code:
            return lid
    raise HTTPException(404, "Lobby not found")

async def broadcast(lobby_id: UUID, message: dict):
    """Broadcast a JSON message to everyone in the lobby."""
    if lobby_id not in connections:
        return

    for ws in connections[lobby_id][:]:
        try:
            await ws.send_json(message)
        except Exception:
            try:
                connections[lobby_id].remove(ws)
            except ValueError:
                pass

async def send_lobby_welcome(lobby_id: UUID, websocket: WebSocket):
    lobby = lobbies.get(lobby_id)
    if not lobby:
        return
    creator = lobby_creators.get(lobby_id, "Unknown")
    welcome = {
        "username": "system",
        "type": "system",
        "message": f"🎮 Welcome to '{lobby['name']}'! Created by {creator}. Say hi to get the bots talking!",
        "timestamp": datetime.now().isoformat()
    }
    try:
        await websocket.send_json(welcome)
    except Exception:
        pass

# -----------------------------------------------------------------------------
# Trivia Functions (Updated)
# -----------------------------------------------------------------------------
async def maybe_trigger_trivia(lobby_id: UUID):
    lobby_message_counts[lobby_id] = lobby_message_counts.get(lobby_id, 0) + 1

    if (lobby_message_counts[lobby_id] % MESSAGES_BETWEEN_TRIVIA == 0
        and not lobby_trivia_active.get(lobby_id, False)):
        await start_trivia_round(lobby_id)

async def start_trivia_round(lobby_id: UUID):
    try:
        lobby_trivia_active[lobby_id] = True
        lobby_trivia_answers[lobby_id] = {}

        trivia = random.choice(TRIVIA_QUESTIONS)
        trivia_msg = {
            "username": "🎯 TriviaBot",
            "type": "trivia",
            "message": f"⏰ TRIVIA TIME! Answer within 30 seconds:\n\n{trivia['question']}",
            "trivia_data": {
                "question": trivia["question"],
                "options": trivia["options"],
                "time_limit": 30
            },
            "timestamp": datetime.now().isoformat()
        }

        await broadcast(lobby_id, trivia_msg)

        correct_idx = trivia["correct"]
        await asyncio.sleep(30)
        await end_trivia_round(lobby_id, correct_idx)

    except Exception as e:
        logger.exception("start_trivia_round error")
        lobby_trivia_active[lobby_id] = False

async def end_trivia_round(lobby_id: UUID, correct_answer_index: int):
    try:
        answers = lobby_trivia_answers.get(lobby_id, {})
        winners = [u for u, a in answers.items() if a == correct_answer_index]

        if winners:
            msg = {
                "username": "🎯 TriviaBot",
                "type": "trivia_result",
                "message": f"🎉 Correct answer was option {correct_answer_index + 1}!\nWinners: {', '.join(winners)}",
                "winners": winners,
                "correct_answer": correct_answer_index,
                "timestamp": datetime.now().isoformat()
            }
        else:
            msg = {
                "username": "🎯 TriviaBot", 
                "type": "trivia_result",
                "message": f"⏰ Time's up! The correct answer was option {correct_answer_index + 1}.\nBetter luck next time!",
                "winners": [],
                "correct_answer": correct_answer_index,
                "timestamp": datetime.now().isoformat()
            }

        await broadcast(lobby_id, msg)

    except Exception:
        logger.exception("end_trivia_round error")
    finally:
        lobby_trivia_active[lobby_id] = False
        lobby_trivia_answers[lobby_id] = {}

# -----------------------------------------------------------------------------
# REST Endpoints (Updated)
# -----------------------------------------------------------------------------
@app.post("/register", response_model=RegisterResponse)
async def register(req: RegisterRequest):
    if req.username in users:
        raise HTTPException(400, "Username already taken.")

    user_id = str(uuid.uuid4())
    users[req.username] = {"user_id": user_id, "created_at": datetime.now().isoformat()}
    logger.info("Registered user=%s id=%s", req.username, user_id)
    return RegisterResponse(user_id=user_id)

@app.post("/lobbies", response_model=CreateLobbyResponse)
async def create_lobby(req: CreateLobbyRequest):
    lobby_id = uuid.uuid4()
    invite_code = generate_invite_code()

    lobbies[lobby_id] = {
        "id": lobby_id,
        "name": req.name,
        "max_humans": req.max_humans,
        "max_bots": req.max_bots,
        "is_private": req.is_private,
        "users": [],
        "invite_code": invite_code,
        "created_at": datetime.now().isoformat()
    }

    active_users[lobby_id] = set()
    lobby_bots[lobby_id] = []
    lobby_message_counts[lobby_id] = 0
    lobby_trivia_active[lobby_id] = False
    lobby_trivia_answers[lobby_id] = {}

    logger.info("Created lobby=%s (private=%s)", lobby_id, req.is_private)
    return CreateLobbyResponse(lobby_id=str(lobby_id), invite_code=invite_code, name=req.name)

@app.get("/lobbies")
async def list_lobbies():
    """Returns public lobbies with enhanced info"""
    public_lobbies = []
    for lobby in lobbies.values():
        if not lobby.get("is_private", False):
            public_lobbies.append({
                "lobby_id": str(lobby["id"]),
                "name": lobby["name"],
                "current_players": len(lobby["users"]),
                "max_humans": lobby["max_humans"],
                "current_bots": len(lobby_bots.get(lobby["id"], [])),
                "max_bots": lobby["max_bots"],
                "is_private": lobby["is_private"],
                "has_trivia_active": lobby_trivia_active.get(lobby["id"], False),
                "message_count": lobby_message_counts.get(lobby["id"], 0)
            })
    return public_lobbies

@app.post("/lobbies/join-invite")
async def join_lobby_with_invite(req: JoinLobbyByInviteRequest):
    lobby_id = find_lobby_by_invite(req.invite_code)
    return await _join_lobby_core(lobby_id, req.user_id)

@app.post("/lobbies/join-public") 
async def join_public_lobby(req: JoinLobbyPublicRequest):
    if req.lobby_id not in lobbies:
        raise HTTPException(404, "Lobby not found")
    return await _join_lobby_core(req.lobby_id, req.user_id)

async def _join_lobby_core(lobby_id: UUID, user_id: str):
    lobby = lobbies.get(lobby_id)
    if not lobby:
        raise HTTPException(404, "Lobby not found")

    username = get_username(user_id)

    if username in lobby["users"]:
        return {"message": f"{username} rejoined the lobby.", "lobby_id": str(lobby_id)}

    if len(lobby["users"]) >= lobby["max_humans"]:
        raise HTTPException(400, "Lobby is full.")

    lobby["users"].append(username)

    if len(lobby["users"]) == 1:
        lobby_creators[lobby_id] = username

    logger.info("User=%s joined lobby=%s", username, lobby_id)
    return {"message": f"{username} joined the lobby.", "lobby_id": str(lobby_id)}

@app.post("/lobbies/leave")
async def leave_lobby(req: LeaveLobbyRequest):
    lobby = lobbies.get(req.lobby_id)
    if not lobby:
        raise HTTPException(404, "Lobby not found")

    username = get_username(req.user_id)

    if username not in lobby["users"]:
        raise HTTPException(400, "User not in lobby.")

    lobby["users"].remove(username)
    logger.info("User=%s left lobby=%s", username, req.lobby_id)
    return {"message": f"{username} left the lobby."}

@app.post("/lobbies/{lobby_id}/add-bot")
async def add_bot(lobby_id: UUID, req: AddBotRequest):
    if lobby_id not in lobbies:
        raise HTTPException(404, "Lobby not found")

    lobby = lobbies[lobby_id]
    current_bots = len(lobby_bots.get(lobby_id, []))
    
    if current_bots >= lobby.get("max_bots", 2):
        raise HTTPException(400, "Maximum bots reached")

    bot_name = req.bot_name if req.bot_name in AI_BOTS else "ChatBot"
    
    if bot_name not in lobby_bots[lobby_id]:
        lobby_bots[lobby_id].append(bot_name)
        
        # Initialize bot conversation history
        history_key = f"{bot_name}_context"
        if history_key not in bot_conversation_history:
            bot_conversation_history[history_key] = []

        await broadcast(lobby_id, {
            "username": "system",
            "type": "system",
            "message": f"🤖 {bot_name} has joined the chat! Say hello to get them talking!",
            "timestamp": datetime.now().isoformat()
        })

    return {"message": f"{bot_name} added to lobby", "bot_count": len(lobby_bots[lobby_id])}

@app.post("/lobbies/{lobby_id}/trivia-answer")
async def submit_trivia_answer(lobby_id: UUID, req: TriviaAnswerRequest):
    if lobby_id not in lobbies:
        raise HTTPException(404, "Lobby not found")

    if not lobby_trivia_active.get(lobby_id, False):
        raise HTTPException(400, "No active trivia round")

    username = get_username(req.user_id)
    lobby_trivia_answers.setdefault(lobby_id, {})
    lobby_trivia_answers[lobby_id][username] = req.answer

    await broadcast(lobby_id, {
        "username": "system",
        "type": "system", 
        "message": f"✅ {username} submitted their answer!",
        "timestamp": datetime.now().isoformat()
    })

    return {"message": "Answer submitted"}

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "users": len(users),
        "lobbies": len(lobbies),
        "active_ws": sum(len(conns) for conns in connections.values()),
        "ai_config": {
            "huggingface_available": bool(HUGGINGFACE_API_KEY),
            "ollama_available": USE_LOCAL_OLLAMA,
            "enhanced_rules": True
        },
        "timestamp": datetime.now().isoformat()
    }

@app.get("/bots")
async def list_available_bots():
    """List all available AI bots with their configurations"""
    return {
        "available_bots": [
            {
                "name": name,
                "personality": config["personality"],
                "provider": config["provider"]
            }
            for name, config in AI_BOTS.items()
        ]
    }

# -----------------------------------------------------------------------------
# WebSocket (Updated)
# -----------------------------------------------------------------------------
@app.websocket("/ws/{lobby_id}/{user_id}")
async def ws_endpoint(websocket: WebSocket, lobby_id: UUID, user_id: str):
    # Accept connection
    await websocket.accept()

    # Validate user & lobby
    try:
        username = get_username(user_id)
    except HTTPException:
        await websocket.close(code=1008, reason="User not found")
        return

    if lobby_id not in lobbies:
        await websocket.close(code=1008, reason="Lobby not found")
        return

    # Register connection
    connections.setdefault(lobby_id, []).append(websocket)
    active_users.setdefault(lobby_id, set())

    was_empty = len(active_users[lobby_id]) == 0
    active_users[lobby_id].add(username)

    # Send welcome message
    await send_lobby_welcome(lobby_id, websocket)

    # Broadcast join message if others are present
    if not was_empty:
        await broadcast(lobby_id, {
            "username": "system",
            "type": "system",
            "message": f"👋 {username} joined the chat.",
            "timestamp": datetime.now().isoformat()
        })

    # Send current lobby status
    lobby = lobbies.get(lobby_id)
    status_msg = {
        "username": "system",
        "type": "lobby_status",
        "message": f"📊 Lobby Status: {len(active_users[lobby_id])} users, {len(lobby_bots.get(lobby_id, []))} bots active",
        "lobby_data": {
            "active_users": list(active_users[lobby_id]),
            "active_bots": lobby_bots.get(lobby_id, []),
            "trivia_active": lobby_trivia_active.get(lobby_id, False),
            "message_count": lobby_message_counts.get(lobby_id, 0)
        },
        "timestamp": datetime.now().isoformat()
    }
    
    try:
        await websocket.send_json(status_msg)
    except Exception:
        pass

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
                await broadcast(lobby_id, {
                    "username": username,
                    "type": "typing",
                    "is_typing": data.get("is_typing", False),
                    "timestamp": datetime.now().isoformat()
                })
                continue

            # Handle regular messages
            text = data.get("message", "").strip()
            if not text:
                continue

            # Broadcast user message with enhanced metadata
            msg = {
                "username": username,
                "type": "user",
                "message": text,
                "timestamp": datetime.now().isoformat(),
                "message_id": str(uuid.uuid4())[:8]
            }
            await broadcast(lobby_id, msg)

            # Trigger background tasks (don't await to avoid blocking)
            asyncio.create_task(maybe_trigger_trivia(lobby_id))
            asyncio.create_task(trigger_bot_reply(lobby_id, text, username))

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {username} from {lobby_id}")
    except Exception as e:
        logger.exception(f"WebSocket error for {username}: {e}")
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
            await broadcast(lobby_id, {
                "username": "system",
                "type": "system",
                "message": f"👋 {username} left the chat.",
                "timestamp": datetime.now().isoformat()
            })

        # Clean up empty lobbies after some time
        if not active_users.get(lobby_id):
            # Schedule cleanup after 5 minutes of inactivity
            asyncio.create_task(cleanup_empty_lobby(lobby_id))

async def cleanup_empty_lobby(lobby_id: UUID):
    """Clean up empty lobbies after delay"""
    await asyncio.sleep(300)  # Wait 5 minutes
    
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
        
        logger.info(f"Cleaned up empty lobby: {lobby_id}")

# -----------------------------------------------------------------------------
# Additional API Endpoints for Flutter Integration
# -----------------------------------------------------------------------------

@app.get("/lobbies/{lobby_id}/info")
async def get_lobby_info(lobby_id: UUID):
    """Get detailed lobby information for Flutter app"""
    if lobby_id not in lobbies:
        raise HTTPException(404, "Lobby not found")
    
    lobby = lobbies[lobby_id]
    return {
        "lobby_id": str(lobby_id),
        "name": lobby["name"],
        "users": lobby["users"],
        "active_users": list(active_users.get(lobby_id, set())),
        "bots": lobby_bots.get(lobby_id, []),
        "max_humans": lobby["max_humans"],
        "max_bots": lobby["max_bots"],
        "is_private": lobby["is_private"],
        "invite_code": lobby["invite_code"],
        "creator": lobby_creators.get(lobby_id, "Unknown"),
        "message_count": lobby_message_counts.get(lobby_id, 0),
        "trivia_active": lobby_trivia_active.get(lobby_id, False),
        "created_at": lobby.get("created_at"),
        "ai_available": {
            "huggingface": bool(HUGGINGFACE_API_KEY),
            "ollama": USE_LOCAL_OLLAMA,
            "enhanced_rules": True
        }
    }

@app.post("/lobbies/{lobby_id}/remove-bot")
async def remove_bot(lobby_id: UUID, req: AddBotRequest):
    """Remove a bot from the lobby"""
    if lobby_id not in lobbies:
        raise HTTPException(404, "Lobby not found")

    bot_name = req.bot_name
    if bot_name in lobby_bots.get(lobby_id, []):
        lobby_bots[lobby_id].remove(bot_name)
        
        # Clean up bot conversation history
        history_key = f"{bot_name}_context"
        bot_conversation_history.pop(history_key, None)
        
        await broadcast(lobby_id, {
            "username": "system",
            "type": "system",
            "message": f"🤖 {bot_name} has left the chat.",
            "timestamp": datetime.now().isoformat()
        })
        
        return {"message": f"{bot_name} removed from lobby"}
    else:
        raise HTTPException(404, "Bot not found in lobby")

@app.get("/lobbies/{lobby_id}/messages/recent")
async def get_recent_messages(lobby_id: UUID, limit: int = 50):
    """Get recent messages for lobby (useful for reconnection)"""
    if lobby_id not in lobbies:
        raise HTTPException(404, "Lobby not found")
    
    # In a real app, you'd store messages in a database
    # For now, return empty as messages are only live via WebSocket
    return {
        "lobby_id": str(lobby_id),
        "messages": [],
        "note": "Messages are real-time only via WebSocket in this demo"
    }

# -----------------------------------------------------------------------------
# Entrypoint with Environment Setup Instructions
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    
    # Print setup instructions
    print("\n" + "="*60)
    print("🚀 FREE AI TRIVIA CHAT BACKEND STARTING")
    print("="*60)
    print("\n📋 SETUP INSTRUCTIONS FOR FREE AI:")
    print("\n1. HUGGING FACE (FREE TIER):")
    print("   - Sign up at https://huggingface.co")
    print("   - Get free API key from https://huggingface.co/settings/tokens")
    print("   - Set: export HUGGINGFACE_API_KEY=your_token_here")
    print("\n2. OLLAMA (COMPLETELY FREE - LOCAL):")
    print("   - Install: curl -fsSL https://ollama.ai/install.sh | sh")
    print("   - Run: ollama pull llama2:7b")
    print("   - Set: export USE_LOCAL_OLLAMA=true")
    print("\n3. ENHANCED RULES (CURRENT - ALWAYS WORKS):")
    print("   - Smart context-aware responses")
    print("   - No API keys needed")
    print("   - Works out of the box!")
    
    print(f"\n🔧 CURRENT CONFIG:")
    print(f"   Hugging Face: {'✅ Available' if HUGGINGFACE_API_KEY else '❌ Not configured'}")
    print(f"   Ollama Local: {'✅ Enabled' if USE_LOCAL_OLLAMA else '❌ Disabled'}")
    print(f"   Enhanced Rules: ✅ Always available")
    
    print(f"\n🌐 Starting server...")
    print("="*60 + "\n")
    
    port = int(os.environ.get("PORT", 8080))
    logger.info("Starting server on 0.0.0.0:%d", port)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
