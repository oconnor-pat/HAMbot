from dotenv import load_dotenv
import nextcord
from nextcord.ext import commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import asyncio
import os
import logging

# Config logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Load env variables
load_dotenv()
APPLICATION_ID = os.getenv("APPLICATION_ID")
GUILD_IDS = [int(guild_id) for guild_id in os.getenv("GUILD_IDS").split(",")]
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

intents = nextcord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Initializes the scheduler
scheduler = AsyncIOScheduler()

# Modifies the poll_responses to track each user's response
poll_responses = {"available": [], "unavailable": [], "responded_users": set()}


# Function to send the daily poll
async def send_daily_poll():
    for guild_id in GUILD_IDS:
        guild = bot.get_guild(guild_id)
        if guild is None:
            logger.error(f"Guild with ID {guild_id} not found")
            continue

        channel = nextcord.utils.get(guild.text_channels, name="general")
        if channel is None:
            logger.error("Channel 'general' not found in guild ID " + str(guild_id))
            continue

        message = await channel.send(
            "Availability for raid tonight:\nReact with ✅ for Available and ❌ for Unavailable."
        )
        await message.add_reaction("✅")
        await message.add_reaction("❌")

        # Reset poll responses
        poll_responses["available"].clear()
        poll_responses["unavailable"].clear()
        poll_responses["responded_users"].clear()

        # Starts handling reactions
        asyncio.create_task(handle_reactions(message, channel))


async def handle_reactions(message, channel):
    logger.info("handle_reactions started.")
    start_time = asyncio.get_event_loop().time()
    total_timeout = 18000.0  # 5 hours in seconds
    reaction_wait_timeout = 30.0  # 30 seconds

    while True:
        try:
            elapsed_time = asyncio.get_event_loop().time() - start_time
            remaining_timeout = max(0, total_timeout - elapsed_time)

            if remaining_timeout <= 0:
                logger.info("Poll duration expired.")
                break

            # Waits for a reaction with a timeout of up to 30 seconds or the remaining timeout
            reaction, user = await asyncio.wait_for(
                bot.wait_for(
                    "reaction_add", check=lambda r, u: check_reaction(r, u, message)
                ),
                timeout=min(reaction_wait_timeout, remaining_timeout),
            )
            logger.info(f"Reaction received: {reaction.emoji} from {user.name}")
            await process_reaction(reaction, user, channel)

        except asyncio.TimeoutError:
            # logs timeouts
            logger.info("Waiting for more reactions...")

    logger.info("handle_reactions ended.")


# Updates the check_reaction function to allow reactions from users who have already responded
def check_reaction(reaction, user, message):
    return str(reaction.emoji) in ["✅", "❌"] and reaction.message.id == message.id


# Modifies the function to allow users to change their response
async def process_reaction(reaction, user, channel):
    # Removes the user's previous response if they have already responded
    if user.id in poll_responses["responded_users"]:
        if user.id in poll_responses["available"]:
            poll_responses["available"].remove(user.id)
        elif user.id in poll_responses["unavailable"]:
            poll_responses["unavailable"].remove(user.id)

    # Adds the user's new response
    if str(reaction.emoji) == "✅":
        poll_responses["available"].append(user.id)
    elif str(reaction.emoji) == "❌":
        poll_responses["unavailable"].append(user.id)

    # Ensures the user is marked as having responded
    poll_responses["responded_users"].add(user.id)

    # Logs the updated counts
    logger.info(
        f"Processed reaction: {reaction.emoji} from {user.name}. Available: {len(poll_responses['available'])}, Unavailable: {len(poll_responses['unavailable'])}"
    )

    # Checks if enough people are available
    if len(poll_responses["available"]) >= 6:
        await channel.send("@everyone We have enough people for the raid tonight!")
        logger.info("Enough people for the raid tonight.")


@bot.slash_command(name="checkpoll", description="Check the current poll status")
async def check_poll(interaction: nextcord.Interaction):
    available = len(poll_responses["available"])
    unavailable = len(poll_responses["unavailable"])
    await interaction.response.send_message(
        f"Poll Status:\nAvailable: {available}\nUnavailable: {unavailable}",
        ephemeral=False,
    )


@bot.slash_command(name="raidpoll", description="Start a raid availability poll")
async def start_raid_poll(interaction: nextcord.Interaction):
    await interaction.response.defer()
    logger.info("Interaction deferred.")

    guild = bot.get_guild(interaction.guild_id)
    if guild is None:
        await interaction.followup.send(
            "Error: Bot is not in the guild associated with this command.",
            ephemeral=True,
        )
        logger.error("Guild not found.")
        return

    channel = nextcord.utils.get(guild.text_channels, name="general")
    if channel is None:
        await interaction.followup.send(
            "Error: Channel 'general' not found in the guild.", ephemeral=True
        )
        logger.error("Channel 'general' not found.")
        return

    message_content = (
        "Availability for raid tonight:\n"
        "React with ✅ for Available and ❌ for Unavailable."
    )
    message = await channel.send(message_content)
    await message.add_reaction("✅")
    await message.add_reaction("❌")
    logger.info("Poll message sent and reactions added.")

    # Reset poll responses
    poll_responses["available"].clear()
    poll_responses["unavailable"].clear()
    poll_responses["responded_users"].clear()

    # Start handling reactions
    asyncio.create_task(handle_reactions(message, channel))
    logger.info("Reactions handling started.")

    await interaction.followup.send(
        "Raid availability poll has been successfully started!"
    )
    logger.info("Follow-up message sent.")


# slash command to reset to poll and it's responses
@bot.slash_command(
    name="resetpoll", description="Reset the current poll and clear all responses"
)
async def reset_poll(interaction: nextcord.Interaction):
    # Clears the poll responses
    poll_responses["available"].clear()
    poll_responses["unavailable"].clear()
    poll_responses["responded_users"].clear()

    # Sends a confirmation message
    await interaction.response.send_message("The poll has been reset.", ephemeral=False)
    logger.info("Poll reset.")


# Time to send the daily poll
scheduler.add_job(send_daily_poll, "cron", hour=12, minute=0)


@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user}")
    scheduler.start()


bot.run(DISCORD_BOT_TOKEN)
