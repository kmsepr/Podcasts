# Use official lightweight Python image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy app files
COPY . /app

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Create volume mount point for persistent data
VOLUME ["/mnt/data"]

# Avoid Python buffering
ENV PYTHONUNBUFFERED=1

# Expose port (Koyeb/Heroku use $PORT)
EXPOSE 8000

# Run Flask app
CMD ["python", "app.py"]
