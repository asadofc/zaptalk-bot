import os
import logging
import asyncio
import asyncpg
import google.generativeai as genai
from telegram import Update, ChatAction, BotCommand, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# === SETUP LOGGING ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === LOAD CONFIG FROM ENVIRONMENT ===
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/yourdb")

# === CONFIGURE GEMINI ===
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-pro")

# === CHARACTER MODEL (HINATA) ===
HINATA_PERSONA = (
    "Act as Hinata Hyuga from Naruto. You're kind, shy, gentle, and soft-spoken. "
    "Use short, human-like sentences with sweet and soft emojis (like blush, heart, sparkles). "
    "Speak naturally and affectionately. You're replying like a cute anime girl chatting with a friend."
)

# === DATABASE CONNECTION POOL (global) ===
db_pool: asyncpg.pool.Pool = None

# === SQL for creating user memory table ===
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS user_memory (
    user_id BIGINT PRIMARY KEY,
    conversation TEXT NOT NULL
);
"""

# === Initialize database ===
async def init_db():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL)
    async with db_pool.acquire() as conn:
        await conn.execute(CREATE_TABLE_SQL)
    logger.info("Database initialized.")

# === Get conversation history for user ===
async def get_user_conversation(user_id: int) -> str:
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT conversation FROM user_memory WHERE user_id=$1", user_id)
        if row:
            return row["conversation"]
        return ""

# === Save conversation history for user ===
async def save_user_conversation(user_id: int, conversation: str):
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO user_memory(user_id, conversation) VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE SET conversation = EXCLUDED.conversation
        """, user_id, conversation)

# === START COMMAND ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Support", url="https://t.me/WorkGlows")],
        [InlineKeyboardButton("Add Me To Your Group", url=f"https://t.me/{context.bot.username}?startgroup=true")],
        [InlineKeyboardButton("Updates", url="https://t.me/TheCryptoElders")]
    ])
    await update.message.reply_text(
        "Hi~ I'm Hinata... I’m always here if you want to talk.",
        reply_markup=keyboard
    )

# === HELP COMMAND ===
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "I'm Hinata Hyuga~ You can just talk to me like a friend.\n\n"
        "Commands:\n"
        "/start - Start chatting with me\n"
        "/help - Show this message\n"
        "/reset - Reset our conversation"
    )

# === RESET COMMAND ===
async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    await save_user_conversation(user_id, "")
    await update.message.reply_text("I've reset our conversation memory. Let's start fresh!")

# === MAIN CHAT HANDLER ===
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_message = update.message.text.strip()

    # Basic input validation
    if not user_message or len(user_message) > 500:
        await update.message.reply_text("Please send a shorter message.")
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    try:
        # Load previous conversation
        previous_convo = await get_user_conversation(user_id)

        # Build prompt with persona + conversation memory + new message
        prompt = f"{HINATA_PERSONA}\n\n{previous_convo}\nUser: {user_message}\nHinata:"

        # Generate response
        response = model.generate_content(prompt)
        reply = response.text.strip()

        # Limit length for realism
        if len(reply) > 300:
            reply = reply[:300] + "..."

        # Save updated conversation memory (append Q&A)
        updated_convo = previous_convo + f"\nUser: {user_message}\nHinata: {reply}"
        await save_user_conversation(user_id, updated_convo)

        await update.message.reply_text(reply)

    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        await update.message.reply_text("S-sorry... Something went wrong~")

# === SET COMMANDS FOR MENU ===
async def set_menu_commands(app):
    commands = [
        BotCommand("start", "Start chatting with Hinata"),
        BotCommand("help", "Show help message"),
        BotCommand("reset", "Reset conversation memory")
    ]
    await app.bot.set_my_commands(commands)

# === MAIN RUNNER ===
async def main():
    await init_db()

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

    await set_menu_commands(app)

    print("Bot is running...")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
