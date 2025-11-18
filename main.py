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

BOT_TOKEN = "8300519461:AAGub3h_FqGkggWkGGE95Pgh8k4u6deI_F4"
MONGO_URI = "mongodb+srv://itxcriminal:qureshihashmI1@cluster0.jyqy9.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"

# Temporary storage
user_tokens = {}
matching_tasks = {}
user_stats = {}

# MongoDB
mongo = AsyncIOMotorClient(MONGO_URI)
db = mongo["meeff_db"]
config = db["config"]

# Telegram Bot
bot = Bot(BOT_TOKEN)
dp = Dispatcher()

###########################################
#   MEEFF API FUNCTIONS
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
        status = res.status

        if status != 200:
            try:
                error_text = await res.text()
                print("\n========= MEEFF ERROR =========")
                print(f"STATUS  : {status}")
                print(f"RESPONSE:\n{error_text}")
                print("================================\n")
            except:
                print(f"[Non-JSON Error] Status: {status}")

            return status, None

        data = await res.json(content_type=None)
        return status, data


async def start_matching(chat_id, token, explore_url):
    headers = HEADERS_TEMPLATE.copy()
    headers["meeff-access-token"] = token

    stats = {"requests": 0, "cycles": 0, "errors": 0}
    user_stats[chat_id] = stats

    stat_message = await bot.send_message(chat_id, "🚀 Matching started...")

    empty_count = 0
    timeout = aiohttp.ClientTimeout(total=30)
    connector = aiohttp.TCPConnector(ssl=False, limit_per_host=10)

    # Change button to STOP
    stop_keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🛑 Stop Matching")]],
        resize_keyboard=True
    )
    await bot.send_message(chat_id, "🛑 Matching in progress...", reply_markup=stop_keyboard)

    try:
        async with aiohttp.ClientSession(timeout=timeout, connector=connector, headers=headers) as session:
            while chat_id in matching_tasks:
                status, data = await fetch_users(session, explore_url)

                if status == 401:
                    await stat_message.edit_text("❌ Token expired! Send a new token.")
                    break

                if data is None or not data.get("users"):
                    empty_count += 1
                    if empty_count >= 5:
                        await stat_message.edit_text("⚠ No users found. Stopping.")
                        break
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

                await stat_message.edit_text(
                    f"📊 *Live Stats:*\n"
                    f"🚀 Requests: `{stats['requests']}`\n"
                    f"🔄 Cycles: `{stats['cycles']}`\n"
                    f"⚠ Errors: `{stats['errors']}`\n\n"
                    f"🛑 Send /stop or press stop button.",
                    parse_mode="Markdown"
                )

                await asyncio.sleep(random.uniform(1, 2))

    except Exception as e:
        stats["errors"] += 1
        await stat_message.edit_text(f"⚠ ERROR: `{e}`", parse_mode="Markdown")

    # Reset buttons after stop
    start_keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔥 Start Matching")]],
        resize_keyboard=True
    )
    await bot.send_message(chat_id, "🛑 Matching stopped.", reply_markup=start_keyboard)
    matching_tasks.pop(chat_id, None)
    user_tokens.pop(chat_id, None)


###########################################
#   COMMAND HANDLERS
###########################################

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("👋 Send Meeff Token to continue.")


@dp.message(Command("seturl"))
async def set_url(message: types.Message):
    url = message.text.replace("/seturl", "").strip()
    if not url.startswith("https://"):
        return await message.answer("❌ Invalid URL")
    await config.update_one({"_id": "explore_url"}, {"$set": {"url": url}}, upsert=True)
    await message.answer("✔ URL Saved!")


@dp.message(Command("stop"))
@dp.message(F.text == "🛑 Stop Matching")
async def stop(message: types.Message):
    chat_id = message.chat.id
    task = matching_tasks.pop(chat_id, None)

    if task:
        task.cancel()
        await message.answer("🛑 Matching Stopped.")

        start_keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="🔥 Start Matching")]],
            resize_keyboard=True
        )
        await message.answer("Ready to start again.", reply_markup=start_keyboard)
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
        return await message.answer("❌ Use /seturl first.")

    explore_url = data["url"]

    await message.answer("🚀 Starting matching...")
    task = asyncio.create_task(start_matching(chat_id, token, explore_url))
    matching_tasks[chat_id] = task


@dp.message(F.text)
async def receive_token(message: types.Message):
    chat_id = message.chat.id
    if chat_id in user_tokens:
        return await message.answer("✔ Token already saved.")
    
    user_tokens[chat_id] = message.text.strip()
    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔥 Start Matching")]],
        resize_keyboard=True
    )
    await message.answer("✔ Token saved!", reply_markup=keyboard)


###########################################
#   RUN BOT
###########################################

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
