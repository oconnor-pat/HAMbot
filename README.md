# HAMbot

This Discord bot helps manage raid availability polls by sending daily poll messages and tracking user responses. The bot is built using Nextcord and APScheduler and can be customized to work with multiple Discord servers.

Features
Sends a daily raid availability poll to a specified channel.
Tracks user responses to the poll (Available or Unavailable).
Allows users to change their responses.
Automatically notifies when enough people are available for a raid.
Provides slash commands to start a new poll, check the current poll status, and reset the poll.

Requirements
Python 3.8+
nextcord
python-dotenv
apscheduler

Installation
Clone the repository:

git clone https://github.com/yourusername/raid-availability-bot.git
cd raid-availability-bot
Create and activate a virtual environment:

python -m venv venv
source venv/bin/activate # On Windows, use `venv\Scripts\activate`
Install the required packages:

pip install -r requirements.txt

Create a .env file in the root directory and add your Discord bot token and guild IDs:

DISCORD_BOT_TOKEN=your_bot_token
GUILD_IDS=guild_id1,guild_id2

Usage
Run the bot:

python bot.py
The bot will log in and start sending daily polls at 12:00 PM server time.

Users can respond to the poll by reacting with ✅ for Available and ❌ for Unavailable.

The bot will track responses and notify the channel when enough people are available for a raid.

Commands
Slash Commands
/checkpoll - Check the current poll status.
/raidpoll - Start a raid availability poll manually.
/resetpoll - Reset the current poll and clear all responses.

Code Overview
python3 HAMbot.py: The main script that runs the bot.

Poll responses are tracked in a dictionary with lists for available and unavailable users.
The bot uses Nextcord's event loop and reaction handling to manage poll responses.
APScheduler is used to schedule the daily poll.

Logging
The bot logs important events and errors using Python's logging module. Logs include information about reactions, poll status, and any issues encountered while sending messages or handling reactions.
