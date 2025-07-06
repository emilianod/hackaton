# Sistema de Reconocimiento Facial con Alerta de Prioridad

Este proyecto es un sistema de reconocimiento facial diseñado para identificar personas a partir de una imagen y emitir una alerta de alta prioridad si la persona detectada se encuentra en una lista de seguimiento especial.

## Características Principales

- Reconocimiento de rostros en una imagen.
- Base de datos de personas conocidas en formato JSON.
- Sistema de alerta para "personas peligrosas" o de interés.
- Fácil de configurar y extender.

## Instalación

1. Clona o descarga este repositorio.
2. Asegúrate de tener Python 3.x instalado.
3. Instala las dependencias necesarias ejecutando el siguiente comando en la raíz del proyecto:
   ```bash
   pip install -r requirements.txt
   ```

## Configuración

1. **Base de Datos (`db/database.json`):**
   - Crea una carpeta `db` en la raíz de tu proyecto.
   - Abre el archivo `db/database.json`.
   - Añade o modifica los registros de las personas que deseas reconocer.
     - `"nombre"`: El nombre de la persona.
     - `"imagenes"`: Una **lista** con los nombres de los archivos de imagen (deben estar en la carpeta `known_faces/`). Puedes añadir una o más imágenes por persona.
     - `"peligroso"`: `true` si la persona debe activar una alerta de alta prioridad, `false` en caso contrario.

2. **Rostros Conocidos (`known_faces/`):**
   - Coloca los archivos de imagen de las personas conocidas en la carpeta `known_faces/`.
   - El nombre de cada archivo debe coincidir con uno de los nombres de la lista `"imagenes"` en `db/database.json`.

## Uso

1. Coloca la imagen que deseas analizar en la raíz del proyecto y nómbrala `imagen_a_revisar.jpg`.
2. Ejecuta el script principal desde tu terminal:
   ```bash
   python main.py
   ```
3. El resultado del análisis se mostrará en la consola. Si se detecta una persona de interés, se mostrará una alerta especial.

## Dockerización

Para levantar la aplicación usando Docker y Docker Compose, sigue estos pasos:

1.  **Asegúrate de tener Docker y Docker Compose instalados** en tu sistema.

2.  **Crea la estructura de directorios necesaria:**
    -   Asegúrate de que la carpeta `known_faces` exista en la raíz de tu proyecto y contenga las imágenes de los rostros conocidos.
    -   Crea una carpeta `db` en la raíz de tu proyecto y coloca tu archivo `database.json` dentro de ella (`./db/database.json`).

3.  **Construye la imagen de Docker:**
    Desde la raíz de tu proyecto (donde se encuentran `Dockerfile` y `docker-compose.yml`), ejecuta:
    ```bash
    docker-compose build
    ```

4.  **Levanta el servicio Docker:**
    ```bash
    docker-compose up -d
    ```
    Esto iniciará el contenedor en segundo plano. La API estará disponible en `http://localhost:8000`.

    **Volúmenes:**
    -   La carpeta local `./known_faces` se vinculará con `/app/known_faces` dentro del contenedor.
    -   El archivo local `./db/database.json` se vinculará con `/app/db/database.json` dentro del contenedor.
    Esto asegura que tus datos de rostros conocidos y tu base de datos persistan y sean accesibles para la aplicación dentro del contenedor.

    **Variable de Entorno `N8N_WEBHOOK_URL`:**
    Puedes configurar la URL de tu webhook de n8n a través de la variable de entorno `N8N_WEBHOOK_URL`. Si no se especifica, se usará un valor por defecto. Puedes sobrescribirla en tu archivo `.env` o directamente en el comando `docker-compose up`.

5.  **Para detener el servicio:**
    ```bash
    docker-compose down
    ```