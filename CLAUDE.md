# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a facial recognition system built with FastAPI that identifies faces from uploaded images and sends notifications via n8n webhook. The system maintains a database of known faces with their encoded facial features and personal information.

## Architecture

### Core Components

- **main.py**: FastAPI application with two main endpoints:
  - `/recognize_face/`: Accepts image upload, performs face recognition, sends results to n8n webhook
  - `/register_person/`: Registers new people with their facial encodings and personal data
- **db/database.json**: JSON database storing person records with face encodings, personal info, and notification settings
- **known_faces/**: Directory containing reference images for registered people
- **index.html**: Bootstrap-based web interface for registering new people

### Key Data Flow

1. Face registration: Images uploaded → face encodings computed → stored in database.json with metadata
2. Face recognition: New image → face encodings extracted → compared against database → results sent to n8n webhook
3. Database loads into memory on startup for fast recognition performance

## Development Commands

### Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Run directly with Python
python main.py
```

### Docker Development
```bash
# Build and run with Docker Compose
docker-compose build
docker-compose up -d

# Stop the service
docker-compose down
```

## Environment Configuration

- **N8N_WEBHOOK_URL**: Configure webhook URL for notifications (defaults to test URL)
- **Port**: Application runs on port 8000
- **Volumes**: 
  - `./known_faces` mounted to `/app/known_faces`
  - `./db/database.json` mounted to `/app/db/database.json`

## Database Structure

The database.json contains person records with:
- `nombre`: Person's name
- `peligroso`: Boolean flag for high-priority alerts
- `face_encodings`: Pre-computed facial feature vectors for recognition
- `imagenes`: List of reference image filenames
- Personal info: `dni`, `domicilio`, `correo_electronico`, `celular`
- `a_notificar`: Phone number for notifications when person is recognized

## Key Functions

- `cargar_base_de_datos()`: Loads face encodings from database.json into memory
- `reconocer_rostros()`: Performs face recognition using face_recognition library
- `enviar_a_n8n()`: Sends recognition results to webhook
- `procesar_imagenes_y_obtener_codificaciones()`: Processes uploaded images and extracts face encodings

## Testing

The system can be tested via:
1. Web interface at `http://localhost:8000` for person registration
2. API endpoints at `/recognize_face/` and `/register_person/`
3. Manual testing with curl or similar tools

## Dependencies

- face-recognition: Core facial recognition functionality
- fastapi: Web framework
- uvicorn: ASGI server
- httpx: HTTP client for webhook calls
- python-multipart: File upload support