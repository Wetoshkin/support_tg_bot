import logging

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# --- IMPORTANT ---
# Replace these placeholder values with your actual Bot Token and Group ID.
# Do NOT commit this file with your real credentials.
TELEGRAM_BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN_HERE"
SUPPORT_GROUP_ID = "YOUR_SUPPORT_GROUP_ID_HERE"
# -----------------

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# In-memory storage for user-to-thread mapping and ticket counting.
# For a production bot, consider using a database.
user_threads = {}  # {user_id: thread_id}
ticket_counter = 0


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message when the /start command is issued."""
    user = update.effective_user
    await update.message.reply_html(
        rf"Здравствуйте, {user.mention_html()}! Я бот технической поддержки. Отправьте мне свой вопрос, и я создам для вас тикет.",
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming messages for ticket creation and forwarding."""
    message = update.message
    chat_id = message.chat_id
    user = update.effective_user

    # Handle messages from users in private chat
    if chat_id > 0:  # User chats have positive IDs
        thread_id = user_threads.get(chat_id)

        # If no thread exists, create one
        if thread_id is None:
            try:
                global ticket_counter
                ticket_counter += 1

                topic = await context.bot.create_forum_topic(
                    chat_id=SUPPORT_GROUP_ID,
                    name=f"Тикет #{ticket_counter} - {user.full_name}",
                )
                thread_id = topic.message_thread_id
                user_threads[chat_id] = thread_id
                await context.bot.send_message(
                    chat_id=SUPPORT_GROUP_ID,
                    text=f"New ticket #{ticket_counter} from {user.mention_html()} (ID: {user.id})",
                    message_thread_id=thread_id,
                )
                await message.reply_text(
                    "Спасибо! Ваш тикет создан. Специалист поддержки скоро свяжется с вами."
                )
            except Exception as e:
                logger.error(f"Failed to create topic for user {chat_id}: {e}")
                await message.reply_text(
                    "К сожалению, не удалось создать тикет. Пожалуйста, попробуйте еще раз позже."
                )
                return

        # Forward user's message to the group thread
        try:
            await context.bot.forward_message(
                chat_id=SUPPORT_GROUP_ID,
                from_chat_id=chat_id,
                message_id=message.message_id,
                message_thread_id=thread_id,
            )
        except Exception as e:
            logger.error(
                f"Failed to forward message from user {chat_id} to thread {thread_id}: {e}"
            )

    # Handle messages from the support group
    elif str(chat_id) == str(SUPPORT_GROUP_ID):
        thread_id = message.message_thread_id
        if thread_id:
            # Find the user this thread belongs to
            user_id_to_reply = None
            for uid, tid in user_threads.items():
                if tid == thread_id:
                    user_id_to_reply = uid
                    break

            if user_id_to_reply:
                # Avoid echoing bot's own messages
                if message.from_user.is_bot:
                    return

                # Don't forward the /close command to the user
                if message.text and message.text.startswith("/close"):
                    return

                try:
                    # Forward the message (text, photo, document, etc.)
                    await context.bot.copy_message(
                        chat_id=user_id_to_reply,
                        from_chat_id=chat_id,
                        message_id=message.message_id,
                    )
                except Exception as e:
                    logger.error(
                        f"Failed to forward message from thread {thread_id} to user {user_id_to_reply}: {e}"
                    )


async def close_ticket(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Closes a ticket (topic) in the support group."""
    chat_id = update.message.chat_id
    thread_id = update.message.message_thread_id

    if str(chat_id) != str(SUPPORT_GROUP_ID) or not thread_id:
        await update.message.reply_text(
            "Эта команда может быть использована только в теме тикета в группе поддержки."
        )
        return

    # Find the user this thread belongs to
    user_id_to_notify = None
    for uid, tid in user_threads.items():
        if tid == thread_id:
            user_id_to_notify = uid
            break

    try:
        await context.bot.close_forum_topic(
            chat_id=SUPPORT_GROUP_ID, message_thread_id=thread_id
        )
        await context.bot.send_message(
            chat_id=SUPPORT_GROUP_ID,
            text=f"Тикет #{thread_id} был закрыт пользователем {update.effective_user.mention_html()}.",
            message_thread_id=thread_id,
        )

        if user_id_to_notify:
            del user_threads[user_id_to_notify]
            await context.bot.send_message(
                chat_id=user_id_to_notify,
                text="Ваш тикет был закрыт. Если у вас есть другие вопросы, просто отправьте новое сообщение!",
            )

    except Exception as e:
        logger.error(f"Failed to close topic {thread_id}: {e}")
        await update.message.reply_text(f"Failed to close ticket: {e}")


def main() -> None:
    """Start the bot."""
    # Create the Application and pass it your bot's token.
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # on different commands - answer in Telegram
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("close", close_ticket))

    # on non command i.e message - echo the message on Telegram
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )
    application.add_handler(MessageHandler(filters.PHOTO, handle_message))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_message))

    # Start the Bot
    application.run_polling()


if __name__ == "__main__":
    main()
