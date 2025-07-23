# from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
# from pydantic import BaseModel
# from typing import Dict, List
# import uuid
# from uuid import UUID

# app = FastAPI(
#     title="Trivia Game API",
#     version="3.0.0"
# )

# # --- In-memory Data Stores ---
# users: Dict[str, dict] = {}                   # username -> {user_id}
# lobbies: Dict[UUID, dict] = {}                # lobby_id -> lobby info
# connections: Dict[UUID, List[WebSocket]] = {} # lobby_id -> WebSocket connections
# chat_history: Dict[UUID, List[Dict]] = {}     # lobby_id -> chat messages

# # --- Models ---
# class RegisterRequest(BaseModel):
#     username: str

# class RegisterResponse(BaseModel):
#     user_id: str

# class CreateLobbyRequest(BaseModel):
#     name: str
#     max_humans: int = 5
#     max_bots: int = 0
#     is_private: bool = False

# class CreateLobbyResponse(BaseModel):
#     lobby_id: UUID
#     invite_code: str

# class JoinLobbyRequest(BaseModel):
#     invite_code: str
#     user_id: str

# class LeaveLobbyRequest(BaseModel):
#     lobby_id: UUID
#     user_id: str

# # --- Helper Functions ---
# def generate_invite_code():
#     return str(uuid.uuid4())[:6]

# def find_lobby_by_invite(invite_code: str):
#     for lobby_id, lobby in lobbies.items():
#         if lobby["invite_code"] == invite_code:
#             return lobby
#     raise HTTPException(404, "Lobby not found.")

# def get_username(user_id: str):
#     for username, data in users.items():
#         if data["user_id"] == user_id:
#             return username
#     raise HTTPException(404, "User not found.")

# async def broadcast(lobby_id: UUID, message: dict):
#     for ws in connections.get(lobby_id, []):
#         await ws.send_json(message)

# # --- User Registration ---
# @app.post("/register", response_model=RegisterResponse)
# def register(req: RegisterRequest):
#     if req.username in users:
#         raise HTTPException(400, "Username already taken.")
    
#     user_id = str(uuid.uuid4())
#     users[req.username] = {"user_id": user_id}
#     return RegisterResponse(user_id=user_id)

# # --- Lobby Management (HTTP) ---
# @app.post("/lobbies")
# def create_lobby(req: CreateLobbyRequest):
#     lobby_id = uuid.uuid4()
#     invite_code = generate_invite_code()
#     lobbies[lobby_id] = {
#         "id": lobby_id,
#         "name": req.name,
#         "max_humans": req.max_humans,
#         "max_bots": req.max_bots,
#         "is_private": req.is_private,
#         "users": [],
#         "invite_code": invite_code
#     }
#     chat_history[lobby_id] = [{
#         "username": "system",
#         "message": f"Lobby '{req.name}' created.",
#         "type": "system"
#     }]
#     return {
#         "lobby_id": str(lobby_id),
#         "invite_code": invite_code,
#         "name": req.name
#     }

# @app.post("/lobbies/join-invite")
# def join_lobby(req: JoinLobbyRequest):
#     lobby = find_lobby_by_invite(req.invite_code)
#     username = get_username(req.user_id)
    
#     if username in lobby["users"]:
#         raise HTTPException(400, "User already in lobby.")
    
#     if len(lobby["users"]) >= lobby["max_humans"]:
#         raise HTTPException(400, "Lobby is full.")
    
#     lobby["users"].append(username)
#     return {"message": f"{username} joined the lobby."}

# @app.post("/lobbies/leave")
# def leave_lobby(req: LeaveLobbyRequest):
#     lobby = lobbies.get(req.lobby_id)
#     username = get_username(req.user_id)
    
#     if not lobby:
#         raise HTTPException(404, "Lobby not found.")
    
#     if username in lobby["users"]:
#         lobby["users"].remove(username)
#         return {"message": f"{username} left the lobby."}
#     else:
#         raise HTTPException(400, "User not in lobby.")

# @app.get("/lobbies")
# def list_lobbies():
#     return [{
#         "lobby_id": str(lobby["id"]),
#         "name": lobby["name"],
#         "current_players": len(lobby["users"]),
#         "max_humans": lobby["max_humans"],
#         "is_private": lobby["is_private"],
#         "invite_code": lobby["invite_code"]
#     } for lobby in lobbies.values()]

# @app.get("/lobbies/public")
# def list_public_lobbies():
#     return [{
#         "lobby_id": str(lobby["id"]),
#         "name": lobby["name"],
#         "current_players": len(lobby["users"]),
#         "max_humans": lobby["max_humans"],
#         "invite_code": lobby["invite_code"]
#     } for lobby in lobbies.values() if not lobby["is_private"]]

# # --- WebSocket: Real-time Lobby Chat ---
# @app.websocket("/ws/{lobby_id}/{user_id}")
# async def websocket_endpoint(websocket: WebSocket, lobby_id: UUID, user_id: str):
#     await websocket.accept()
    
#     username = get_username(user_id)
    
#     if lobby_id not in connections:
#         connections[lobby_id] = []
#     connections[lobby_id].append(websocket)
    
#     # Send only system messages to new user
#     for msg in chat_history.get(lobby_id, []):
#         if msg['type'] == "system":
#             await websocket.send_json(msg)
    
#     # Notify others of new join
#     join_message = {
#         "username": "system",
#         "message": f"{username} joined the chat.",
#         "type": "system"
#     }
#     chat_history[lobby_id].append(join_message)
#     await broadcast(lobby_id, join_message)
    
#     # Broadcast lobby user list
#     await broadcast(lobby_id, {
#         "username": "system",
#         "message": f"Players in lobby: {', '.join(lobbies[lobby_id]['users'])}",
#         "type": "system"
#     })

#     try:
#         while True:
#             data = await websocket.receive_json()
#             user_message = {
#                 "username": username,
#                 "message": data.get("message"),
#                 "type": "user"
#             }
#             chat_history[lobby_id].append(user_message)
#             await broadcast(lobby_id, user_message)
#     except WebSocketDisconnect:
#         connections[lobby_id].remove(websocket)
        
#         # Remove user from lobby
#         if username in lobbies[lobby_id]["users"]:
#             lobbies[lobby_id]["users"].remove(username)
        
#         leave_message = {
#             "username": "system",
#             "message": f"{username} left the chat.",
#             "type": "system"
#         }
#         chat_history[lobby_id].append(leave_message)
#         await broadcast(lobby_id, leave_message)
        
#         # Broadcast updated player list
#         await broadcast(lobby_id, {
#             "username": "system",
#             "message": f"Players in lobby: {', '.join(lobbies[lobby_id]['users'])}",
#             "type": "system"
#         })
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware  # Add this import
from pydantic import BaseModel
from typing import Dict, List
import uuid
from uuid import UUID

app = FastAPI(
    title="Trivia Game API",
    version="3.0.0"
)

# Add CORS middleware - THIS IS CRUCIAL FOR WEB TESTING
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- In-memory Data Stores ---
users: Dict[str, dict] = {}                   # username -> {user_id}
lobbies: Dict[UUID, dict] = {}                # lobby_id -> lobby info
connections: Dict[UUID, List[WebSocket]] = {} # lobby_id -> WebSocket connections
chat_history: Dict[UUID, List[Dict]] = {}     # lobby_id -> chat messages

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
        for ws in connections[lobby_id][:]:  # Create a copy to avoid modification during iteration
            try:
                await ws.send_json(message)
            except:
                # Remove dead connections
                connections[lobby_id].remove(ws)

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
        "created_at": str(uuid.uuid4())  # Add timestamp-like field
    }
    chat_history[lobby_id] = [{
        "username": "system",
        "message": f"Lobby '{req.name}' created.",
        "type": "system"
    }]
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

# Add a simple health check endpoint
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
    
    # Send chat history to new user (only system messages initially)
    for msg in chat_history.get(lobby_id, []):
        if msg['type'] == "system":
            try:
                await websocket.send_json(msg)
            except:
                break
    
    # Notify others of new join
    join_message = {
        "username": "system",
        "message": f"{username} joined the chat.",
        "type": "system"
    }
    if lobby_id not in chat_history:
        chat_history[lobby_id] = []
    chat_history[lobby_id].append(join_message)
    await broadcast(lobby_id, join_message)
    
    # Broadcast lobby user list
    user_list_message = {
        "username": "system",
        "message": f"Players in lobby: {', '.join(lobbies[lobby_id]['users'])}",
        "type": "system"
    }
    await broadcast(lobby_id, user_list_message)

    try:
        while True:
            data = await websocket.receive_json()
            user_message = {
                "username": username,
                "message": data.get("message", ""),
                "type": "user"
            }
            chat_history[lobby_id].append(user_message)
            await broadcast(lobby_id, user_message)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        # Cleanup
        if lobby_id in connections and websocket in connections[lobby_id]:
            connections[lobby_id].remove(websocket)
        
        # Remove user from lobby
        if lobby_id in lobbies and username in lobbies[lobby_id]["users"]:
            lobbies[lobby_id]["users"].remove(username)
        
        leave_message = {
            "username": "system",
            "message": f"{username} left the chat.",
            "type": "system"
        }
        if lobby_id in chat_history:
            chat_history[lobby_id].append(leave_message)
        await broadcast(lobby_id, leave_message)
        
        # Broadcast updated player list
        if lobby_id in lobbies:
            updated_list_message = {
                "username": "system",
                "message": f"Players in lobby: {', '.join(lobbies[lobby_id]['users'])}",
                "type": "system"
            }
            await broadcast(lobby_id, updated_list_message)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)