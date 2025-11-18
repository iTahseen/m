import asyncio
import aiohttp
import random
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.client.default import DefaultBotProperties
from motor.motor_asyncio import AsyncIOMotorClient

BOT_TOKEN = "8300519461:AAGub3h_FqGkggWkGGE95Pgh8k4u6deI_F4"
MONGO_URI = "mongodb+srv://itxcriminal:qureshihashmI1@cluster0.jyqy9.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"

user_tokens = {}
matching_tasks = {}
user_stats = {}

mongo = AsyncIOMotorClient(MONGO_URI)
db = mongo["meeff_db"]
config = db["config"]

bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()


# ========================= HANDLERS =========================

async def start(message: types.Message):
    await message.answer("Send Meeff Token.")

async def set_url(message: types.Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.answer("Please provide a URL.")
    url = parts[1].strip()
    if not url.startswith("https://"):
        return await message.answer("Invalid URL.")
    await config.update_one({"_id": "explore_url"}, {"$set": {"url": url}}, upsert=True)
    await message.answer("✔️ URL saved.")

async def stop(message: types.Message):
    chat_id = message.chat.id
    task = matching_tasks.pop(chat_id, None)
    if task:
        task.cancel()
        keyboard = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Start Matching")]], resize_keyboard=True)
        await message.answer("Stopped.", reply_markup=keyboard)
    else:
        await message.answer("Not running.")

async def start_matching_btn(message: types.Message):
    chat_id = message.chat.id
    if chat_id not in user_tokens:
        return await message.answer("Send token first.")
    data = await config.find_one({"_id": "explore_url"})
    if not data:
        return await message.answer("Use /seturl first.")
    explore_url = data["url"]
    token = user_tokens[chat_id]

    keyboard = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Stop Matching")]], resize_keyboard=True)
    await message.answer("Matching Started...", reply_markup=keyboard)

    task = asyncio.create_task(start_matching(chat_id, token, explore_url))
    matching_tasks[chat_id] = task

async def receive_token(message: types.Message):
    chat_id = message.chat.id
    if message.text.startswith("/") or message.text in ["Start Matching", "Stop Matching"]:
        return
    if chat_id in user_tokens:
        return await message.answer("Token already saved.")

    user_tokens[chat_id] = message.text.strip()
    keyboard = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Start Matching")]], resize_keyboard=True)
    await message.answer("✔️ Token saved.", reply_markup=keyboard)


# ========================= REGISTER HANDLERS =========================
def register_handlers():
    dp.message.register(start, Command("start"))
    dp.message.register(set_url, Command("seturl"))
    dp.message.register(stop, Command("stop"))
    dp.message.register(start_matching_btn, F.text == "Start Matching")
    dp.message.register(receive_token, F.text)


# ========================= RUN BOT =========================
async def main():
    register_handlers()         # <--- IMPORTANT!
    print("Bot is running...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
