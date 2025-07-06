# Usa una imagen base de Python
FROM python:3.9-slim-buster

# Instalar dependencias del sistema necesarias para dlib
RUN apt-get update && apt-get install -y \
    cmake \
    build-essential \
    libopenblas-dev \
    liblapack-dev \
    libx11-dev \
    libgtk-3-dev \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Establece el directorio de trabajo dentro del contenedor
WORKDIR /app

# Copia el archivo de requisitos e instala las dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia el resto del código de la aplicación al contenedor
COPY . .

# Expone el puerto en el que se ejecutará la aplicación
EXPOSE 8000

# Define la variable de entorno para el webhook de N8N (puede ser sobrescrita en tiempo de ejecución)
ENV N8N_WEBHOOK_URL="https://n8n.supervis.ar/webhook-test/e641ceb9-838c-4df7-a3e0-c493ec6b69e8"

# Comando para ejecutar la aplicación con Uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]