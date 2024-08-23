import os
import random
import aiohttp
import nextcord
from nextcord.ext import commands
from nextcord import Interaction, ButtonStyle, SelectOption
from nextcord.ui import Button, View, Select
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import asyncio
import logging
from dotenv import load_dotenv
from pytz import timezone
import logging

# Loads environment variables from the appropriate .env file
env_file = ".env.prod" if os.getenv("ENV") == "production" else ".env.test"
load_dotenv(env_file)

# Environment Variables
APPLICATION_ID = os.getenv("APPLICATION_ID")
GUILD_IDS = [
    int(guild_id.strip()) for guild_id in os.getenv("GUILD_IDS", "").split(",")
]

HAKUNA_AHAMKARA = GUILD_IDS[0]
WHAT_CAN_MEN_DO = (
    GUILD_IDS[1] if len(GUILD_IDS) > 1 else GUILD_IDS[0]
)  # Defaults to the first guild if only one is available

TEST_GUILD = GUILD_IDS[0]
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

print("Loaded ENV:", os.getenv("ENV"))
print("DISCORD_BOT_TOKEN:", os.getenv("DISCORD_BOT_TOKEN"))
print("GUILD_IDS:", os.getenv("GUILD_IDS"))
print("APPLICATION_ID:", os.getenv("APPLICATION_ID"))
print("First GUILD_ID:", WHAT_CAN_MEN_DO)


# Config logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Intents and Bot Initialization
intents = nextcord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Scheduler Setup
scheduler = AsyncIOScheduler()
est = timezone("US/Eastern")

# Poll responses storage
poll_responses = {
    guild_id: {
        "available": [],
        "unavailable": [],
        "could_be_convinced": [],
        "responded_users": set(),
    }
    for guild_id in GUILD_IDS
}


async def fetch_trivia_question():
    url = "https://the-trivia-api.com/api/questions"  # API endpoint to fetch questions
    params = {
        "limit": 1,  # Fetch only one question per call
        "difficulty": "easy",  # Specify the difficulty if required
        "categories": "general",  # Specify the category if required
    }
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if (
                        data and isinstance(data, list) and len(data) > 0
                    ):  # Check if data is not empty and correctly formatted
                        return data[0]  # Return the first question object
                    else:
                        logging.error("No data returned from the trivia API.")
                        return None
                else:
                    logging.error(
                        f"Failed to fetch trivia question, HTTP status: {response.status}"
                    )
                    return None
        except Exception as e:
            logging.error(
                f"An error occurred while fetching the trivia question: {str(e)}"
            )
            return None


# Function to send the daily poll
async def send_daily_poll():

    # Server ID for Hakuna Ahamkara
    guild_id = WHAT_CAN_MEN_DO

    guild = bot.get_guild(guild_id)
    if guild is None:
        logger.error(f"Guild with ID {guild_id} not found")
        return

    channel = nextcord.utils.get(guild.text_channels, name="general")
    if channel is None:
        logger.error(f"Channel 'general' not found in guild ID {guild_id}")
        return

    message = await channel.send(
        "Availability for raid tonight:\nReact with ✅ for Available, ❌ for Unavailable, or 🤷 if you could be convinced."
    )
    await message.add_reaction("✅")
    await message.add_reaction("❌")
    await message.add_reaction("🤷")

    # Reset poll responses
    poll_responses[guild_id] = {
        "available": [],
        "unavailable": [],
        "could_be_convinced": [],
        "responded_users": set(),
    }

    # Start handling reactions
    asyncio.create_task(handle_reactions(message, channel, guild_id))


# Check if the reaction is valid
def check_reaction(reaction, user, message):
    return (
        str(reaction.emoji) in ["✅", "❌", "🤷"] and reaction.message.id == message.id
    )


# Processes each user's response to the poll
async def handle_reactions(message, channel, guild_id):
    logger.info("Handling reactions started.")
    start_time = asyncio.get_event_loop().time()
    total_timeout = 18000.0  # 5 hours in seconds

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
                timeout=min(30.0, remaining_timeout),
            )
            logger.info(f"Reaction received: {reaction.emoji} from {user.name}")
            await process_reaction(reaction, user, channel, guild_id)

        except asyncio.TimeoutError:
            logger.info("Waiting for more reactions...")

    # After the poll ends, this closes it and announces the results
    await finalize_poll(channel, guild_id)
    logger.info("Handling reactions ended.")


# Finalize the poll results
async def finalize_poll(channel, guild_id):
    available_count = len(poll_responses[guild_id]["available"])
    could_be_convinced_count = len(poll_responses[guild_id]["could_be_convinced"])

    # count for available and could be convinced responses added together
    total_possible = available_count + could_be_convinced_count

    if total_possible < 6:
        await channel.send("**Not enough people tonight, try again tomorrow!**")
        logger.info("Not enough people for the raid tonight.")
    else:
        await channel.send("**@everyone We have enough people for the raid tonight!**")
        logger.info("Enough people for the raid tonight.")


# Check if the reaction is valid
async def process_reaction(reaction, user, channel, guild_id):
    if user.id == bot.user.id:
        return  # Ignores bot's own reactions

    # Ensure user can only have one reaction
    if user.id in poll_responses[guild_id]["responded_users"]:
        # Remove the user's old response
        old_emoji = None
        if user.id in poll_responses[guild_id]["available"]:
            old_emoji = "✅"
            poll_responses[guild_id]["available"].remove(user.id)
        elif user.id in poll_responses[guild_id]["unavailable"]:
            old_emoji = "❌"
            poll_responses[guild_id]["unavailable"].remove(user.id)
        elif user.id in poll_responses[guild_id]["could_be_convinced"]:
            old_emoji = "🤷"
            poll_responses[guild_id]["could_be_convinced"].remove(user.id)

        # Remove old reaction from the message
        if old_emoji:
            await reaction.message.remove_reaction(old_emoji, user)

    # Add the user's new response
    if str(reaction.emoji) == "✅":
        poll_responses[guild_id]["available"].append(user.id)
    elif str(reaction.emoji) == "❌":
        poll_responses[guild_id]["unavailable"].append(user.id)
    elif str(reaction.emoji) == "🤷":
        poll_responses[guild_id]["could_be_convinced"].append(user.id)

    # Ensure user ID is marked as having responded
    poll_responses[guild_id]["responded_users"].add(user.id)

    # Logs the updated counts
    available_count = len(poll_responses[guild_id]["available"])
    unavailable_count = len(poll_responses[guild_id]["unavailable"])
    could_be_convinced_count = len(poll_responses[guild_id]["could_be_convinced"])
    logger.info(
        f"Processed reaction: {reaction.emoji} from {user.name}. Available: {available_count}, Unavailable: {unavailable_count}, Could be convinced: {could_be_convinced_count}"
    )

    # Notify if enough people are available
    if available_count >= 6:
        await channel.send("@everyone We have enough people for the raid tonight!")
        logger.info("Enough people for the raid tonight.")


# Command to check the raid poll response count
@bot.slash_command(
    name="checkpoll",
    description="Check the current poll status",
    guild_ids=[HAKUNA_AHAMKARA],
)
async def check_poll(interaction: nextcord.Interaction):
    guild_id = interaction.guild_id
    available = len(poll_responses.get(guild_id, {}).get("available", []))
    unavailable = len(poll_responses.get(guild_id, {}).get("unavailable", []))
    could_be_convinced = len(
        poll_responses.get(guild_id, {}).get("could_be_convinced", [])
    )
    logger.info(
        f"Checking poll status: Available: {available}, Unavailable: {unavailable}, Could be convinced: {could_be_convinced}"
    )
    await interaction.response.send_message(
        f"Poll Status:\nAvailable: {available}\nUnavailable: {unavailable}\nCould be convinced: {could_be_convinced}",
        ephemeral=False,
    )


# Command to manually launch the raid poll
@bot.slash_command(
    name="raidpoll",
    description="Start a raid availability poll",
    guild_ids=[HAKUNA_AHAMKARA],
)
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
        "React with ✅ for Available, ❌ for Unavailable, or 🤷 for Could be convinced."
    )
    message = await channel.send(message_content)
    await message.add_reaction("✅")
    await message.add_reaction("❌")
    await message.add_reaction("🤷")
    logger.info("Poll message sent and reactions added.")

    # Reset poll responses
    poll_responses[guild_id] = {
        "available": [],
        "unavailable": [],
        "could_be_convinced": [],
        "responded_users": set(),
    }

    # Start handling reactions
    asyncio.create_task(handle_reactions(message, channel, guild_id))
    logger.info("Reactions handling started.")

    await interaction.followup.send(
        "Raid availability poll has been successfully started!"
    )
    logger.info("Follow-up message sent.")


# Command to manually finalize the poll
@bot.slash_command(
    name="finalize_poll",
    description="Finalize the current raid poll",
    guild_ids=[HAKUNA_AHAMKARA],
)
async def finalize_poll_command(interaction: nextcord.Interaction):
    guild_id = interaction.guild_id
    channel = nextcord.utils.get(interaction.guild.text_channels, name="general")
    if channel:
        # Finalize the poll and send the results to the channel
        await finalize_poll(channel, guild_id)
        await interaction.response.send_message(
            "Poll has been closed, results are:", ephemeral=False
        )
    else:
        await interaction.response.send_message(
            "Channel 'general' not found.", ephemeral=True
        )


# Command to reset the poll and its responses
@bot.slash_command(
    name="resetpoll",
    description="Reset the current poll and its responses",
    guild_ids=[HAKUNA_AHAMKARA],
)
async def reset_poll(interaction: Interaction):
    guild_id = interaction.guild_id
    # Clears the poll responses
    poll_responses[guild_id] = {
        "available": [],
        "unavailable": [],
        "could_be_convinced": [],
        "responded_users": set(),
    }

    # Sends a confirmation message
    await interaction.response.send_message("The poll has been reset.", ephemeral=False)
    logger.info("Poll reset.")


# Time to send the daily poll
scheduler.add_job(send_daily_poll, "cron", hour=12, minute=0, timezone=est)


@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user}")
    logger.info(f"Connected guilds: {[guild.id for guild in bot.guilds]}")
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

            # Enforces strict requirement for "Dual Destiny"
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


@bot.slash_command(
    name="getfireteam",
    description="Create a fireteam roster",
    guild_ids=[HAKUNA_AHAMKARA],
)
async def getfireteam(interaction: Interaction):
    view = SelectActivityView()
    await interaction.response.send_message("Please select the activity:", view=view)


# What can men do against such reckless hate server slash commands
@bot.slash_command(
    name="trivia",
    description="Start a trivia game!",
    guild_ids=[
        WHAT_CAN_MEN_DO,
        TEST_GUILD,
    ],  # Ensures it's available only in specified guilds
)
async def trivia(interaction: nextcord.Interaction):
    question_data = await fetch_trivia_question()
    if not question_data:
        await interaction.response.send_message(
            "Failed to fetch trivia question, please try again later.", ephemeral=True
        )
        return

    print(question_data)

    # Extracts question and answers from the question_data
    question = question_data["question"]
    correct_answer = question_data["correctAnswer"]
    incorrect_answers = question_data["incorrectAnswers"]

    # Shuffles and prepares choices for display
    choices = [correct_answer] + incorrect_answers
    random.shuffle(choices)  # Randomizes the order of choices

    # Creates a formatted string of choices
    answer_text = "\n".join(
        [f"{idx + 1}. {choice}" for idx, choice in enumerate(choices)]
    )
    await interaction.response.send_message(f"{question}\n{answer_text}")

    # Function to check if the response is from any user in the same channel who responded to the question
    def check(m):
        return m.channel == interaction.channel and m.author != bot.user

    try:
        # Waits for a message from any user
        user_message = await bot.wait_for(
            "message", check=check, timeout=60.0
        )  # 60 seconds to respond
        user_answer = user_message.content.strip()

        # Checks if the answer is correct
        if user_answer.lower() in [
            str(choices.index(correct_answer) + 1),
            correct_answer.lower(),
        ]:
            await interaction.followup.send(
                f"{user_message.author.mention} Correct! 🎉", ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"{user_message.author.mention} Incorrect! The correct answer was {correct_answer}.",
                ephemeral=True,
            )
    except asyncio.TimeoutError:
        await interaction.followup.send(
            "Sorry, time's up! No one responded in time.", ephemeral=False
        )


# Runs the bot with the token
bot.run(DISCORD_BOT_TOKEN)
