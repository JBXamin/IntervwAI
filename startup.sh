#!/bin/sh
echo "Startup script started" >> /home/site/wwwroot/startup.log
apt-get update >> /home/site/wwwroot/startup.log 2>&1
apt-get install -y portaudio19-dev >> /home/site/wwwroot/startup.log 2>&1
pip install -r requirements.txt >> /home/site/wwwroot/startup.log 2>&1
echo "Startup script completed" >> /home/site/wwwroot/startup.log
