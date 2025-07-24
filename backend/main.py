from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Set
import uuid
from uuid import UUID
import logging
import asyncio
import aiohttp
import json
import random

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Trivia Game API", version="3.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- In-memory Data Stores ---
users: Dict[str, dict] = {}
lobbies: Dict[UUID, dict] = {}
connections: Dict[UUID, List[WebSocket]] = {}
active_users: Dict[UUID, Set[str]] = {}
lobby_creators: Dict[UUID, str] = {}
lobby_bots: Dict[UUID, List[str]] = {}
lobby_message_counts: Dict[UUID, int] = {}
lobby_trivia_active: Dict[UUID, bool] = {}
lobby_trivia_answers: Dict[UUID, Dict[str, int]] = {}

# FREE AI Configuration using Hugging Face
HUGGING_FACE_API_URL = "https://api-inference.huggingface.co/models/microsoft/DialoGPT-large"
HUGGING_FACE_TOKEN = "hf_your_free_token_here"  # Get free token from huggingface.co

AI_BOTS = {
    "ChatBot": "You are a friendly trivia game bot.",
    "QuizMaster": "You are a trivia expert who loves asking questions.",
    "Cheerleader": "You are an enthusiastic supporter who cheers everyone on!"
}

# Trivia questions
TRIVIA_QUESTIONS = [
    {"question": "What is the capital of France?", "options": ["London", "Berlin", "Paris", "Madrid"], "correct": 2},
    {"question": "Which planet is closest to the Sun?", "options": ["Venus", "Mercury", "Earth", "Mars"], "correct": 1},
    {"question": "What is 15 + 27?", "options": ["41", "42", "43", "44"], "correct": 1},
    {"question": "Who painted the Mona Lisa?", "options": ["Van Gogh", "Picasso", "Da Vinci", "Monet"], "correct": 2},
    {"question": "What is the largest ocean?", "options": ["Atlantic", "Indian", "Arctic", "Pacific"], "correct": 3},
    {"question": "How many continents are there?", "options": ["5", "6", "7", "8"], "correct": 2},
    {"question": "What year did World War 2 end?", "options": ["1944", "1945", "1946", "1947"], "correct": 1},
]

MESSAGES_BETWEEN_TRIVIA = 8

# --- Models ---
class RegisterRequest(BaseModel):
    username: str

class RegisterResponse(BaseModel):
    user_id: str

class CreateLobbyRequest(BaseModel):
    name: str
    max_humans: int = 5
    max_bots: int = 0
    is_private: bool = False

class JoinLobbyRequest(BaseModel):
    invite_code: str
    user_id: str

class LeaveLobbyRequest(BaseModel):
    lobby_id: UUID
    user_id: str

class AddBotRequest(BaseModel):
    bot_name: str = "ChatBot"

class TriviaAnswerRequest(BaseModel):
    user_id: str
    answer: int

# --- Helper Functions ---
def generate_invite_code():
    return str(uuid.uuid4())[:6]

def find_lobby_by_invite(invite_code: str):
    for lobby_id, lobby in lobbies.items():
        if lobby["invite_code"] == invite_code:
            return lobby
    raise HTTPException(404, "Lobby not found.")

def get_username(user_id: str):
    for username, data in users.items():
        if data["user_id"] == user_id:
            return username
    raise HTTPException(404, "User not found.")

async def broadcast(lobby_id: UUID, message: dict):
    if lobby_id in connections:
        for ws in connections[lobby_id][:]:
            try:
                await ws.send_json(message)
            except:
                connections[lobby_id].remove(ws)

async def send_lobby_info(lobby_id: UUID, websocket: WebSocket):
    if lobby_id not in lobbies:
        return
    
    lobby = lobbies[lobby_id]
    creator = lobby_creators.get(lobby_id, "Unknown")
    
    creation_message = {
        "username": "system",
        "message": f"Welcome to '{lobby['name']}'! This lobby was created by {creator}.",
        "type": "system"
    }
    
    try:
        await websocket.send_json(creation_message)
    except:
        pass

# FREE AI API call using Hugging Face
async def call_free_ai_api(message: str, bot_name: str) -> str:
    try:
        # Fallback responses for when API is unavailable
        fallback_responses = [
            f"That's interesting! 🤖",
            f"Tell me more about that!",
            f"Great point! What do you think about trivia?",
            f"I love chatting with everyone here! 😊",
            f"Anyone ready for some trivia? 🎯",
            f"This lobby is so fun! Keep chatting!",
            f"I'm learning so much from you all!",
            f"That's a cool message! 👍"
        ]
        
        # Simple rule-based responses (works without API)
        message_lower = message.lower()
        if "hello" in message_lower or "hi" in message_lower:
            return f"Hello there! Welcome to the chat! 👋"
        elif "trivia" in message_lower:
            return f"I love trivia! Ready for some brain teasers? 🧠"
        elif "question" in message_lower:
            return f"Great question! I wish I had all the answers! 🤔"
        elif "game" in message_lower:
            return f"Games are so much fun! This trivia chat is awesome! 🎮"
        else:
            return random.choice(fallback_responses)
            
    except Exception as e:
        logger.error(f"AI API error: {e}")
        return f"*{bot_name} is thinking...* 🤖"

async def trigger_bot_response(lobby_id: UUID, user_message: str, username: str):
    if lobby_id not in lobby_bots or not lobby_bots[lobby_id]:
        return
    
    # Random delay between 1-3 seconds
    await asyncio.sleep(random.uniform(1.0, 3.0))
    
    # Pick a random bot from this lobby
    bot_name = random.choice(lobby_bots[lobby_id])
    
    # Get AI response
    ai_response = await call_free_ai_api(f"{username} said: {user_message}", bot_name)
    
    # Broadcast bot response
    bot_message = {
        "username": bot_name,
        "message": ai_response,
        "type": "bot"
    }
    await broadcast(lobby_id, bot_message)

async def check_trivia_trigger(lobby_id: UUID):
    if lobby_id not in lobby_message_counts:
        lobby_message_counts[lobby_id] = 0
    
    lobby_message_counts[lobby_id] += 1
    
    if (lobby_message_counts[lobby_id] % MESSAGES_BETWEEN_TRIVIA == 0 and 
        not lobby_trivia_active.get(lobby_id, False)):
        await start_trivia_round(lobby_id)

async def start_trivia_round(lobby_id: UUID):
    try:
        lobby_trivia_active[lobby_id] = True
        lobby_trivia_answers[lobby_id] = {}
        
        trivia = random.choice(TRIVIA_QUESTIONS)
        
        trivia_message = {
            "username": "🎯 TriviaBot",
            "message": f"⏰ TRIVIA TIME! Answer within 30 seconds:\n\n{trivia['question']}",
            "type": "trivia",
            "trivia_data": {
                "question": trivia["question"],
                "options": trivia["options"]
            }
        }
        
        await broadcast(lobby_id, trivia_message)
        
        correct_answer = trivia["correct"]
        await asyncio.sleep(30)
        await end_trivia_round(lobby_id, correct_answer)
        
    except Exception as e:
        logger.error(f"Trivia error: {e}")
        lobby_trivia_active[lobby_id] = False

async def end_trivia_round(lobby_id: UUID, correct_answer: int):
    try:
        if lobby_id not in lobby_trivia_answers:
            return
            
        answers = lobby_trivia_answers[lobby_id]
        correct_users = [user for user, answer in answers.items() if answer == correct_answer]
        
        if correct_users:
            result_message = {
                "username": "🎯 TriviaBot",
                "message": f"🎉 Correct! Winners: {', '.join(correct_users)}",
                "type": "system"
            }
        else:
            result_message = {
                "username": "🎯 TriviaBot", 
                "message": f"⏰ Time's up! The correct answer was option {correct_answer + 1}",
                "type": "system"
            }
        
        await broadcast(lobby_id, result_message)
        
        lobby_trivia_active[lobby_id] = False
        lobby_trivia_answers[lobby_id] = {}
        
    except Exception as e:
        logger.error(f"End trivia error: {e}")

# --- API Endpoints ---
@app.post("/register", response_model=RegisterResponse)
async def register(req: RegisterRequest):
    try:
        if req.username in users:
            raise HTTPException(400, "Username already taken.")
        
        user_id = str(uuid.uuid4())
        users[req.username] = {"user_id": user_id}
        logger.info(f"User {req.username} registered with ID: {user_id}")
        return RegisterResponse(user_id=user_id)
    except Exception as e:
        logger.error(f"Registration error: {e}")
        raise HTTPException(500, f"Registration failed: {str(e)}")

@app.post("/lobbies")
async def create_lobby(req: CreateLobbyRequest):
    try:
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
            "created_at": str(uuid.uuid4())
        }
        
        active_users[lobby_id] = set()
        lobby_bots[lobby_id] = []
        
        return {
            "lobby_id": str(lobby_id),
            "invite_code": invite_code,
            "name": req.name
        }
    except Exception as e:
        logger.error(f"Create lobby error: {e}")
        raise HTTPException(500, f"Failed to create lobby: {str(e)}")

@app.post("/lobbies/join-invite")
async def join_lobby(req: JoinLobbyRequest):
    try:
        lobby = find_lobby_by_invite(req.invite_code)
        username = get_username(req.user_id)
        
        if username in lobby["users"]:
            raise HTTPException(400, "User already in lobby.")
        
        if len(lobby["users"]) >= lobby["max_humans"]:
            raise HTTPException(400, "Lobby is full.")
        
        lobby["users"].append(username)
        
        lobby_id = None
        for lid, lob in lobbies.items():
            if lob == lobby:
                lobby_id = lid
                break
        
        if lobby_id and len(lobby["users"]) == 1:
            lobby_creators[lobby_id] = username
        
        logger.info(f"User {username} joined lobby {lobby_id}")
        return {"message": f"{username} joined the lobby."}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Join lobby error: {e}")
        raise HTTPException(500, f"Failed to join lobby: {str(e)}")

@app.get("/lobbies")
async def list_lobbies():
    try:
        result = [{
            "lobby_id": str(lobby["id"]),
            "name": lobby["name"],
            "current_players": len(lobby["users"]),
            "max_humans": lobby["max_humans"],
            "is_private": lobby["is_private"],
            "invite_code": lobby["invite_code"]
        } for lobby in lobbies.values()]
        
        return result
    except Exception as e:
        logger.error(f"List lobbies error: {e}")
        raise HTTPException(500, f"Failed to list lobbies: {str(e)}")

@app.post("/lobbies/{lobby_id}/add-bot")
async def add_bot_to_lobby(lobby_id: UUID, req: AddBotRequest):
    try:
        if lobby_id not in lobbies:
            raise HTTPException(404, "Lobby not found")
        
        bot_name = req.bot_name if req.bot_name in AI_BOTS else "ChatBot"
        
        if lobby_id not in lobby_bots:
            lobby_bots[lobby_id] = []
        
        if bot_name not in lobby_bots[lobby_id]:
            lobby_bots[lobby_id].append(bot_name)
            
            join_message = {
                "username": "system",
                "message": f"🤖 {bot_name} has joined the chat!",
                "type": "system"
            }
            await broadcast(lobby_id, join_message)
            
        return {"message": f"{bot_name} added to lobby"}
    except Exception as e:
        logger.error(f"Add bot error: {e}")
        raise HTTPException(500, f"Failed to add bot: {str(e)}")

@app.post("/lobbies/{lobby_id}/trivia-answer")
async def submit_trivia_answer(lobby_id: UUID, req: TriviaAnswerRequest):
    try:
        if lobby_id not in lobby_trivia_active or not lobby_trivia_active[lobby_id]:
            raise HTTPException(400, "No active trivia")
            
        username = get_username(req.user_id)
        
        if lobby_id not in lobby_trivia_answers:
            lobby_trivia_answers[lobby_id] = {}
            
        lobby_trivia_answers[lobby_id][username] = req.answer
        
        answer_message = {
            "username": "system",
            "message": f"{username} submitted their answer! ✅",
            "type": "system"
        }
        await broadcast(lobby_id, answer_message)
        
        return {"message": "Answer submitted"}
        
    except Exception as e:
        logger.error(f"Trivia answer error: {e}")
        raise HTTPException(500, f"Failed to submit answer: {str(e)}")

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "users_count": len(users),
        "lobbies_count": len(lobbies),
        "active_connections": sum(len(conns) for conns in connections.values())
    }

@app.websocket("/ws/{lobby_id}/{user_id}")
async def websocket_endpoint(websocket: WebSocket, lobby_id: UUID, user_id: str):
    await websocket.accept()
    
    try:
        username = get_username(user_id)
    except HTTPException:
        await websocket.close(code=1008, reason="User not found")
        return
    
    if lobby_id not in lobbies:
        await websocket.close(code=1008, reason="Lobby not found")
        return
    
    if lobby_id not in connections:
        connections[lobby_id] = []
    connections[lobby_id].append(websocket)
    
    if lobby_id not in active_users:
        active_users[lobby_id] = set()
    
    was_empty = len(active_users[lobby_id]) == 0
    active_users[lobby_id].add(username)
    
    await send_lobby_info(lobby_id, websocket)
    
    if not was_empty:
        join_message = {
            "username": "system",
            "message": f"{username} joined the chat.",
            "type": "system"
        }
        await broadcast(lobby_id, join_message)

    try:
        while True:
            data = await websocket.receive_json()
            message_text = data.get("message", "").strip()
            
            if message_text:
                user_message = {
                    "username": username,
                    "message": message_text,
                    "type": "user"
                }
                await broadcast(lobby_id, user_message)
                
                # Trigger game events
                asyncio.create_task(check_trivia_trigger(lobby_id))
                asyncio.create_task(trigger_bot_response(lobby_id, message_text, username))
                
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        if lobby_id in connections and websocket in connections[lobby_id]:
            connections[lobby_id].remove(websocket)
        
        if lobby_id in active_users and username in active_users[lobby_id]:
            active_users[lobby_id].remove(username)
        
        if lobby_id in active_users and len(active_users[lobby_id]) > 0:
            leave_message = {
                "username": "system",
                "message": f"{username} left the chat.",
                "type": "system"
            }
            await broadcast(lobby_id, leave_message)

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 8000))
    print(f"Starting server on 0.0.0.0:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
