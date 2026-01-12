import os
import uvicorn
from fastapi import FastAPI, Form, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import google.generativeai as genai
from twilio.twiml.messaging_response import MessagingResponse

# --- 1. CONFIGURACIÓN ---
load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise ValueError("❌ FALTA LA API KEY EN .ENV")

genai.configure(api_key=API_KEY)

# INSTRUCCIONES DEL EXPERTO (Prompt de Venta)
INSTRUCCIONES = """
Eres el Asistente Virtual de "Constructora Lautaro" (Tech by SanTec).
OBJETIVO: Atender clientes por Web y WhatsApp, dar precios referenciales y conseguir visitas.

REGLAS:
1. Responde preguntas sobre construcción, materiales y la empresa.
2. PRECIOS (Solo si preguntan):
   - Cemento Avellaneda (50kg): $9.500
   - Ladrillo Hueco 12x18x33: $550 c/u
   - Arena (Bolson): $35.000
3. Si piden presupuesto de obra completa: "Necesitamos ver el terreno. ¿Te agendo una visita técnica?".
4. Respuestas cortas, profesionales y serviciales (Máx 2 oraciones).
5. No uses markdown (negritas, cursivas) porque en WhatsApp a veces se rompe.
"""

model = genai.GenerativeModel(
    'models/gemini-2.5-flash',
    system_instruction=INSTRUCCIONES
)

app = FastAPI()

# Permisos para la Web
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- MEMORIA VOLÁTIL (RAM) ---
# Diccionario simple: { "cliente_id": [historial_gemini] }
sesiones_activas = {}

def obtener_respuesta_gemini(client_id, mensaje_usuario):
    """Función auxiliar para manejar la lógica de Gemini"""
    try:
        # 1. Recuperar o iniciar historial
        if client_id not in sesiones_activas:
            sesiones_activas[client_id] = []
        
        historial_actual = sesiones_activas[client_id]

        # 2. Iniciar chat
        chat = model.start_chat(history=historial_actual)
        
        # 3. Enviar mensaje
        response = chat.send_message(mensaje_usuario)
        bot_reply = response.text
        
        # 4. Guardar historial actualizado en RAM
        sesiones_activas[client_id] = chat.history
        
        return bot_reply
    except Exception as e:
        print(f"❌ Error Gemini: {e}")
        return "Disculpá, tuve un error técnico momentáneo. ¿Podés repetir?"

# --- ENDPOINT 1: WEB (JSON) ---
class MessageInput(BaseModel):
    user_message: str
    client_id: str

@app.post("/chat")
def chat_web(input_data: MessageInput):
    cid = input_data.client_id
    msg = input_data.user_message
    print(f"🌐 WEB ({cid}): {msg}")
    
    respuesta = obtener_respuesta_gemini(cid, msg)
    print(f"🤖 SanTec Web: {respuesta}")
    
    return {"response": respuesta}

# --- ENDPOINT 2: WHATSAPP (Twilio XML) ---
@app.post("/whatsapp")
async def chat_whatsapp(Body: str = Form(...), From: str = Form(...)):
    # 'From' viene como 'whatsapp:+549...', lo usamos de ID
    msg = Body
    cid = From
    print(f"📲 WSP ({cid}): {msg}")

    # Obtenemos la respuesta de la IA
    bot_reply = obtener_respuesta_gemini(cid, msg)
    print(f"🤖 SanTec WSP: {bot_reply}")

    # Generamos XML para Twilio
    twiml_resp = MessagingResponse()
    twiml_resp.message(bot_reply)
    
    return Response(content=str(twiml_resp), media_type="application/xml")

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)