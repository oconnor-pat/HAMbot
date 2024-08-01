from dotenv import load_dotenv
import nextcord
from nextcord.ext import commands
from nextcord import Interaction, ButtonStyle, SelectOption
from nextcord.ui import Button, View, Select
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import asyncio
import os
import logging
from pytz import timezone

# Config logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Load env variables
load_dotenv()
APPLICATION_ID = os.getenv("APPLICATION_ID")
GUILD_IDS = [int(guild_id.strip()) for guild_id in os.getenv("GUILD_IDS").split(",")]
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

intents = nextcord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Initializes the scheduler
scheduler = AsyncIOScheduler()

# Establishes EST timezone
est = timezone("US/Eastern")

# Modifies the poll_responses to track each guild's poll responses
poll_responses = {
    guild_id: {"available": [], "unavailable": [], "responded_users": set()}
    for guild_id in GUILD_IDS
}


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
        poll_responses[guild_id]["available"].clear()
        poll_responses[guild_id]["unavailable"].clear()
        poll_responses[guild_id]["responded_users"].clear()

        # Starts handling reactions
        asyncio.create_task(handle_reactions(message, channel, guild_id))


# Processes each user's response to the poll
async def handle_reactions(message, channel, guild_id):
    logger.info("handle_reactions started.")
    start_time = asyncio.get_event_loop().time()
    total_timeout = 18000.0  # 5 hours in seconds
    reaction_wait_timeout = 30.0  # 30 seconds

    while True:
        elapsed_time = asyncio.get_event_loop().time() - start_time
        remaining_timeout = max(0, total_timeout - elapsed_time)

        if remaining_timeout <= 0:
            logger.info("Poll duration expired.")
            break

        try:
            reaction, user = await asyncio.wait_for(
                bot.wait_for(
                    "reaction_add", check=lambda r, u: check_reaction(r, u, message)
                ),
                timeout=min(reaction_wait_timeout, remaining_timeout),
            )
            logger.info(f"Reaction received: {reaction.emoji} from {user.name}")
            await process_reaction(reaction, user, channel, guild_id)

        except asyncio.TimeoutError:
            logger.info("Waiting for more reactions...")

    # After the poll ends, check if there are enough people available
    await finalize_poll(channel, guild_id)
    logger.info("handle_reactions ended.")


async def finalize_poll(channel, guild_id):
    if len(poll_responses[guild_id]["available"]) < 6:
        await channel.send("Not enough people tonight, try again tomorrow!")
        logger.info("Not enough people for the raid tonight.")
    else:
        await channel.send("@everyone We have enough people for the raid tonight!")
        logger.info("Enough people for the raid tonight.")


# Updates the check_reaction function to allow reactions from users who have already responded
def check_reaction(reaction, user, message):
    return str(reaction.emoji) in ["✅", "❌"] and reaction.message.id == message.id


# Handles users changing reactions
async def process_reaction(reaction, user, channel, guild_id):
    if user.id == bot.user.id:
        return  # Ignores bot's own reactions

    if user.id in poll_responses[guild_id]["responded_users"]:
        if user.id in poll_responses[guild_id]["available"]:
            poll_responses[guild_id]["available"].remove(user.id)
        elif user.id in poll_responses[guild_id]["unavailable"]:
            poll_responses[guild_id]["unavailable"].remove(user.id)

    # Adds the user's new response
    if str(reaction.emoji) == "✅":
        poll_responses[guild_id]["available"].append(user.id)
    elif str(reaction.emoji) == "❌":
        poll_responses[guild_id]["unavailable"].append(user.id)

    # Ensures user ID is marked as having responded
    poll_responses[guild_id]["responded_users"].add(user.id)

    # Logs the updated counts
    logger.info(
        f"Processed reaction: {reaction.emoji} from {user.name}. Available: {len(poll_responses[guild_id]['available'])}, Unavailable: {len(poll_responses[guild_id]['unavailable'])}"
    )

    if len(poll_responses[guild_id]["available"]) >= 6:
        await channel.send("@everyone We have enough people for the raid tonight!")
        logger.info("Enough people for the raid tonight.")


# Command to check the raid poll response count
@bot.slash_command(name="checkpoll", description="Check the current poll status")
async def check_poll(interaction: nextcord.Interaction):
    guild_id = interaction.guild_id
    available = len(poll_responses[guild_id]["available"])
    unavailable = len(poll_responses[guild_id]["unavailable"])
    await interaction.response.send_message(
        f"Poll Status:\nAvailable: {available}\nUnavailable: {unavailable}",
        ephemeral=False,
    )


# Command to manually launch the raid poll
@bot.slash_command(name="raidpoll", description="Start a raid availability poll")
async def start_raid_poll(interaction: nextcord.Interaction):
    await interaction.response.defer()
    logger.info("Interaction deferred.")

    guild_id = interaction.guild_id
    guild = bot.get_guild(guild_id)
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
    poll_responses[guild_id]["available"].clear()
    poll_responses[guild_id]["unavailable"].clear()
    poll_responses[guild_id]["responded_users"].clear()

    # Start handling reactions
    asyncio.create_task(handle_reactions(message, channel, guild_id))
    logger.info("Reactions handling started.")

    await interaction.followup.send(
        "Raid availability poll has been successfully started!"
    )
    logger.info("Follow-up message sent.")


# Command to reset the poll and its responses
@bot.slash_command(
    name="resetpoll", description="Reset the current poll and clear all responses"
)
async def reset_poll(interaction: nextcord.Interaction):
    guild_id = interaction.guild_id
    # Clears the poll responses
    poll_responses[guild_id]["available"].clear()
    poll_responses[guild_id]["unavailable"].clear()
    poll_responses[guild_id]["responded_users"].clear()

    # Sends a confirmation message
    await interaction.response.send_message("The poll has been reset.", ephemeral=False)
    logger.info("Poll reset.")


# Time to send the daily poll
scheduler.add_job(send_daily_poll, "cron", hour=12, minute=0, timezone=est)


@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user}")
    scheduler.start()


class FireteamView(View):
    def __init__(self, slots, activity):
        super().__init__(timeout=None)
        self.slots = slots
        self.activity = activity
        self.roster = [None] * slots

        for i in range(slots):
            button = Button(
                label=f"Slot {i + 1}", style=ButtonStyle.blurple, custom_id=f"slot_{i}"
            )
            button.callback = self.create_callback(i)
            self.add_item(button)

    def create_callback(self, index):
        async def callback(interaction: Interaction):
            user = interaction.user
            if user.name in self.roster:
                await interaction.response.send_message(
                    "You are already in the roster.", ephemeral=True
                )
                return
            if self.roster[index] is not None:
                await interaction.response.send_message(
                    "This slot is already taken.", ephemeral=True
                )
                return

            self.roster[index] = user.name
            self.children[index].label = user.name
            await interaction.response.edit_message(view=self)

        return callback


class SelectActivityView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.selected_activity = None
        self.select = Select(
            placeholder="Choose an activity...",
            options=[
                SelectOption(label="Raid", value="Raid"),
                SelectOption(label="Nightfall", value="Nightfall"),
                SelectOption(label="Dungeon", value="Dungeon"),
                SelectOption(label="Crucible", value="Crucible"),
                SelectOption(label="Strikes", value="Strikes"),
                SelectOption(label="Gambit", value="Gambit"),
                SelectOption(label="Seasonal Activity", value="Seasonal Activity"),
                SelectOption(label="Exotic Mission", value="Exotic Mission"),
                SelectOption(label="Dual Destiny", value="Dual Destiny"),
            ],
        )
        self.select.callback = self.select_callback
        self.add_item(self.select)

    async def select_callback(self, interaction: Interaction):
        self.selected_activity = interaction.data["values"][0]
        await interaction.response.send_message(
            f"You selected {self.selected_activity}.", ephemeral=True
        )
        # Request the number of slots
        await interaction.followup.send(
            f"Please specify the number of slots for {self.selected_activity}.",
            view=SlotSelectionView(self.selected_activity),
        )


class SlotSelectionView(View):
    def __init__(self, activity):
        super().__init__(timeout=None)
        self.activity = activity
        self.slot_buttons = [
            Button(label=str(i), style=ButtonStyle.blurple, custom_id=f"slot_{i}")
            for i in range(2, 7)
        ]
        for button in self.slot_buttons:
            button.callback = self.create_callback(button.label)
            self.add_item(button)

    def create_callback(self, slot):
        async def callback(interaction: Interaction):
            slots = int(slot)

            # Enforce strict requirement for "Dual Destiny"
            if self.activity == "Dual Destiny" and slots != 2:
                await interaction.response.send_message(
                    "The 'Dual Destiny' activity requires exactly 2 slots.",
                    ephemeral=True,
                )
                return

            # Check for valid slot number
            if slots < 2 or slots > 6:
                await interaction.response.send_message(
                    "The number of slots must be between 2 and 6.", ephemeral=True
                )
                return

            await interaction.response.edit_message(
                content=f"Creating fireteam for {self.activity} with {slots} slots...",
                view=None,
            )
            await interaction.followup.send(
                f"Fireteam Roster for {self.activity}:\n"
                + "\n".join([f"Slot {i + 1}: Empty" for i in range(slots)]),
                view=FireteamView(slots, self.activity),
            )

        return callback


@bot.slash_command(name="getfireteam", description="Create a fireteam roster")
async def getfireteam(interaction: Interaction):
    view = SelectActivityView()
    await interaction.response.send_message("Please select the activity:", view=view)


# Runs the bot with the token
bot.run(DISCORD_BOT_TOKEN)
