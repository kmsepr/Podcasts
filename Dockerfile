# Use official lightweight Python image
FROM python:3.11-slim

# Install ffmpeg (needed for mp3 transcoding)
RUN apt-get update && apt-get install -y ffmpeg && apt-get clean && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy app files
COPY . /app

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Create volume mount point for persistent data
VOLUME ["/mnt/data"]

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV MEDIA_ROOT=/mnt/data/media
ENV DB_PATH=/mnt/data/podcasts.db
ENV PORT=8000

# Expose port
EXPOSE 8000

# Run app
CMD ["python", "app.py"]
