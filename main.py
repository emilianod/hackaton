from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.responses import JSONResponse, HTMLResponse
import face_recognition
import json
import numpy as np
import os
import io
import httpx
import base64
from contextlib import asynccontextmanager
import logging
from typing import List, Optional
from pathlib import Path

# Configurar logging básico para que sea más detallado
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s'
)

# --- Configuración ---
RUTA_DB = 'db/database.json'
RUTA_IMAGENES_CONOCIDAS = 'known_faces'
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "https://n8n.supervis.ar/webhook-test/e641ceb9-838c-4df7-a3e0-c493ec6b69e8") # Obtener de variable de entorno o usar placeholder

# Cargar la base de datos una vez al inicio de la aplicación
codificaciones_conocidas = []
nombres_conocidos = []
info_personas = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.info("Iniciando aplicación y preparando directorios...")
    try:
        # Asegurarse de que el directorio de imágenes conocidas existe
        if not os.path.exists(RUTA_IMAGENES_CONOCIDAS):
            os.makedirs(RUTA_IMAGENES_CONOCIDAS)
            logging.warning(f"Directorio '{RUTA_IMAGENES_CONOCIDAS}' creado. Por favor, añade las imágenes de las personas conocidas.")
        
        # Asegurarse de que el directorio de la base de datos existe
        db_dir = os.path.dirname(RUTA_DB)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir)
            logging.info(f"Directorio '{db_dir}' creado.")

        logging.info("Cargando base de datos de rostros conocidos...")
        actualizar_base_de_datos_en_memoria()
        if not codificaciones_conocidas:
            logging.warning("Advertencia: No se cargaron rostros conocidos. La base de datos está vacía o las imágenes no han sido procesadas.")
        else:
            logging.info(f"Base de datos cargada con {len(nombres_conocidos)} rostros conocidos.")
    except Exception as e:
        logging.error("Error crítico al cargar la base de datos durante el inicio.", exc_info=True)
    yield
    logging.info("La aplicación se ha detenido.")

app = FastAPI(lifespan=lifespan)

def cargar_base_de_datos(ruta_db, ruta_imagenes):
    _codificaciones_conocidas = []
    _nombres_conocidos = []
    _info_personas = {}

    db_dir = os.path.dirname(ruta_db)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir)
        logging.info(f"Directorio de base de datos '{db_dir}' creado.")

    if not os.path.exists(ruta_db):
        logging.warning(f"El archivo de base de datos '{ruta_db}' no existe. Se creará uno nuevo al registrar la primera persona.")
        return _codificaciones_conocidas, _nombres_conocidos, _info_personas

    try:
        with open(ruta_db, 'r', encoding='utf-8') as f:
            db = json.load(f)
    except json.JSONDecodeError:
        logging.warning(f"El archivo de base de datos '{ruta_db}' está vacío o mal formado. Se tratará como una base de datos vacía.")
        return _codificaciones_conocidas, _nombres_conocidos, _info_personas
    except FileNotFoundError:
        logging.warning(f"El archivo de base de datos '{ruta_db}' no fue encontrado. Se creará al registrar una nueva persona.")
        return _codificaciones_conocidas, _nombres_conocidos, _info_personas


    for persona in db:
        nombre = persona.get('nombre', 'Sin Nombre')
        _info_personas[nombre] = {
            'peligroso': persona.get('peligroso', False),
            'dni': persona.get('dni'),
            'domicilio': persona.get('domicilio'),
            'correo_electronico': persona.get('correo_electronico'),
            'celular': persona.get('celular'),
            'a_notificar': persona.get('a_notificar')
        }
        if 'face_encodings' in persona and persona['face_encodings']:
            for encoding_list in persona['face_encodings']:
                _codificaciones_conocidas.append(np.array(encoding_list))
                _nombres_conocidos.append(nombre)
        else:
            logging.warning(f"No se encontraron codificaciones faciales para '{nombre}' en la base de datos.")

    return _codificaciones_conocidas, _nombres_conocidos, _info_personas

def actualizar_base_de_datos_en_memoria():
    logging.info("Intentando actualizar la base de datos en memoria...")
    global codificaciones_conocidas, nombres_conocidos, info_personas
    codificaciones_conocidas, nombres_conocidos, info_personas = cargar_base_de_datos(RUTA_DB, RUTA_IMAGENES_CONOCIDAS)
    logging.info(f"Base de datos en memoria actualizada. {len(nombres_conocidos)} rostros cargados.")

def reconocer_rostros(imagen_np, codificaciones_conocidas, nombres_conocidos, info_personas):
    logging.info("Iniciando reconocimiento de rostros en la imagen proporcionada.")
    ubicaciones_rostros = face_recognition.face_locations(imagen_np)
    codificaciones_rostros = face_recognition.face_encodings(imagen_np, ubicaciones_rostros)
    logging.info(f"Se encontraron {len(ubicaciones_rostros)} rostro(s) en la imagen.")

    resultados = []
    for codificacion_rostro in codificaciones_rostros:
        coincidencias = face_recognition.compare_faces(codificaciones_conocidas, codificacion_rostro)
        distancia_rostro = face_recognition.face_distance(codificaciones_conocidas, codificacion_rostro)
        
        nombre_detectado = "Desconocido"
        es_peligroso = False
        numero_a_notificar = None

        if True in coincidencias:
            mejor_coincidencia_idx = np.argmin(distancia_rostro)
            if distancia_rostro[mejor_coincidencia_idx] < 0.6: # Umbral de confianza
                nombre_detectado = nombres_conocidos[mejor_coincidencia_idx]
                info = info_personas.get(nombre_detectado, {})
                es_peligroso = info.get('peligroso', False)
                numero_a_notificar = info.get('a_notificar')
                logging.info(f"Rostro reconocido: {nombre_detectado} (Peligroso: {es_peligroso})")
            else:
                logging.info("Se encontró una coincidencia, pero la distancia es muy alta. Se considera 'Desconocido'.")

        resultados.append({
            "nombre": nombre_detectado,
            "peligroso": es_peligroso,
            "a_notificar": numero_a_notificar
        })
    return resultados

async def enviar_a_n8n(data, numero_a_notificar=None):
    if not N8N_WEBHOOK_URL or "e641ceb9-838c-4df7-a3e0-c493ec6b69e8" in N8N_WEBHOOK_URL:
        logging.warning("N8N_WEBHOOK_URL no está configurado o sigue siendo el de prueba. No se enviarán datos a n8n.")
        return {"status": "skipped", "message": "N8N_WEBHOOK_URL no configurado."}
    
    if numero_a_notificar:
        data["numero_a_notificar"] = numero_a_notificar

    logging.info(f"Enviando datos a n8n webhook. Payload: {json.dumps(data, indent=2)}")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(N8N_WEBHOOK_URL, json=data, timeout=10.0)
            response.raise_for_status()
            logging.info("Datos enviados a n8n correctamente.")
            return {"status": "success", "message": "Datos enviados a n8n correctamente."}
    except httpx.RequestError as e:
        logging.error(f"Error de red al enviar datos a n8n: {e}", exc_info=True)
        return {"status": "error", "message": f"Error de red al contactar n8n: {e}"}
    except httpx.HTTPStatusError as e:
        logging.error(f"Error de estado HTTP al enviar datos a n8n: {e.response.status_code} - {e.response.text}", exc_info=True)
        return {"status": "error", "message": f"Error de n8n: {e.response.status_code}"}

@app.post("/recognize_face/")
async def recognize_face_api(file: UploadFile = File(...)):
    logging.info(f"Recibida solicitud en /recognize_face/ para el archivo: {file.filename}")
    content_type = getattr(file, 'content_type', '')
    filename = getattr(file, 'filename', '').lower()

    if not content_type or not isinstance(content_type, str) or not content_type.startswith('image/'):
        logging.warning(f"Rechazado archivo '{file.filename}' por tipo de contenido inválido: {content_type}")
        raise HTTPException(status_code=400, detail=f"El archivo '{file.filename}' no es una imagen válida. Content-Type: {content_type}")
    if not (filename.endswith('.jpg') or filename.endswith('.jpeg')):
        logging.warning(f"Rechazado archivo '{file.filename}' por extensión no permitida.")
        raise HTTPException(status_code=400, detail="Solo se permiten archivos de imagen con extensión .jpg o .jpeg.")

    try:
        image_bytes = await file.read()
        logging.info(f"Leídos {len(image_bytes)} bytes del archivo '{file.filename}'.")
        image_stream = io.BytesIO(image_bytes)
        imagen_np = face_recognition.load_image_file(image_stream)

        if not codificaciones_conocidas:
            logging.error("No hay rostros conocidos cargados en la base de datos. El reconocimiento no es posible.")
            raise HTTPException(status_code=503, detail="Servicio no disponible: la base de datos de rostros está vacía.")

        resultados_reconocimiento = reconocer_rostros(imagen_np, codificaciones_conocidas, nombres_conocidos, info_personas)
        reconocido = any(d["nombre"] != "Desconocido" for d in resultados_reconocimiento)
        status = "reconocido" if reconocido else "no_reconocido"
        logging.info(f"Resultado del reconocimiento: {status}. Detecciones: {resultados_reconocimiento}")

        numero_a_notificar_para_n8n = next((d["a_notificar"] for d in resultados_reconocimiento if d["nombre"] != "Desconocido" and d["a_notificar"]), None)

        image_stream.seek(0)
        encoded_image = base64.b64encode(image_stream.read()).decode('utf-8')

        data_to_n8n = {
            "filename": file.filename,
            "detecciones": resultados_reconocimiento,
            "status": status,
            "imagen_b64": encoded_image
        }

        n8n_response = await enviar_a_n8n(data_to_n8n, numero_a_notificar_para_n8n)

        response_content = {
            "message": "Procesamiento de imagen completado.",
            "detecciones": resultados_reconocimiento,
            "status": status,
            "n8n_status": n8n_response,
        }

        return JSONResponse(content=response_content)

    except Exception as e:
        logging.error(f"Error inesperado en recognize_face_api al procesar '{file.filename}'.", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error interno del servidor al procesar la imagen: {e}")

async def procesar_imagenes_y_obtener_codificaciones(files: List[UploadFile], nombre_persona: str):
    imagenes_guardadas = []
    codificaciones_obtenidas = []
    Path(RUTA_IMAGENES_CONOCIDAS).mkdir(parents=True, exist_ok=True)

    for file in files:
        filename = os.path.basename(getattr(file, 'filename', 'unknown.jpg').lower())
        logging.info(f"Procesando imagen '{filename}' para la persona '{nombre_persona}'.")
        content_type = getattr(file, 'content_type', '')
        if not content_type or not isinstance(content_type, str) or not content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail=f"El archivo {filename} no parece ser una imagen válida.")
        if not (filename.endswith('.jpg') or filename.endswith('.jpeg')):
            raise HTTPException(status_code=400, detail=f"Solo se aceptan imágenes .jpg o .jpeg. Archivo recibido: {filename}")

        try:
            image_bytes = await file.read()
            image_stream = io.BytesIO(image_bytes)
            imagen_np = face_recognition.load_image_file(image_stream)

            encodings = face_recognition.face_encodings(imagen_np)
            if encodings:
                codificaciones_obtenidas.append(encodings[0].tolist())
                file_path = os.path.join(RUTA_IMAGENES_CONOCIDAS, filename)
                with open(file_path, "wb") as buffer:
                    buffer.write(image_bytes)
                imagenes_guardadas.append(filename)
                logging.info(f"Imagen '{filename}' procesada y guardada correctamente para '{nombre_persona}'.")
            else:
                logging.warning(f"No se detectó ningún rostro en la imagen '{filename}'. Será descartada.")

        except Exception as e:
            logging.error(f"Error al procesar la imagen '{filename}' para '{nombre_persona}'.", exc_info=True)
            raise HTTPException(status_code=500, detail=f"No se pudo procesar la imagen '{filename}'. ¿Es un archivo de imagen válido y no está corrupto?")

    if not codificaciones_obtenidas:
        logging.warning(f"No se pudo obtener ninguna codificación facial para '{nombre_persona}' de los archivos proporcionados.")
        raise HTTPException(status_code=400, detail="No se detectaron rostros válidos en ninguna de las imágenes. Sube imágenes claras donde se vea bien la cara.")

    return imagenes_guardadas, codificaciones_obtenidas

@app.post("/register_person/")
async def register_person(
    nombre: str = Form(...),
    peligroso: bool = Form(False),
    dni: Optional[str] = Form(None),
    domicilio: Optional[str] = Form(None),
    correo_electronico: Optional[str] = Form(None),
    celular: Optional[str] = Form(None),
    a_notificar: Optional[str] = Form(None),
    files: List[UploadFile] = File(...)
):
    logging.info(f"Recibida solicitud para registrar a la persona: '{nombre}'.")
    if not files:
        raise HTTPException(status_code=400, detail="Es obligatorio subir al menos una imagen de la persona.")

    db_dir = os.path.dirname(RUTA_DB)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir)

    db = []
    if os.path.exists(RUTA_DB):
        try:
            with open(RUTA_DB, 'r', encoding='utf-8') as f:
                content = f.read()
                if content:
                    db = json.loads(content)
        except json.JSONDecodeError:
            logging.error(f"El archivo '{RUTA_DB}' está mal formado y no se puede decodificar. Se tratará como vacío.", exc_info=True)
            raise HTTPException(status_code=500, detail="La base de datos parece estar corrupta.")
        except Exception as e:
            logging.error(f"Error inesperado al leer la base de datos '{RUTA_DB}'.", exc_info=True)
            raise HTTPException(status_code=500, detail="Error crítico al leer la base de datos.")

    if any(p.get('nombre', '').lower() == nombre.lower() for p in db):
        logging.warning(f"Intento de registrar a una persona que ya existe: '{nombre}'.")
        raise HTTPException(status_code=409, detail=f"La persona con el nombre '{nombre}' ya existe.")

    imagenes_guardadas, codificaciones_obtenidas = await procesar_imagenes_y_obtener_codificaciones(files, nombre)

    nueva_persona = {
        "nombre": nombre,
        "peligroso": peligroso,
        "imagenes": imagenes_guardadas,
        "face_encodings": codificaciones_obtenidas,
        "dni": dni,
        "domicilio": domicilio,
        "correo_electronico": correo_electronico,
        "celular": celular,
        "a_notificar": a_notificar
    }
    db.append(nueva_persona)

    try:
        with open(RUTA_DB, 'w', encoding='utf-8') as f:
            json.dump(db, f, indent=4)
        logging.info(f"Persona '{nombre}' registrada y guardada en '{RUTA_DB}'.")
    except Exception as e:
        logging.error(f"No se pudo escribir en el archivo de base de datos '{RUTA_DB}'.", exc_info=True)
        raise HTTPException(status_code=500, detail="No se pudo guardar la información en la base de datos.")

    actualizar_base_de_datos_en_memoria()

    return JSONResponse(content={
        "message": f"Persona '{nombre}' registrada exitosamente.",
        "imagenes_registradas": imagenes_guardadas
    })

@app.get("/")
async def read_root():
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            html_content = f.read()
        return HTMLResponse(content=html_content, status_code=200)
    except FileNotFoundError:
        logging.error("No se encontró el archivo index.html en el directorio raíz.")
        return HTMLResponse(content="<h1>Error: index.html no encontrado</h1><p>Asegúrate de que el archivo se encuentra en el directorio correcto.</p>", status_code=404)

if __name__ == "__main__":
    import uvicorn
    logging.info("Para iniciar la API, ejecuta el comando: uvicorn main:app --host 0.0.0.0 --port 8000 --reload")
    logging.info(f"URL del Webhook de n8n configurada: {N8N_WEBHOOK_URL}")
    # Descomenta la siguiente línea para ejecutar directamente con 'python main.py'
    # uvicorn.run(app, host="0.0.0.0", port=8000)
