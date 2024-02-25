from fastapi import FastAPI, WebSocket, HTTPException
from typing import List
from pydantic import BaseModel
import httpx
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from supabase_py import create_client, Client
from fastapi.websockets import WebSocketDisconnect
from typing import Dict

app = FastAPI()

SUPABASE_URL = "https://zwrwcaxpczcdnobaveqs.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inp3cndjYXhwY3pjZG5vYmF2ZXFzIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTcwNzk4NjI3OSwiZXhwIjoyMDIzNTYyMjc5fQ.4a1AOfnqiUMgj03tSb1N-No6e-i9h8A-i3kF2knAJxU"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

connected_users = {}

class Usuario(BaseModel):
    id: int
    nombre: str
    email: str

class Mensaje(BaseModel):
    id_usuario_emisor: int
    id_usuario_receptor: int
    texto: str
    leido: bool
    estado: str


origins = [
    "http://localhost",
    "http://localhost:8000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


html= """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>WebSocket Chat</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            background-color: #f4f4f4;
            margin: 0;
            padding: 0;
        }
        #container {
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
        }
        label {
            font-weight: bold;
            margin-right: 10px;
            display: block;
        }
        input[type="text"], button {
            padding: 8px;
            font-size: 16px;
            border-radius: 5px;
            border: 1px solid #ccc;
            margin-bottom: 10px;
            width: calc(100% - 22px);
        }
        button {
            background-color: #007bff;
            color: #fff;
            border: none;
            cursor: pointer;
        }
        button:hover {
            background-color: #0056b3;
        }
        #chat-container {
            margin-top: 20px;
        }
        #message-container {
            max-height: 200px;
            overflow-y: auto;
            border: 1px solid #ccc;
            border-radius: 5px;
            padding: 10px;
            background-color: #fff;
            margin-bottom: 10px;
        }
        #message {
            width: calc(100% - 76px);
            margin-right: 10px;
        }
    </style>
</head>
<body>
    <div id="container">
        <div id="connection-container">
            <label for="user-id">Enter your user ID:</label>
            <input type="text" id="user-id">
            
            <label for="user-id2">Enter the user ID of the person you want to message:</label>
            <input type="text" id="user-id2">
            
            <button onclick="connect()">Connect</button>
        </div>

        <div id="chat-container" style="display: none;">
            <div id="message-container"></div>
            <input type="text" id="message" placeholder="Enter message">
            <button onclick="sendMessage()">Send</button>
        </div>
    </div>

    <script>
        var socket;

        function connect() {
            var userId = document.getElementById("user-id").value;
            var userId2 = document.getElementById("user-id2").value || 1; // Default value if not provided
            socket = new WebSocket('ws://localhost:8000/ws/' + userId + '/' + userId2);
            socket.onopen = function(event) {
                console.log("WebSocket connected.");
                document.getElementById("chat-container").style.display = "block";
            };
            socket.onmessage = function(event) {
                console.log("Message received:", event.data);
                displayMessage(event.data);
            };
        }

        function sendMessage() {
            var message = document.getElementById("message").value;
            socket.send(message);
            document.getElementById("message").value = '';
        }

        function displayMessage(message) {
            var messageElement = document.createElement("div");
            messageElement.textContent = message;
            document.getElementById("message-container").appendChild(messageElement);
        }
    </script>
</body>
</html>



"""

async def get_supabase_client():
    if not hasattr(get_supabase_client, "_client") or get_supabase_client._client.is_closed:
        get_supabase_client._client = httpx.AsyncClient()
    return get_supabase_client._client

async def close_supabase_client():
    if hasattr(get_supabase_client, "_client") and not get_supabase_client._client.is_closed:
        await get_supabase_client._client.aclose()

async def insert_message(message: Mensaje):
    client = await get_supabase_client()
    url = f"{SUPABASE_URL}/rest/v1/mensaje"
    headers = {
        "apikey": SUPABASE_KEY,
        "Content-Type": "application/json",
    }
    data = {
        "id_usuario_emisor": message.id_usuario_emisor,
        "id_usuario_receptor": message.id_usuario_receptor,
        "texto": message.texto,
        "leido": message.leido,
        "estado": message.estado
    }
    try:
        response = await client.post(url, headers=headers, json=data)
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.json())
    except httpx.RequestError as e:
        raise HTTPException(status_code=500, detail="Error de conexión con el servidor Supabase")
    return response

async def get_messages(id_usuario: int) -> List[Mensaje]:
    client = await get_supabase_client()
    url = f"{SUPABASE_URL}/rest/v1/mensaje?select=id,id_usuario_emisor,id_usuario_receptor,texto,fecha_envio,leido,estado&or=(id_usuario_emisor.eq.{id_usuario},id_usuario_receptor.eq.{id_usuario})"
    headers = {
        "apikey": SUPABASE_KEY,
        "Content-Type": "application/json",
    }
    try:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        messages = response.json()
        return [Mensaje(**message) for message in messages]
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.json())
    except httpx.RequestError as e:
        raise HTTPException(status_code=500, detail="Error de conexión con el servidor Supabase")
    
    
class ConnectionManager:
    #initialize list for websockets connections
    def __init__(self):
        self.active_connections: List[WebSocket] = []
 
    #accept and append the connection to the list
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
 
    #remove the connection from list
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
 
    #send personal message to the connection
    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)
         
    #send message to the list of connections
    async def broadcast(self, message: str, websocket: WebSocket):
        for connection in self.active_connections:
            if(connection == websocket):
                continue
            await connection.send_text(message)

connectionmanager = ConnectionManager()

@app.websocket("/ws/{id_usuario}/{id_usuario2}")
async def websocket_endpoint(websocket: WebSocket, id_usuario: int, id_usuario2: int ):

    await connectionmanager.connect(websocket)
    connected_users[id_usuario] = websocket
    print(connected_users)

    mensajes = await get_messages(id_usuario)
    
    for mensaje in mensajes:
        await connectionmanager.send_personal_message(f"Usuario {mensaje.id_usuario_emisor} : {mensaje.texto}", websocket)

    try:
        while True:
            data = await websocket.receive_text()
            await connectionmanager.send_personal_message(f"You : {data}", websocket)
            await connectionmanager.broadcast(f"Usuario {id_usuario}: {data}", websocket)
            mensaje = Mensaje(id_usuario_emisor=id_usuario, id_usuario_receptor=id_usuario2, texto=data, leido=False, estado="enviado")
            print(mensaje)
            await insert_message(mensaje)
             
    except WebSocketDisconnect:
        connectionmanager.disconnect(websocket)
        await connectionmanager.broadcast(f"Usuario {id_usuario} left the chat")
        

@app.get("/")
async def get():
    return HTMLResponse(html)
