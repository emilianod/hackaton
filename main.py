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

# Configurar logging básico
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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
    try:
        actualizar_base_de_datos_en_memoria()
        if not codificaciones_conocidas:
            logging.warning("Advertencia: No se cargaron rostros conocidos. La base de datos está vacía o las imágenes no han sido procesadas.")
        else:
            logging.info(f"Base de datos cargada con {len(nombres_conocidos)} rostros conocidos.")
    except Exception as e:
        logging.error(f"Error crítico al cargar la base de datos al inicio: {e}")
    yield

app = FastAPI(lifespan=lifespan)

# Montar el directorio actual para servir archivos estáticos (como index.html)


def cargar_base_de_datos(ruta_db, ruta_imagenes):
    _codificaciones_conocidas = []
    _nombres_conocidos = []
    _info_personas = {}

    # Asegurarse de que el directorio de la base de datos existe
    db_dir = os.path.dirname(ruta_db)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir)
        logging.info(f"Directorio '{db_dir}' creado.")

    if not os.path.exists(ruta_db):
        logging.warning(f"Advertencia: El archivo de base de datos '{ruta_db}' no existe. Creando uno vacío.")
        with open(ruta_db, 'w', encoding='utf-8') as f:
            json.dump([], f)
        return _codificaciones_conocidas, _nombres_conocidos, _info_personas

    with open(ruta_db, 'r', encoding='utf-8') as f:
        try:
            db = json.load(f)
        except json.JSONDecodeError:
            logging.warning(f"Advertencia: El archivo de base de datos '{ruta_db}' está vacío o mal formado. Se tratará como una base de datos vacía.")
            db = []

    for persona in db:
        # Incluir todos los campos relevantes en info_personas
        _info_personas[persona['nombre']] = {
            'peligroso': persona.get('peligroso', False),
            'dni': persona.get('dni'),
            'domicilio': persona.get('domicilio'),
            'correo_electronico': persona.get('correo_electronico'),
            'celular': persona.get('celular'),
            'a_notificar': persona.get('a_notificar') # Nuevo campo
        }
        # Cargar codificaciones directamente de la base de datos
        if 'face_encodings' in persona and persona['face_encodings']:
            for encoding_list in persona['face_encodings']:
                _codificaciones_conocidas.append(np.array(encoding_list))
                _nombres_conocidos.append(persona['nombre'])
        else:
            logging.warning(f"Advertencia: No se encontraron codificaciones faciales para {persona['nombre']} en la base de datos. Asegúrese de que las imágenes fueron procesadas correctamente.")

    return _codificaciones_conocidas, _nombres_conocidos, _info_personas

def actualizar_base_de_datos_en_memoria():
    global codificaciones_conocidas, nombres_conocidos, info_personas
    codificaciones_conocidas, nombres_conocidos, info_personas = cargar_base_de_datos(RUTA_DB, RUTA_IMAGENES_CONOCIDAS)
    logging.info("Base de datos en memoria actualizada.")

def reconocer_rostros(imagen_np, codificaciones_conocidas, nombres_conocidos, info_personas):
    ubicaciones_rostros = face_recognition.face_locations(imagen_np)
    codificaciones_rostros = face_recognition.face_encodings(imagen_np, ubicaciones_rostros)

    resultados = []
    for codificacion_rostro in codificaciones_rostros:
        coincidencias = face_recognition.compare_faces(codificaciones_conocidas, codificacion_rostro)
        distancia_rostro = face_recognition.face_distance(codificaciones_conocidas, codificacion_rostro)
        
        nombre_detectado = "Desconocido"
        es_peligroso = False
        numero_a_notificar = None # Inicializar el nuevo campo

        if True in coincidencias:
            mejor_coincidencia_idx = np.argmin(distancia_rostro)
            nombre_detectado = nombres_conocidos[mejor_coincidencia_idx]
            info = info_personas.get(nombre_detectado, {})
            es_peligroso = info.get('peligroso', False)
            numero_a_notificar = info.get('a_notificar') # Obtener el nuevo campo
        
        resultados.append({
            "nombre": nombre_detectado,
            "peligroso": es_peligroso,
            "a_notificar": numero_a_notificar # Añadir el nuevo campo aquí
        })
    return resultados

async def enviar_a_n8n(data, numero_a_notificar=None):
    if N8N_WEBHOOK_URL == "YOUR_N8N_WEBHOOK_URL_HERE":
        logging.warning("Advertencia: N8N_WEBHOOK_URL no configurado. No se enviarán datos a n8n.")
        return {"status": "error", "message": "N8N_WEBHOOK_URL no configurado."}
    
    # Añadir el número a notificar si está presente
    if numero_a_notificar:
        data["numero_a_notificar"] = numero_a_notificar

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(N8N_WEBHOOK_URL, json=data)
            response.raise_for_status()  # Lanza una excepción para códigos de estado HTTP erróneos
            logging.info(f"Datos enviados a n8n: {data}")
            return {"status": "success", "message": "Datos enviados a n8n correctamente.", "status_webhook": "ok"}
    except httpx.RequestError as e:
        logging.error(f"Error al enviar datos a n8n: {e}")
        return {"status": "error", "status_webhook": f"Error al enviar datos a n8n: {e}"}

@app.post("/recognize_face/")
async def recognize_face_api(file: UploadFile = File(...)):
    content_type = getattr(file, 'content_type', '')
    filename = getattr(file, 'filename', '').lower()
    if not content_type or not isinstance(content_type, str) or not content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="El archivo debe ser una imagen válida.")
    if not (filename.endswith('.jpg') or filename.endswith('.jpeg')):
        raise HTTPException(status_code=400, detail="Solo se permiten archivos .jpg o .jpeg.")
    try:
        # Leer la imagen en memoria
        image_stream = io.BytesIO(await file.read())
        imagen_np = face_recognition.load_image_file(image_stream)

        if not codificaciones_conocidas:
            raise HTTPException(status_code=500, detail="No se han cargado rostros conocidos. Asegúrese de que 'database.json' está configurado y las imágenes existen en 'known_faces'.")

        resultados_reconocimiento = reconocer_rostros(imagen_np, codificaciones_conocidas, nombres_conocidos, info_personas)
        reconocido = any(d["nombre"] != "Desconocido" for d in resultados_reconocimiento)
        status = "reconocido" if reconocido else "no_reconocido"

        # Obtener el número a notificar de la primera persona reconocida (si existe)
        numero_a_notificar_para_n8n = None
        for deteccion in resultados_reconocimiento:
            if deteccion["nombre"] != "Desconocido" and deteccion["a_notificar"]:
                numero_a_notificar_para_n8n = deteccion["a_notificar"]
                break # Tomar el primero que se encuentre

        # Codificar la imagen en base64 (siempre)
        image_stream.seek(0) # Volver al inicio del stream
        encoded_image = base64.b64encode(image_stream.read()).decode('utf-8')

        # Preparar datos para n8n
        data_to_n8n = {
            "filename": file.filename,
            "detecciones": resultados_reconocimiento,
            "status": status,
            "imagen_b64": encoded_image # Siempre incluir la imagen en base64
        }

        # Enviar a n8n (no esperamos a que termine para no bloquear la respuesta de la API)
        n8n_response = await enviar_a_n8n(data_to_n8n, numero_a_notificar_para_n8n)

        response_content = {
            "message": "Procesamiento de imagen completado.",
            "detecciones": resultados_reconocimiento,
            "status": status,
            "n8n_status": n8n_response,
            "imagen_b64": encoded_image # Siempre incluir la imagen en base64 en la respuesta de la API
        }

        return JSONResponse(content=response_content)

    except Exception as e:
        # Loguear el error completo para depuración interna, pero enviar un mensaje genérico al cliente
        logging.error(f"Error interno del servidor en recognize_face_api: {e}")
        raise HTTPException(status_code=500, detail="Error interno del servidor al procesar la imagen.")

async def procesar_imagenes_y_obtener_codificaciones(files: List[UploadFile], nombre_persona: str):
    imagenes_guardadas = []
    codificaciones_obtenidas = []

    # Asegurarse de que el directorio existe
    Path(RUTA_IMAGENES_CONOCIDAS).mkdir(parents=True, exist_ok=True)

    for file in files:
        content_type = getattr(file, 'content_type', '')
        filename = os.path.basename(getattr(file, 'filename', '').lower())
        if not content_type or not isinstance(content_type, str) or not content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail=f"El archivo {file.filename} debe ser una imagen válida.")
        if not (filename.endswith('.jpg') or filename.endswith('.jpeg')):
            raise HTTPException(status_code=400, detail=f"Solo se permiten archivos .jpg o .jpeg para {file.filename}.")

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
                logging.info(f"Imagen {filename} procesada y guardada para {nombre_persona}.")
            else:
                logging.warning(f"Advertencia: No se encontró un rostro en la imagen {filename} para {nombre_persona}. Esta imagen no se usará para el reconocimiento.")

        except Exception as e:
            logging.error(f"Error al procesar o guardar la imagen {filename}: {e}")
            raise HTTPException(status_code=500, detail=f"Error al procesar o guardar la imagen {filename}.")

    if not codificaciones_obtenidas:
        raise HTTPException(status_code=400, detail="No se detectaron rostros válidos en ninguna de las imágenes proporcionadas. Por favor, sube imágenes claras de la cara.")

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
    if not files:
        raise HTTPException(status_code=400, detail="Debe subir al menos una imagen.")

    # Validar que el archivo de base de datos existe y cargarlo
    db_dir = os.path.dirname(RUTA_DB)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir)
        logging.info(f"Directorio '{db_dir}' creado.")

    if not os.path.exists(RUTA_DB):
        db = []
    else:
        try:
            with open(RUTA_DB, 'r', encoding='utf-8') as f:
                content = f.read()
                if not content:
                    db = []
                else:
                    db = json.loads(content)
        except json.JSONDecodeError:
            db = [] # Tratar archivo malformado como vacío
        except Exception as e:
            logging.error(f"Error al leer la base de datos: {e}")
            raise HTTPException(status_code=500, detail="Error al leer la base de datos.")

    # Validar que el nombre no exista ya
    if any(p['nombre'].lower() == nombre.lower() for p in db):
        raise HTTPException(status_code=400, detail=f"La persona con el nombre '{nombre}' ya existe en la base de datos.")

    # Procesar imágenes y obtener codificaciones
    imagenes_guardadas, codificaciones_obtenidas = await procesar_imagenes_y_obtener_codificaciones(files, nombre)

    # Agregar la nueva persona a la base de datos
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
            json.dump(db, f, indent=2)
        logging.info(f"Persona '{nombre}' agregada a database.json.")
    except Exception as e:
        logging.error(f"Error al escribir en database.json: {e}")
        raise HTTPException(status_code=500, detail="Error al actualizar la base de datos.")

    # Recargar la base de datos en memoria
    actualizar_base_de_datos_en_memoria()

    return JSONResponse(content={
        "message": f"Persona '{nombre}' registrada exitosamente.",
        "imagenes_registradas": imagenes_guardadas
    })



@app.get("/")
async def read_root():
    with open("index.html", "r", encoding="utf-8") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content, status_code=200)

if __name__ == "__main__":
    import uvicorn
    # Para ejecutar: uvicorn main:app --host 0.0.0.0 --port 8000 --reload
    # Asegúrate de configurar la variable de entorno N8N_WEBHOOK_URL
    logging.info("Para iniciar la API, ejecuta: uvicorn main:app --host 0.0.0.0 --port 8000 --reload")
    logging.info(f"Asegúrate de configurar la variable de entorno N8N_WEBHOOK_URL (actualmente: {N8N_WEBHOOK_URL})")
    # uvicorn.run(app, host="0.0.0.0", port=8000) # Descomentar para ejecutar directamente desde aquí si es necesario
