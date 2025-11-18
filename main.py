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

BOT_TOKEN = "8300519461:AAGub3h_FqGkggWkGGE95Pgh8k4u6deI_F4"  # YOUR BOT TOKEN
MONGO_URI = "mongodb+srv://itxcriminal:qureshihashmI1@cluster0.jyqy9.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"

user_tokens = {}            # Store Meeff token temporarily (only in memory)
matching_tasks = {}         # Track running matching tasks per user
user_stats = {}             # Live stats per user

# MongoDB setup
mongo = AsyncIOMotorClient(MONGO_URI)
db = mongo["meeff_db"]
config = db["config"]

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

###########################################
#   MEEFF MATCHING FUNCTIONS
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
    async with session.get(explore_url) as res:
        return res.status, await res.json(content_type=None) if res.status == 200 else None


async def start_matching(chat_id, token, explore_url):
    headers = HEADERS_TEMPLATE.copy()
    headers["meeff-access-token"] = token

    stats = {"requests": 0, "cycles": 0, "errors": 0}
    user_stats[chat_id] = stats

    try:
        timeout = aiohttp.ClientTimeout(total=30)
        connector = aiohttp.TCPConnector(ssl=False, limit_per_host=10)

        async with aiohttp.ClientSession(timeout=timeout, connector=connector, headers=headers) as session:
            while True:
                if chat_id not in matching_tasks:  # STOP signal
                    break

                status, data = await fetch_users(session, explore_url)

                if status == 401:  # TOKEN EXPIRED
                    await bot.send_message(chat_id, "❌ *Token expired — send a new Meeff token!*", parse_mode="Markdown")
                    matching_tasks.pop(chat_id, None)
                    user_tokens.pop(chat_id, None)
                    break

                if data is None or not data.get("users"):
                    await asyncio.sleep(1)
                    continue

                users = data.get("users", [])
                tasks = []

                for user in users:
                    user_id = user.get("_id")
                    if user_id:
                        tasks.append(session.get(ANSWER_URL.format(user_id=user_id)))
                        stats["requests"] += 1
                        await asyncio.sleep(random.uniform(0.05, 0.2))

                    if len(tasks) >= 10:
                        await asyncio.gather(*tasks)
                        tasks.clear()

                stats["cycles"] += 1

                # LIVE STATS
                msg = (
                    "📊 *Live Matching Stats*\n"
                    f"🚀 Requests Sent: `{stats['requests']}`\n"
                    f"🔄 Cycles: `{stats['cycles']}`\n"
                    f"⚠ Errors: `{stats['errors']}`"
                )
                try:
                    await bot.send_message(chat_id, msg, parse_mode="Markdown")
                except:
                    pass

                await asyncio.sleep(random.uniform(1.0, 2.0))

    except Exception as e:
        stats["errors"] += 1
        await bot.send_message(chat_id, f"⚠ ERROR: `{e}`", parse_mode="Markdown")


###########################################
#   TELEGRAM HANDLERS
###########################################

@dp.message(Command("start"))
async def start_handler(message: types.Message):
    await message.answer("👋 *Send Meeff token to continue!*", parse_mode="Markdown")


@dp.message(Command("seturl"))
async def set_url(message: types.Message):
    url = message.text.replace("/seturl", "").strip()
    if not url.startswith("https://"):
        return await message.answer("❌ Invalid URL format.")
    await config.update_one({"_id": "explore_url"}, {"$set": {"url": url}}, upsert=True)
    await message.answer("✅ URL saved!")


@dp.message(Command("geturl"))
async def get_url(message: types.Message):
    data = await config.find_one({"_id": "explore_url"})
    if not data:
        return await message.answer("❌ No URL set yet.")
    await message.answer(f"🌍 Explore URL:\n`{data['url']}`", parse_mode="Markdown")


@dp.message(Command("stop"))
async def stop_matching(message: types.Message):
    chat_id = message.chat.id
    task = matching_tasks.pop(chat_id, None)
    if task:
        task.cancel()
        await message.answer("🛑 Matching Stopped.")
    else:
        await message.answer("⚠ No matching is running.")


@dp.message(F.text == "🔥 Start Matching")
async def start_matching_btn(message: types.Message):
    chat_id = message.chat.id
    if chat_id not in user_tokens:
        return await message.answer("❌ Send Meeff token first.")

    token = user_tokens[chat_id]
    data = await config.find_one({"_id": "explore_url"})
    if not data:
        return await message.answer("❌ Use /seturl <url> first.")

    explore_url = data["url"]
    await message.answer("🚀 Matching started!")
    task = asyncio.create_task(start_matching(chat_id, token, explore_url))
    matching_tasks[chat_id] = task


@dp.message(F.text)
async def token_receiver(message: types.Message):
    chat_id = message.chat.id
    if chat_id in user_tokens:
        return await message.answer("✔ Token already saved.")

    user_tokens[chat_id] = message.text.strip()

    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔥 Start Matching")], [KeyboardButton(text="/stop")]],
        resize_keyboard=True
    )
    await message.answer("✔ Token received!", reply_markup=keyboard)


###########################################
#   RUN BOT
###########################################

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
