import discord
from discord.ext import commands
import random
import asyncio
import os
import certifi
import requests
import html
from dotenv import load_dotenv

# Load the environment variables
load_dotenv()

# Set the path to the SSL certificate
os.environ['SSL_CERT_FILE'] = certifi.where()

# Intents for the bot
intents = discord.Intents.default()
intents.message_content = True

# Initialize the bot
bot = commands.Bot(command_prefix='/', intents=intents)

# Function to generate a random trivia question
def generate_question():
    response = requests.get("https://opentdb.com/api.php?amount=1&")
    response.raise_for_status()
    data = response.json()
    return data['results'][0]

# Command to start a trivia question
@bot.command()
async def trivia(ctx):
    question_data = generate_question()
    question = html.unescape(question_data['question'])
    correct_answer = html.unescape(question_data['correct_answer'])

    await ctx.send(f"Trivia Question: {question}")

    # List of users that have answered the question
    answered_users = []

    # Function to check if the message is from the user
    def check(m):
        return m.author not in answered_users and m.channel == ctx.channel
    
    # Wait for user input
    while True:
        try:
            msg = await bot.wait_for('message', check=check, timeout=60.0)
        except asyncio.TimeoutError:
            await ctx.send("Sorry, you took too long to answer.")
            break
        else:
            answered_users.append(msg.author)
            if msg.content.lower() == correct_answer.lower():
                await ctx.send("Correct!")
            else:
                await ctx.send(f"Incorrect!: The correct answer is: {correct_answer}")
            return

# Run the bot
bot.run(os.getenv('DISCORD_BOT_TOKEN'))
