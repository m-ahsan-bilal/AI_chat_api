from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Set
import uuid
from uuid import UUID

app = FastAPI(
    title="Trivia Game API",
    version="3.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- In-memory Data Stores ---
users: Dict[str, dict] = {}                   # username -> {user_id}
lobbies: Dict[UUID, dict] = {}                # lobby_id -> lobby info
connections: Dict[UUID, List[WebSocket]] = {} # lobby_id -> WebSocket connections
active_users: Dict[UUID, Set[str]] = {}       # lobby_id -> active usernames
lobby_creators: Dict[UUID, str] = {}          # lobby_id -> creator username

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

class CreateLobbyResponse(BaseModel):
    lobby_id: UUID
    invite_code: str

class JoinLobbyRequest(BaseModel):
    invite_code: str
    user_id: str

class LeaveLobbyRequest(BaseModel):
    lobby_id: UUID
    user_id: str

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
    """Send initial lobby information to a new connection"""
    if lobby_id not in lobbies:
        return
    
    lobby = lobbies[lobby_id]
    creator = lobby_creators.get(lobby_id, "Unknown")
    
    # Send lobby creation message
    creation_message = {
        "username": "system",
        "message": f"Welcome to '{lobby['name']}'! This lobby was created by {creator}.",
        "type": "system"
    }
    
    try:
        await websocket.send_json(creation_message)
    except:
        pass
    
    # Send current active users if any
    if lobby_id in active_users and active_users[lobby_id]:
        active_list = list(active_users[lobby_id])
        if len(active_list) > 1:  # Don't show if only the current user
            users_message = {
                "username": "system",
                "message": f"Currently active: {', '.join(active_list)}",
                "type": "system"
            }
            try:
                await websocket.send_json(users_message)
            except:
                pass

# --- User Registration ---
@app.post("/register", response_model=RegisterResponse)
def register(req: RegisterRequest):
    if req.username in users:
        raise HTTPException(400, "Username already taken.")
    
    user_id = str(uuid.uuid4())
    users[req.username] = {"user_id": user_id}
    return RegisterResponse(user_id=user_id)

# --- Lobby Management (HTTP) ---
@app.post("/lobbies")
def create_lobby(req: CreateLobbyRequest):
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
    
    # Initialize active users for this lobby
    active_users[lobby_id] = set()
    
    return {
        "lobby_id": str(lobby_id),
        "invite_code": invite_code,
        "name": req.name
    }

@app.post("/lobbies/join-invite")
def join_lobby(req: JoinLobbyRequest):
    lobby = find_lobby_by_invite(req.invite_code)
    username = get_username(req.user_id)
    
    if username in lobby["users"]:
        raise HTTPException(400, "User already in lobby.")
    
    if len(lobby["users"]) >= lobby["max_humans"]:
        raise HTTPException(400, "Lobby is full.")
    
    lobby["users"].append(username)
    
    # Find lobby_id for this lobby
    lobby_id = None
    for lid, lob in lobbies.items():
        if lob == lobby:
            lobby_id = lid
            break
    
    # Store creator information if this is the first user
    if lobby_id and len(lobby["users"]) == 1:
        lobby_creators[lobby_id] = username
    
    return {"message": f"{username} joined the lobby."}

@app.post("/lobbies/leave")
def leave_lobby(req: LeaveLobbyRequest):
    lobby = lobbies.get(req.lobby_id)
    if not lobby:
        raise HTTPException(404, "Lobby not found.")
    
    username = get_username(req.user_id)
    
    if username in lobby["users"]:
        lobby["users"].remove(username)
        return {"message": f"{username} left the lobby."}
    else:
        raise HTTPException(400, "User not in lobby.")

@app.get("/lobbies")
def list_lobbies():
    return [{
        "lobby_id": str(lobby["id"]),
        "name": lobby["name"],
        "current_players": len(lobby["users"]),
        "max_humans": lobby["max_humans"],
        "is_private": lobby["is_private"],
        "invite_code": lobby["invite_code"]
    } for lobby in lobbies.values()]

@app.get("/lobbies/public")
def list_public_lobbies():
    return [{
        "lobby_id": str(lobby["id"]),
        "name": lobby["name"],
        "current_players": len(lobby["users"]),
        "max_humans": lobby["max_humans"],
        "invite_code": lobby["invite_code"]
    } for lobby in lobbies.values() if not lobby["is_private"]]

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "users_count": len(users),
        "lobbies_count": len(lobbies),
        "active_connections": sum(len(conns) for conns in connections.values())
    }

# --- WebSocket: Real-time Lobby Chat ---
@app.websocket("/ws/{lobby_id}/{user_id}")
async def websocket_endpoint(websocket: WebSocket, lobby_id: UUID, user_id: str):
    await websocket.accept()
    
    try:
        username = get_username(user_id)
    except HTTPException:
        await websocket.close(code=1008, reason="User not found")
        return
    
    # Check if lobby exists
    if lobby_id not in lobbies:
        await websocket.close(code=1008, reason="Lobby not found")
        return
    
    if lobby_id not in connections:
        connections[lobby_id] = []
    connections[lobby_id].append(websocket)
    
    # Add user to active users
    if lobby_id not in active_users:
        active_users[lobby_id] = set()
    
    was_empty = len(active_users[lobby_id]) == 0
    active_users[lobby_id].add(username)
    
    # Send initial lobby info to the new user
    await send_lobby_info(lobby_id, websocket)
    
    # Only broadcast join message if there were already active users
    if not was_empty:
        join_message = {
            "username": "system",
            "message": f"{username} joined the chat.",
            "type": "system"
        }
        await broadcast(lobby_id, join_message)
    
    # Broadcast updated active users count
    active_count = len(active_users[lobby_id])
    if active_count > 1:
        count_message = {
            "username": "system",
            "message": f"{active_count} users currently active in this lobby.",
            "type": "system"
        }
        await broadcast(lobby_id, count_message)

    try:
        while True:
            data = await websocket.receive_json()
            user_message = {
                "username": username,
                "message": data.get("message", ""),
                "type": "user"
            }
            await broadcast(lobby_id, user_message)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        # Cleanup
        if lobby_id in connections and websocket in connections[lobby_id]:
            connections[lobby_id].remove(websocket)
        
        # Remove user from active users
        if lobby_id in active_users and username in active_users[lobby_id]:
            active_users[lobby_id].remove(username)
        
        # Only broadcast leave message if there are still active users
        if lobby_id in active_users and len(active_users[lobby_id]) > 0:
            leave_message = {
                "username": "system",
                "message": f"{username} left the chat.",
                "type": "system"
            }
            await broadcast(lobby_id, leave_message)
            
            # Broadcast updated active users count
            active_count = len(active_users[lobby_id])
            if active_count > 0:
                count_message = {
                    "username": "system",
                    "message": f"{active_count} users currently active in this lobby.",
                    "type": "system"
                }
                await broadcast(lobby_id, count_message)

if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
