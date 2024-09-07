import discord
from discord.ext import commands
from discord import app_commands
from discord import ui
import logging
import os
import asyncio
import subprocess
from dotenv import load_dotenv
import re
import traceback
import paramiko

# Load environment variables
load_dotenv()

# Configure logging
handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logging.basicConfig(level=logging.INFO, handlers=[handler])

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD = os.getenv("GUILD_ID")

# SSH details from environment variables
SSH_HOST = os.getenv("SSH_HOST")
SSH_PORT = os.getenv("SSH_PORT") 
SSH_USERNAME = os.getenv("SSH_USERNAME")
SSH_KEY = os.getenv("SSH_KEY")

def validate_ssh_config():
    return all([SSH_HOST, SSH_PORT, SSH_USERNAME, SSH_KEY])
    
SSH_CONFIG_VALID = validate_ssh_config()

# Main Class

class GreatEagle(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        
    async def setup_hook(self):
        await self.tree.sync(guild=discord.Object(id=GUILD))
        logging.info(f"Synced slash commands for {self.user}.")

    async def on_command_error(self, ctx, error):
        logging.error(f"Command error: {error}")
        await ctx.send(f"An error occurred: {error}", ephemeral=True)

# Modal Classes

# docker exec -t loginserver ls /data > /dev/null 2>&1 && echo 1 || echo 0

class VerifyModal(discord.ui.Modal, title="Verify Account for the PUG login server"):
    answer = ui.TextInput(
        label="Username",
        style=discord.TextStyle.short,
        placeholder="Tribes Username",
        required=True,
        max_length=9
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        username = self.answer.value
        
        # Regular expression to check for only alphanumeric characters
        if not re.match("^[a-zA-Z0-9]*$", username):
            logging.error(f"User attempted to use non-alphanumeric characters: {username}")
            await interaction.followup.send("Invalid input: Please use only alphanumeric characters.", ephemeral=True)
            return

        if not SSH_CONFIG_VALID:
            await interaction.followup.send("Verification process is currently unavailable due to missing configuration.", ephemeral=True)
            return

        try:
            # Create and use an SSH client context manager for better resource management
            async with asyncio.Semaphore(1):  # Limit the number of concurrent SSH connections
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                
                # Connect to the remote server
                ssh.connect(SSH_HOST, port=SSH_PORT, username=SSH_USERNAME, password=SSH_KEY)
                
                # Construct the Docker command
                command = f"docker exec loginserver python3 taserver/getauthcode.py {username} {username}"
                
                # Execute the Docker command
                stdin, stdout, stderr = ssh.exec_command(command)
                exit_status = stdout.channel.recv_exit_status()  # Wait for command to complete
                
                # Capture and handle command output
                stdout_lines = stdout.readlines()
                stderr_lines = stderr.readlines()
                ssh.close()
                
                if exit_status == 0:
                    verification_code = stdout_lines[0].strip() if stdout_lines else "No output from script"
                    logging.info(f"Generated verification code for {username}: {verification_code}")
                    await interaction.followup.send(f'Thanks for verifying, your code is: {verification_code}', ephemeral=True)
                else:
                    logging.error(f"Script error: {''.join(stderr_lines)}")
                    await interaction.followup.send('Oops, something went wrong with the verification process.', ephemeral=True)

        except paramiko.SSHException as e:
            logging.error(f"SSH connection error: {e}")
            await interaction.followup.send('Failed to connect to the verification server.', ephemeral=True)
        except Exception as e:
            logging.error(f"Unexpected error: {e}")
            await interaction.followup.send('Oops, something went wrong!', ephemeral=True)

        await asyncio.sleep(4)  # Optional: simulate processing delay

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        logging.error(f"Modal error: {error}")
        await interaction.followup.send('Oops, something went wrong!', ephemeral=True)
        traceback.print_exception(type(error), error, error.__traceback__)

# The ritual to spawn our great leader
greatEagle = GreatEagle()

# Modals
if SSH_CONFIG_VALID:
    @greatEagle.tree.command(guild=discord.Object(id = GUILD), description="Submit verification")
    async def verify(interaction: discord.Interaction):
        await interaction.response.send_modal(VerifyModal())
else:
    @greatEagle.tree.command(guild=discord.Object(id = GUILD), description="Submit verification")
    async def verify(interaction: discord.Interaction):
        await interaction.response.send_message("Command not available due to missing or incorrect configuration.", ephemeral=True)

# Hybrid Commands

@greatEagle.hybrid_command(name = "test", with_app_command = True, description = "Testing")
@app_commands.guilds(discord.Object(id = GUILD))
async def test(ctx: commands.Context):
    await ctx.defer(ephemeral = True)
    await ctx.reply("hi!")

if SSH_CONFIG_VALID:
    @greatEagle.hybrid_command(name="restartloginserver", with_app_command=True, description="Restart the PUG Login Server")
    @app_commands.guilds(discord.Object(id=GUILD))
    @commands.has_permissions(administrator=True)
    async def restartloginserver(ctx: commands.Context):
        await ctx.defer(ephemeral=True)

        try:
            # Create an SSH client
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Connect to the remote server
            ssh.connect(SSH_HOST, port=int(SSH_PORT), username=SSH_USERNAME, password=SSH_KEY)

            # Run the Docker restart command
            stdin, stdout, stderr = ssh.exec_command("docker restart loginserver")
            exit_status = stdout.channel.recv_exit_status()  # Wait for command to complete
            
            # Log output and errors
            stdout_lines = stdout.readlines()
            stderr_lines = stderr.readlines()
            logging.info(f"Command output: {''.join(stdout_lines)}")
            logging.error(f"Command error: {''.join(stderr_lines)}" if stderr_lines else "No errors")
            
            if exit_status == 0:
                await ctx.reply("The login server Docker container is being restarted. Please wait a moment for it to come back online.")
            else:
                await ctx.reply("Failed to restart the login server Docker container. Please check the logs for more details.")
            
        except Exception as e:
            logging.error(f"SSH error: {e}")
            await ctx.reply("An unexpected error occurred while attempting to restart the Docker container.")

        finally:
            ssh.close()
else:
    # Define a placeholder command or handle the case where SSH config is invalid
    @greatEagle.hybrid_command(name="restartloginserver", with_app_command=True, description="Restart the PUG Login Server")
    @app_commands.guilds(discord.Object(id=GUILD))
    @commands.has_permissions(administrator=True)
    async def restartloginserver(ctx: commands.Context):
        await ctx.reply("Command not available due to missing or incorrect configuration.", ephemeral=True)


greatEagle.run(TOKEN, log_handler=handler)
