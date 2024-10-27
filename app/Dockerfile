# Use the official lightweight Python image.
FROM python:3.10-slim

# Allow statements and log messages to immediately appear in the Knative logs
ENV PYTHONUNBUFFERED True

# Define the working directory inside the container
ENV APP_HOME /app
WORKDIR $APP_HOME

# Copy all the files from the local directory to the working directory in the container
COPY . ./

# Print the files in the /app directory to verify that config.json is copied
RUN ls -l /app

# Set permissions for config.json to be readable and writable by the app
RUN chmod 666 /app/config.json

# Install production dependencies.
RUN pip install --no-cache-dir -r requirements.txt

# Run the web service on container startup. Using gunicorn with one worker process and 8 threads.
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 main:app
