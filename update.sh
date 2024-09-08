# Download and unzip latest commit
wget -O great-eagle.zip https://github.com/ToddButler93/tribes-login-bot/archive/refs/heads/main.zip
unzip -oq great-eagle.zip

# Setup Permissions
chmod +x tribes-login-bot-main/great-eagle.py
chmod +x tribes-login-bot-main/update.sh

# Remove oldfiles
rm great-eagle.py
rm update.sh
rm Dockerfile
rm requirements.txt

# Remove unessisary files
rm great-eagle.zip

# Move files
mv -f tribes-login-bot-main/update.sh update.new.sh
mv -f tribes-login-bot-main/* .

# Cleanup
rm -r tribes-login-vm-main

# Update this script
mv -f update.new.sh update.sh