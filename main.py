import asyncio
import aiohttp
import random
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient

BOT_TOKEN = "8300519461:AAGub3h_FqGkggWkGGE95Pgh8k4u6deI_F4"
MONGO_URI = "mongodb+srv://itxcriminal:qureshihashmI1@cluster0.jyqy9.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"

user_tokens = {}
matching_tasks = {}
user_stats = {}

mongo = AsyncIOMotorClient(MONGO_URI)
db = mongo["meeff_db"]
config = db["config"]

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

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
        text = await res.text()
        if status != 200:
            print("\n=========== MEEFF EXPLORE ERROR ==========")
            print(f"STATUS      : {status}")
            print(f"RESPONSE    : {text}")
            print("==========================================\n")
            return status, text, None
        try:
            data = await res.json(content_type=None)
        except Exception as e:
            print(f"[EXPLORE JSON ERROR] {e}")
            return status, text, None
        return status, text, data


async def start_matching(chat_id, token, explore_url):
    headers = HEADERS_TEMPLATE.copy()
    headers["meeff-access-token"] = token

    stats = {"requests": 0, "cycles": 0, "errors": 0}
    user_stats[chat_id] = stats

    stat_msg = await bot.send_message(chat_id, "⏳ Starting matching...")

    timeout = aiohttp.ClientTimeout(total=30)
    connector = aiohttp.TCPConnector(ssl=False, limit_per_host=10)
    empty_count = 0
    stop_reason = None

    try:
        async with aiohttp.ClientSession(timeout=timeout, connector=connector, headers=headers) as session:

            async def answer_user(user_id):
                nonlocal stop_reason
                try:
                    async with session.get(ANSWER_URL.format(user_id=user_id)) as res:
                        text = await res.text()
                        print(f"[ANSWER] {user_id}: {res.status}")
                        print(text)
                        if res.status == 429 or "LikeExceeded" in text:
                            stop_reason = "limit"
                            return False
                        if res.status == 401 or "AuthRequired" in text:
                            stop_reason = "token"
                            return False
                        return True
                except Exception as e:
                    print(f"[ANSWER ERROR] {user_id}: {e}")
                    stats["errors"] += 1
                    return True

            while chat_id in matching_tasks:
                status, raw_text, data = await fetch_users(session, explore_url)
                print(f"[EXPLORE] Status: {status}")

                if status == 401 or "AuthRequired" in str(raw_text):
                    stop_reason = "token"
                    break

                if data is None or not data.get("users"):
                    empty_count += 1
                    if empty_count >= 6:
                        stop_reason = "empty"
                        break
                    await asyncio.sleep(1)
                    continue

                empty_count = 0
                users = data.get("users", [])
                tasks = []
                results = []

                for user in users:
                    user_id = user.get("_id")
                    if not user_id:
                        continue
                    task = asyncio.create_task(answer_user(user_id))
                    tasks.append(task)
                    stats["requests"] += 1
                    await asyncio.sleep(random.uniform(0.05, 0.2))

                    if len(tasks) >= 10:
                        batch_results = await asyncio.gather(*tasks)
                        results.extend(batch_results)
                        tasks.clear()
                        if False in batch_results:
                            break

                if tasks:
                    batch_results = await asyncio.gather(*tasks)
                    results.extend(batch_results)

                if False in results:
                    break

                stats["cycles"] += 1

                await stat_msg.edit_text(
                    f"📊 *Live Stats:*\n"
                    f"🚀 Requests: `{stats['requests']}`\n"
                    f"🔄 Cycles: `{stats['cycles']}`\n"
                    f"⚠ Errors: `{stats['errors']}`\n\n"
                    f"🛑 Send /stop or press button.",
                    parse_mode="Markdown"
                )

                await asyncio.sleep(random.uniform(1, 2))

    except Exception as e:
        print(f"[MATCHING ERROR] {e}")
        try:
            await stat_msg.edit_text(f"🔥 ERROR: `{e}`", parse_mode="Markdown")
        except:
            pass

    if stop_reason == "limit":
        text = "⚠ Daily like limit reached! Try again tomorrow."
    elif stop_reason == "token":
        text = "❌ Token expired. Send a new token."
    elif stop_reason == "empty":
        text = "⚠ No users found repeatedly. Stopping."
    else:
        text = "🛑 Matching stopped."

    keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔥 Start Matching")]],
        resize_keyboard=True
    )
    try:
        await stat_msg.edit_text(text, parse_mode="Markdown")
    except:
        await bot.send_message(chat_id, text, reply_markup=keyboard)
    else:
        await bot.send_message(chat_id, "Ready again.", reply_markup=keyboard)

    matching_tasks.pop(chat_id, None)
    user_tokens.pop(chat_id, None)


@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("👋 Send Meeff Token to begin.")


@dp.message(Command("seturl"))
async def set_url(message: types.Message):
    url = message.text.replace("/seturl", "").strip()
    if not url.startswith("https://"):
        return await message.answer("❌ Invalid URL!")
    await config.update_one({"_id": "explore_url"}, {"$set": {"url": url}}, upsert=True)
    await message.answer("✔ URL Saved!")


@dp.message(Command("stop"))
@dp.message(F.text == "🛑 Stop Matching")
async def stop(message: types.Message):
    chat_id = message.chat.id
    task = matching_tasks.pop(chat_id, None)
    if task:
        task.cancel()
        keyboard = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🔥 Start Matching")]], resize_keyboard=True)
        await message.answer("🛑 Matching stopped.", reply_markup=keyboard)
    else:
        await message.answer("⚠ No matching running.")


@dp.message(F.text == "🔥 Start Matching")
async def start_matching_btn(message: types.Message):
    chat_id = message.chat.id
    if chat_id not in user_tokens:
        return await message.answer("❌ Send Meeff token first.")
    data = await config.find_one({"_id": "explore_url"})
    if not data:
        return await message.answer("❌ Use `/seturl <url>` first.")
    explore_url = data["url"]
    token = user_tokens[chat_id]
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


async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
