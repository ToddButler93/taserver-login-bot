import discord
from discord.ext import commands
from discord import app_commands, ui, Embed
import logging
import os
import asyncio
import re
import traceback
import json
import docker
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

attempts_lock = asyncio.Lock()

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD = os.getenv("GUILD_ID")
NOTIFY_CHANNEL_ID = int(os.getenv("NOTIFY_CHANNEL_ID", 0))
MAX_ATTEMPTS = 5

if not all([TOKEN, GUILD, NOTIFY_CHANNEL_ID]):
    raise ValueError("Missing env variables.")

# Load user attempts from file
def load_user_attempts():
    file_path = "data/user_attempts.json"
    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            return json.load(f)
    return {}


# Save user attempts to file
def save_user_attempts(user_attempts):
    tmp = "data/user_attempts.tmp"
    final = "data/user_attempts.json"

    with open(tmp, "w") as f:
        json.dump(user_attempts, f)

    os.replace(tmp, final)


# Main Class
class GreatEagle(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)
        self.user_attempts = load_user_attempts()
        
        try:
            self.docker_client = docker.from_env()
        except Exception as e:
            print(f"Failed to connect to Docker: {e}")
            self.docker_client = None

    async def setup_hook(self):
        # Ensure self.tree is initialized
        if self.tree is None:
            raise RuntimeError("self.tree is not initialized.")
        if GUILD:
            guild = discord.Object(id=int(GUILD))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
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
        user_id = str(interaction.user.id)
        
        if not greatEagle.docker_client:
            await interaction.response.send_message(
                "Docker is not available. Please contact admin.",
                ephemeral=True
            )
            return
        
        # Initialize user attempts if not already present
        if user_id not in self.bot.user_attempts:
            self.bot.user_attempts[user_id] = 0

        # Check if the user has exceeded the limit
        async with attempts_lock:
            attempts = self.bot.user_attempts.get(user_id, 0)

        if attempts >= MAX_ATTEMPTS and not interaction.user.guild_permissions.administrator:
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
        
        # Increment the user's attempt count
        async with attempts_lock:
            self.bot.user_attempts[user_id] += 1
            save_user_attempts(self.bot.user_attempts)
            
        try:
            container = greatEagle.docker_client.containers.get("loginserver")

            cmd = [
                "python3",
                "taserver/getauthcode.py",
                username,
                username
            ]

            exit_code, output = await asyncio.to_thread(
                container.exec_run,
                cmd,
                demux=True
            )

            stdout, stderr = output

            stdout_text = stdout.decode() if stdout else ""
            stderr_text = stderr.decode() if stderr else ""

            if exit_code == 0:
                output_text = stdout_text.strip()

                if output_text.startswith("The specified"):
                    logging.info(f"Verification failed for {username}: {output_text}")

                    await interaction.followup.send(
                        "Verification failed: Email does not match.",
                        ephemeral=True,
                    )

                else:
                    verification_code = output_text or "No output"

                    logging.info(
                        f"Generated verification code for {username}: {verification_code}"
                    )

                    await interaction.followup.send(
                        f"Thanks for verifying, your code is: {verification_code}",
                        ephemeral=True,
                    )

            else:
                logging.error(f"Script error: {stderr_text}")

                await interaction.followup.send(
                    "Verification script failed. Contact admin.",
                    ephemeral=True,
                )

        except Exception as e:
            logging.exception("Verification failure")

            await interaction.followup.send(
                "Unexpected error occurred.",
                ephemeral=True
            )

    async def on_error(
        self, interaction: discord.Interaction, error: Exception
    ) -> None:
        logging.error(f"Modal error: {error}")
        await interaction.followup.send("Oops, something went wrong!", ephemeral=True)
        traceback.print_exception(type(error), error, error.__traceback__)


# Commands and Modals
async def verify_command(interaction: discord.Interaction):
    await interaction.response.send_modal(VerifyModal(bot=greatEagle))


@greatEagle.tree.command(
    guild=discord.Object(id=int(GUILD)), description="Submit verification"
)
async def verify(interaction: discord.Interaction):
    await verify_command(interaction)


async def restart_login_server(ctx: commands.Context):
    await ctx.defer(ephemeral=True)
    
    if not greatEagle.docker_client:
        await ctx.reply(
            "Docker is not available. Please contact admin.",
            ephemeral=True
        )
        return
    try:
        container = greatEagle.docker_client.containers.get('loginserver')
        
        # Run restart in executor to avoid blocking
        await asyncio.to_thread(container.restart, timeout=10)
        
        await ctx.reply("The Login Server is being restarted. Please wait a moment for it to come back online.")

    except docker.errors.NotFound:
        await ctx.reply("Login Server not found.")
    except Exception as e:
        await ctx.reply("Error restarting Login Server")


@greatEagle.hybrid_command(
    name="restartloginserver",
    with_app_command=True,
    description="Restart the PUG Login Server",
)
@app_commands.guilds(discord.Object(id=int(GUILD)))
@commands.has_permissions(administrator=True)
async def restartloginserver(ctx: commands.Context):
    await restart_login_server(ctx)


async def reset_user_limit(ctx: commands.Context, user: discord.User):
    user_id = str(user.id)

    async with attempts_lock:
        if user_id in greatEagle.user_attempts:
            greatEagle.user_attempts[user_id] = 0
            save_user_attempts(greatEagle.user_attempts)
            found = True
        else:
            found = False

    if found:
        embed = Embed(
            title="Verification Limit Reset",
            description=f"Attempts for {user.mention} reset.",
            color=0x00FF00,
        )
    else:
        embed = Embed(
            title="User Not Found",
            description="No attempts recorded.",
            color=0xFF0000,
        )

    await ctx.reply(embed=embed)



# Register the command
@greatEagle.hybrid_command(
    name="resetuserlimit",
    with_app_command=True,
    description="Resets a user's verification limit",
)
@app_commands.guilds(discord.Object(id=int(GUILD)))
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
    guild=discord.Object(id=int(GUILD)),
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
