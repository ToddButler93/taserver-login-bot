import discord
from discord.ext import commands
from discord import app_commands, ui, Embed
import logging
import os
import asyncio
import paramiko
import re
import traceback
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
os.makedirs("data/logs", exist_ok=True)
handler = logging.FileHandler(
    filename="data/logs/discord.log", encoding="utf-8", mode="w"
)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
logging.basicConfig(level=logging.INFO, handlers=[handler])

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD = os.getenv("GUILD_ID")
NOTIFY_CHANNEL_ID = int(os.getenv("NOTIFY_CHANNEL_ID", 0))
# SSH details from environment variables
SSH_HOST = os.getenv("SSH_HOST")
try:
    SSH_PORT = int(os.getenv("SSH_PORT"))  # Default to port 22 if not provided
except ValueError:
    raise ValueError("SSH_PORT must be an integer.")
SSH_USERNAME = os.getenv("SSH_USERNAME")
SSH_PASS = os.getenv("SSH_PASS")


if not all([TOKEN, GUILD, NOTIFY_CHANNEL_ID]):
    raise ValueError("Missing env variables.")


def validate_ssh_config():
    return all([SSH_HOST, SSH_PORT, SSH_USERNAME, SSH_PASS])


SSH_CONFIG_VALID = validate_ssh_config()


# Load user attempts from file
def load_user_attempts():
    file_path = "data/user_attempts.json"
    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            return json.load(f)
    return {}


# Save user attempts to file
def save_user_attempts(user_attempts):
    file_path = "data/user_attempts.json"
    with open(file_path, "w") as f:
        json.dump(user_attempts, f)


# Main Class
class GreatEagle(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        self.ssh_semaphore = asyncio.Semaphore(1)
        self.user_attempts = load_user_attempts()

    async def execute_ssh_command(self, command):
        logging.info(f"Executing SSH command: {command}")
        async with self.ssh_semaphore:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            try:
                ssh.connect(
                    SSH_HOST, port=SSH_PORT, username=SSH_USERNAME, password=SSH_PASS
                )
                stdin, stdout, stderr = ssh.exec_command(command)
                exit_status = stdout.channel.recv_exit_status()
                stdout_lines = stdout.readlines()
                stderr_lines = stderr.readlines()
                logging.info(f"SSH command output: {''.join(stdout_lines)}")
                if stderr_lines:
                    logging.error(f"SSH command error: {''.join(stderr_lines)}")
                return exit_status, stdout_lines, stderr_lines
            finally:
                ssh.close()

    async def setup_hook(self):
        # Ensure self.tree is initialized
        if self.tree is None:
            raise RuntimeError("self.tree is not initialized.")
        await self.tree.sync()
        await self.tree.sync(guild=discord.Object(id=GUILD))
        logging.info(f"Cleared and synced slash commands for {self.user}.")

    async def on_command_error(self, ctx, error):
        logging.error(f"Command error: {error}")


# Instantiate the bot
greatEagle = GreatEagle()


# Modal Classes
class VerifyModal(discord.ui.Modal, title="Verify Account for the PUG login server"):
    answer = ui.TextInput(
        label="Username",
        style=discord.TextStyle.short,
        placeholder="Tribes Username",
        required=True,
        max_length=9,
    )

    def __init__(self, bot):
        super().__init__()
        self.bot = bot  # Store the bot instance

    async def on_submit(self, interaction: discord.Interaction):
        user_name = interaction.user.name

        # Initialize user attempts if not already present
        if user_name not in self.bot.user_attempts:
            self.bot.user_attempts[user_name] = 0

        # Check if the user has exceeded the limit
        if (
            self.bot.user_attempts[user_name] >= 5
            and not interaction.user.guild_permissions.administrator
        ):
            if NOTIFY_CHANNEL_ID:
                channel = self.bot.get_channel(NOTIFY_CHANNEL_ID)
                if channel:
                    await channel.send(
                        f"User {interaction.user.mention} has passed the maximum number verification attempts, please assist."
                    )
                else:
                    logging.error(f"Channel with ID {NOTIFY_CHANNEL_ID} not found.")

            await interaction.response.send_message(
                "You have reached the maximum number of attempts. Contact an admin if you need further assistance.",
                ephemeral=True,
            )
            return

        # Increment the user's attempt count
        self.bot.user_attempts[user_name] += 1
        save_user_attempts(self.bot.user_attempts)

        await interaction.response.defer(ephemeral=True)
        username = self.answer.value

        # Regular expression to check for only alphanumeric characters
        if not re.match("^[a-zA-Z0-9]*$", username):
            logging.error(
                f"User attempted to use non-alphanumeric characters: {username}"
            )
            await interaction.followup.send(
                "Invalid input: Please use only alphanumeric characters.",
                ephemeral=True,
            )
            return

        if not SSH_CONFIG_VALID:
            await interaction.followup.send(
                "Verification process is currently unavailable due to missing configuration.",
                ephemeral=True,
            )
            return

        try:
            exit_status, stdout_lines, stderr_lines = (
                await self.bot.execute_ssh_command(
                    f"docker exec loginserver python3 taserver/getauthcode.py {username} {username}"
                )
            )

            if exit_status == 0:
                output = "".join(stdout_lines).strip()
                if output.startswith("The specified"):
                    logging.info(f"Verification failed for {username}: {output}")
                    await interaction.followup.send(
                        "Verification failed: The specified email address does not match the one stored for the account.",
                        ephemeral=True,
                    )
                else:
                    verification_code = output if output else "No output from script"
                    logging.info(
                        f"Generated verification code for {username}: {verification_code}"
                    )
                    await interaction.followup.send(
                        f"Thanks for verifying, your code is: {verification_code}",
                        ephemeral=True,
                    )
            else:
                logging.error(f"Script error: {''.join(stderr_lines)}")
                await interaction.followup.send(
                    "Oops, something went wrong with the verification process.",
                    ephemeral=True,
                )

        except paramiko.SSHException as e:
            logging.error(f"SSH connection error: {e}")
            await interaction.followup.send(
                "Failed to connect to the verification server.", ephemeral=True
            )
        except Exception as e:
            logging.error(f"Unexpected error: {e}")
            await interaction.followup.send(
                "Oops, something went wrong!", ephemeral=True
            )

    async def on_error(
        self, interaction: discord.Interaction, error: Exception
    ) -> None:
        logging.error(f"Modal error: {error}")
        await interaction.followup.send("Oops, something went wrong!", ephemeral=True)
        traceback.print_exception(type(error), error, error.__traceback__)


# Commands and Modals
async def verify_command(interaction: discord.Interaction):
    if SSH_CONFIG_VALID:
        await interaction.response.send_modal(VerifyModal(bot=greatEagle))
    else:
        await interaction.response.send_message(
            "Command not available due to missing or incorrect configuration.",
            ephemeral=True,
        )


@greatEagle.tree.command(
    guild=discord.Object(id=GUILD), description="Submit verification"
)
async def verify(interaction: discord.Interaction):
    await verify_command(interaction)


async def restart_login_server(ctx: commands.Context):
    await ctx.defer(ephemeral=True)
    try:
        exit_status, stdout_lines, stderr_lines = await greatEagle.execute_ssh_command(
            "docker restart loginserver"
        )
        logging.info(f"Command output: {''.join(stdout_lines)}")
        if stderr_lines:
            logging.error(f"Command error: {''.join(stderr_lines)}")

        if exit_status == 0:
            await ctx.reply(
                "The login server is being restarted. Please wait a moment for it to come back online."
            )
        else:
            await ctx.reply(
                "Failed to restart the login server. Please check the logs for more details."
            )
    except Exception as e:
        logging.error(f"Unexpected error while restarting the server: {e}")
        await ctx.reply(
            "An unexpected error occurred while attempting to restart the login server."
        )


if SSH_CONFIG_VALID:

    @greatEagle.hybrid_command(
        name="restartloginserver",
        with_app_command=True,
        description="Restart the PUG Login Server",
    )
    @app_commands.guilds(discord.Object(id=GUILD))
    @commands.has_permissions(administrator=True)
    async def restartloginserver(ctx: commands.Context):
        await restart_login_server(ctx)

else:

    @greatEagle.hybrid_command(
        name="restartloginserver",
        with_app_command=True,
        description="Restart the PUG Login Server",
    )
    @app_commands.guilds(discord.Object(id=GUILD))
    @commands.has_permissions(administrator=True)
    async def restartloginserver(ctx: commands.Context):
        await ctx.reply(
            "Command not available due to missing or incorrect configuration.",
            ephemeral=True,
        )


async def reset_user_limit(ctx: commands.Context, user: discord.User):
    if user.name in greatEagle.user_attempts:
        greatEagle.user_attempts[user.name] = 0
        save_user_attempts(greatEagle.user_attempts)

        # Create an embed message
        embed = Embed(
            title="Verification Limit Reset",
            description=f"Verification attempts for user {user.mention} have been successfully reset.",
            color=0x00FF00,  # Green color for success
        )
        embed.set_author(name=user.display_name, icon_url=user.avatar.url)

        await ctx.reply(embed=embed)
    else:
        embed = Embed(
            title="User Not Found",
            description="No verification attempts found for the specified user.",
            color=0xFF0000,  # Red color for errors
        )
        embed.set_author(name=user.display_name, icon_url=user.avatar.url)

        await ctx.reply(embed=embed)


# Register the command
@greatEagle.hybrid_command(
    name="resetuserlimit",
    with_app_command=True,
    description="Resets a user's verification limit",
)
@app_commands.guilds(discord.Object(id=GUILD))
@commands.has_permissions(administrator=True)
async def resetuserlimit(ctx: commands.Context, user: discord.User):
    await reset_user_limit(ctx, user)


class InstallView(discord.ui.View):
    def __init__(self):
        super().__init__()
        # Add a button to the view
        self.add_item(
            discord.ui.Button(
                label="Download TA Launcher V2",
                style=discord.ButtonStyle.success,  # Green button
                url="https://github.com/Dylan-B-D/ta-launcher/releases/latest",
            )
        )
        self.add_item(
            discord.ui.Button(
                label="How to Play",
                style=discord.ButtonStyle.url,  # Green button
                url="https://www.dodgesdomain.com/docs/gameplay/guide-quick",
            )
        )


@greatEagle.tree.command(
    guild=discord.Object(id=GUILD),
    name="tribesinstall",
    description="Get a link to download the TA Launcher V2",
)
async def tribesinstall(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Tribes Ascend Installation",
        description="Download TA Launcher V2 below. It will guide you through the entire install process.",
        color=int("00AA95", 16),  # Green color
    )
    # Add a thumbnail
    embed.set_thumbnail(
        url="https://utfs.io/f/e45e1d6b-5545-4080-ab99-2bdf3235e8c2-sedzba.png"
    )
    # Add fields to the embed
    embed.add_field(
        name="Verify",
        value="After logging into the PUG login server, you can use the /verify command with this bot to verify your account.",
        inline=False,
    )

    # Add an image to the embed
    embed.set_image(
        url="https://utfs.io/f/99f42db1-4d19-496a-9168-472d01d6327c-2cr5.jpg"
    )

    # Add a footer
    embed.set_footer(
        text="Don't be afraid to ask for help, we are always excited to have more players!"
    )

    await interaction.response.send_message(embed=embed, view=InstallView())


greatEagle.run(TOKEN, log_handler=handler)
