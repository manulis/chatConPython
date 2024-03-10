from fastapi import FastAPI, WebSocket, HTTPException
from typing import List
from pydantic import BaseModel
import httpx
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from supabase_py import create_client, Client
from fastapi.websockets import WebSocketDisconnect

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

#Obtener Cliente de supabase
async def get_supabase_client():
    if not hasattr(get_supabase_client, "_client") or get_supabase_client._client.is_closed:
        get_supabase_client._client = httpx.AsyncClient()
    return get_supabase_client._client


#Insertar mensaje en la BD
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


#Extraer mensajes de la BD
async def get_messages(id_usuario: int, id_usuario2: int) -> List[Mensaje]:
    client = await get_supabase_client()
    url = f"{SUPABASE_URL}/rest/v1/mensaje?select=id,id_usuario_emisor,id_usuario_receptor,texto,fecha_envio,leido,estado&or=(and(id_usuario_emisor.eq.{id_usuario}, id_usuario_receptor.eq.{id_usuario2}), and(id_usuario_emisor.eq.{id_usuario2}, id_usuario_receptor.eq.{id_usuario}))"
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
    
    

#Manejo de conexiones activas
class ConnectionManager:
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []
 
   
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
 

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
 
  
    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)
         
  
    async def broadcast(self, message: str, websocket: WebSocket):
        for connection in self.active_connections:
            if(connection == websocket):
                continue
            await connection.send_text(message)

connectionmanager = ConnectionManager()


#Conexion a websocket
@app.websocket("/ws/{Nombre1}/{Nombre2}")
async def websocket_endpoint(websocket: WebSocket, Nombre1: str, Nombre2: str ):

    await connectionmanager.connect(websocket)

    Response1 = supabase.table("usuario").select("id").eq("nombre", Nombre1).execute()
    Response2 = supabase.table("usuario").select("id").eq("nombre", Nombre2).execute()

    id_usuario = Response1['data'][0]['id']
    id_usuario2 = Response2['data'][0]['id']

    connected_users[id_usuario] = websocket

    print(connected_users)

    mensajes = await get_messages(id_usuario, id_usuario2)
    
    for mensaje in mensajes:
        if(mensaje.id_usuario_emisor == id_usuario):
            await connectionmanager.send_personal_message(f"You  : {mensaje.texto}", websocket)
        else:
            await connectionmanager.send_personal_message(f" {Nombre2} : {mensaje.texto}", websocket)

    try:
        while True:
            data = await websocket.receive_text()
            await connectionmanager.send_personal_message(f"You  : {data}", websocket)
            await connectionmanager.broadcast(f"{Nombre1}: {data}", websocket)
            mensaje = Mensaje(id_usuario_emisor=id_usuario, id_usuario_receptor=id_usuario2, texto=data, leido=False, estado="enviado")
            print(mensaje)
            await insert_message(mensaje)
             
    except WebSocketDisconnect:
        connectionmanager.disconnect(websocket)
        await connectionmanager.broadcast(f"User {id_usuario} left the chat")
        
#Retornar html con el front de la app
@app.get("/")
async def get():
    with open("front.html", "r") as file:
        html_content = file.read()
    return HTMLResponse(content=html_content)
