import asyncio
import aiohttp
import random
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient

###########################################
#   CONFIG
###########################################

BOT_TOKEN = "8300519461:AAGub3h_FqGkggWkGGE95Pgh8k4u6deI_F4"     # ← Replace
MONGO_URI = "mongodb+srv://itxcriminal:qureshihashmI1@cluster0.jyqy9.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"

# Temporary memory storage (token NOT saved in DB)
user_tokens = {}  # key = chat_id | value = Meeff Token

# MongoDB connection
mongo = AsyncIOMotorClient(MONGO_URI)
db = mongo["meeff_db"]
config = db["config"]

###########################################
#   BOT SETUP
###########################################

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

###########################################
#   MEEFF FUNCTIONS
###########################################

HEADERS_TEMPLATE = {
    "User-Agent": "okhttp/5.1.0 (Linux; Android 13; Pixel 6 Build/TQ3A.230901.001)",
    "Accept-Encoding": "gzip",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
    "Host": "api.meeff.com",
}

ANSWER_URL = "https://api.meeff.com/user/undoableAnswer/v5/?userId={user_id}&isOkay=1"


async def fetch_users(session, explore_url):
    try:
        async with session.get(explore_url) as res:
            print(f"[EXPLORE] Status: {res.status}")
            if res.status == 200:
                data = await res.json(content_type=None)
                return data.get("users", [])
            return []
    except Exception as e:
        print(f"Fetch users error: {e}")
        return []


async def answer_user(session, user_id):
    url = ANSWER_URL.format(user_id=user_id)
    try:
        async with session.get(url) as res:
            print(f"[ANSWER] {user_id}: {res.status}")
    except Exception as e:
        print(f"Answer user error({user_id}): {e}")


async def start_matching(token, explore_url):
    headers = HEADERS_TEMPLATE.copy()
    headers["meeff-access-token"] = token

    cycle = 0
    timeout = aiohttp.ClientTimeout(total=30)
    connector = aiohttp.TCPConnector(ssl=False, limit_per_host=10)

    async with aiohttp.ClientSession(timeout=timeout, connector=connector, headers=headers) as session:
        while True:
            users = await fetch_users(session, explore_url)
            if not users:
                print("No users found, retrying...")
                await asyncio.sleep(1)
                continue

            print(f"Fetched {len(users)} users")

            tasks = []
            for user in users:
                user_id = user.get("_id")
                if user_id:
                    tasks.append(answer_user(session, user_id))
                    await asyncio.sleep(random.uniform(0.05, 0.2))

                if len(tasks) >= 10:
                    await asyncio.gather(*tasks)
                    tasks.clear()

            if tasks:
                await asyncio.gather(*tasks)

            cycle += 1
            print(f"Completed cycle: {cycle}")
            await asyncio.sleep(random.uniform(1.0, 2.0))


###########################################
#   HANDLERS
###########################################

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("👋 *Send Meeff Token to continue!*", parse_mode="Markdown")


@dp.message(Command("seturl"))
async def set_url(message: types.Message):
    url = message.text.replace("/seturl", "").strip()
    if not url.startswith("https://"):
        return await message.answer("❌ Invalid URL!")

    await config.update_one({"_id": "explore_url"}, {"$set": {"url": url}}, upsert=True)
    await message.answer("✅ Explore URL saved!")


@dp.message(Command("geturl"))
async def get_url(message: types.Message):
    data = await config.find_one({"_id": "explore_url"})
    if not data:
        return await message.answer("❌ No URL set yet.")
    await message.answer(f"🌍 URL:\n`{data['url']}`", parse_mode="Markdown")


@dp.message(F.text == "🔥 Start Matching")
async def start_matching_btn(message: types.Message):
    chat_id = message.chat.id
    if chat_id not in user_tokens:
        return await message.answer("❌ Send Meeff token first!")

    token = user_tokens[chat_id]
    data = await config.find_one({"_id": "explore_url"})
    if not data:
        return await message.answer("❌ No Explore URL set! Use /seturl <url>")

    explore_url = data["url"]
    await message.answer("🚀 Starting matching now...")
    asyncio.create_task(start_matching(token, explore_url))


@dp.message(F.text)
async def receive_token(message: types.Message):
    chat_id = message.chat.id

    if chat_id not in user_tokens:
        user_tokens[chat_id] = message.text.strip()

        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="🔥 Start Matching")]],
            resize_keyboard=True
        )
        return await message.answer("✔ Token received!\nPress button to start.", reply_markup=keyboard)

    await message.answer("✔ Token already saved. Use the button below.")


###########################################
#   RUN BOT
###########################################

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
