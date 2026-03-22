# 1. Use a lightweight Python image
FROM python:3.10-slim

# 2. Install Linux OS dependencies (Tesseract OCR & OpenCV required libs)
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    libtesseract-dev \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

# 3. Set the working directory inside the cloud server
WORKDIR /app

# 4. Copy your requirements and install them
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy all your project files into the cloud server
COPY . .

# 6. Create necessary folders to prevent crash errors
RUN mkdir -p uploads/payments faces

# 7. Expose the port
EXPOSE 5000

# 8. Start the app using Gunicorn (Production Server)
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--timeout", "120", "--workers", "1", "server:app"]