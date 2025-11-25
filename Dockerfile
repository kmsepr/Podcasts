# Use official lightweight Python image
FROM python:3.11-slim

# Install ffmpeg (required for transcoding)
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy app files
COPY . /app

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Create volume mount point for persistent data
VOLUME ["/mnt/data"]

# Avoid Python buffering
ENV PYTHONUNBUFFERED=1

# Expose port (Koyeb maps $PORT to this)
EXPOSE 8000

# Run Flask app
CMD ["python", "app.py"]
