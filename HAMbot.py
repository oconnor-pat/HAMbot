import asyncio
import json
import os
import random
import requests
import html
from dotenv import load_dotenv
import nextcord
from nextcord.ext import commands

# Load env variables
load_dotenv()
GUILD_ID = int(os.getenv("GUILD_ID"))  # Ensure GUILD_ID is an integer if it's numeric
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

intents = nextcord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


def generate_question(
    category=None,
    id=None,
    tags=None,
    difficulty=None,
    regions=None,
    isNiche=None,
    type=None,
):
    # Parameters for the question
    params = {
        "category": category,
        "id": id,
        "tags": tags,
        "difficulty": difficulty,
        "regions": regions,
        "isNiche": isNiche,
        "type": type,
    }

    response = requests.get("https://the-trivia-api.com/v2/questions", params=params)

    print(f"Response status code: {response.status_code}")
    print(f"Response text: {response.text}")

    try:
        response.raise_for_status()
        # Parse the JSON response
        data = response.json()
    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred: {http_err}")
        return None, None, None
    except requests.exceptions.RequestException as err:
        print(f"An error occurred: {err}")
        return None, None, None
    except json.JSONDecodeError:
        print("Invalid JSON received")
        return None, None, None

    print(f"Response data: {data}")  # Print the entire data list

    # Check if data is empty
    if not data:
        print("No questions found.")
        return None, None, None

    # Extract question and correct answer from the first question in the list
    first_question = data[0]
    question_text = first_question.get("question", {}).get("text")
    correct_answer = first_question.get("correctAnswer")
    incorrect_answers = first_question.get("incorrectAnswers", [])

    return question_text, correct_answer, incorrect_answers


@bot.slash_command(name="trivia", description="Start a trivia game")
async def trivia_command(interaction: nextcord.Interaction):
    question, correct_answer, incorrect_answers = generate_question()
    if not question:
        await interaction.response.send_message(
            "Sorry, no trivia question available at the moment.", ephemeral=True
        )
        return

    all_answers = incorrect_answers + [correct_answer]
    random.shuffle(all_answers)  # Shuffle the answers

    # Unescape HTML entities in the question and answers
    question = html.unescape(question)
    all_answers = [html.unescape(answer) for answer in all_answers]
    correct_answer = html.unescape(correct_answer)

    # Assign each answer to a letter
    answer_dict = {chr(65 + i): answer for i, answer in enumerate(all_answers)}

    content = f"Trivia Question: {question}\n"
    for letter, answer in answer_dict.items():
        content += f"{letter}: {answer}\n"

    await interaction.response.send_message(content=content, ephemeral=False)

    answered_users = set()

    def check(m):
        return (
            m.channel == interaction.channel
            and m.content.strip().upper() in answer_dict.keys()
            and m.author.id not in answered_users
        )

    while True:
        try:
            print("Waiting for user's response...")
            response = await bot.wait_for("message", check=check, timeout=60.0)
            print(f"User's response: {response.content}")
            user_answer = answer_dict.get(response.content.upper())
            if user_answer == correct_answer:
                await response.channel.send(f"{response.author.mention}, correct!")
            else:
                await response.channel.send(
                    f"{response.author.mention}, sorry, the correct answer was {correct_answer}."
                )

            answered_users.add(response.author.id)
        except asyncio.TimeoutError:
            print("TimeoutError")
            await interaction.channel.send("Time's up!")
            break


@bot.event
async def on_ready():
    print("Logged in as", bot.user)


bot.run(DISCORD_BOT_TOKEN)
