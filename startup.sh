#!/bin/sh
# Update package list and install PortAudio
apt-get update
apt-get install -y portaudio19-dev
# Install Python dependencies
pip install -r requirements.txt
# Start the application (modify according to your app's entry point)
gunicorn --bind 0.0.0.0:$PORT main:app
