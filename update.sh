# Download and unzip latest commit
wget -O great-eagle.zip https://github.com/ToddButler93/taserver-login-bot/archive/refs/heads/main.zip
unzip -oq great-eagle.zip

# Setup Permissions
chmod +x taserver-login-bot-main/great-eagle.py
chmod +x taserver-login-bot-main/update.sh

# Remove oldfiles
rm great-eagle.py
rm update.sh
rm Dockerfile
rm requirements.txt

# Remove unessisary files
rm great-eagle.zip

# Move files
mv -f taserver-login-bot-main/update.sh update.new.sh
mv -f taserver-login-bot-main/* .

# Cleanup
rm -r taserver-login-bot-main

# Update this script
mv -f update.new.sh update.sh
