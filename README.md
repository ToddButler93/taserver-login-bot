# Discord Bot

## Description

This project is a Discord bot built using the `discord.py` library. The bot supports several features including user verification through SSH commands, command limits, and administrative commands.

## Features

- **User Verification**: Allows users to verify their accounts through SSH commands.
- **Administrative Commands**: Provides commands for server administrators to manage the bot, including restarting the server and resetting user limits.

## Prerequisites

- Python 3.8 or higher
- A Discord bot token
- SSH server details for verification commands

### Discord bot setup

Follow [here](https://discordpy.readthedocs.io/en/stable/discord.html) and [here](https://discordpy.readthedocs.io/en/stable/intents.html#privileged-intents).

## Setup

### Creating a Virtual Environment

1. **Create the Virtual Environment:**

   ```bash
   python -m venv bot-env
   ```

2. **Activate the Virtual Environment:**

   - On **Windows**:

     ```bash
     bot-env\Scripts\activate
     ```

   - On **macOS and Linux**:

     ```bash
     source bot-env/bin/activate
     ```

3. **Install Dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

### Configuration

1. **Create a `.env` File:**

   Create a file named `.env` in the project directory and add the following environment variables:

   ```env
   DISCORD_TOKEN=your_discord_bot_token
   GUILD_ID=your_discord_guild_id
   SSH_HOST=your_ssh_host
   SSH_PORT=your_ssh_port
   SSH_USERNAME=your_ssh_username
   SSH_KEY=your_ssh_key
   ```

2. **Replace Placeholders:**

   - Replace `your_discord_bot_token` with your actual Discord bot token.
   - Replace `your_discord_guild_id` with your guild (server) ID.
   - Replace `your_ssh_host`, `your_ssh_port`, `your_ssh_username`, and `your_ssh_key` with your SSH server details.

## Running the Bot

To start the bot, use the following command:

```bash
python great-eagle.py
```

## Commands

- **/verify**: Initiates the user verification process.
- **/restartloginserver**: Restarts the login server Docker container. (Administrative only)
- **/resetuserlimit**: Resets a user's verification attempt limit. (Administrative only)

## Troubleshooting

- Ensure that all environment variables are correctly set in the `.env` file.
- Verify that your SSH server is correctly configured and accessible.
- Check the `data/logs/discord.log` file for detailed error logs.
