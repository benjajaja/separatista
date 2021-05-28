import os
from telegram import Update, MessageEntity
from telegram.ext import Updater, CommandHandler, CallbackContext, MessageHandler, Filters
import redis
import json

updater = Updater(os.getenv("SEPARATIST_TOKEN"))

r = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6366"), decode_responses=True)
print(f"links_users: {json.dumps(r.hgetall('links_users'))}")
print(f"links_from: {json.dumps(r.hgetall('links_from'))}")

def hello(update: Update, context: CallbackContext) -> None:
    update.message.reply_text(f'Hello {update.effective_user.first_name}')
updater.dispatcher.add_handler(CommandHandler('hello', hello))

def link(update: Update, context: CallbackContext) -> None:
    group_id = r.hget("links_users", update.effective_user.id)
    if group_id is None:
        r.hset("links_users", str(update.effective_user.id), str(update.effective_chat.id))
        update.message.reply_text(f'Group ID {update.effective_chat.id} is ready to be linked to by you in another group chat.')
    else:
        if int(group_id) == update.effective_chat.id:
            update.message.reply_text(f'Already awaiting linkage by you in another group.')
            return
        elif get_fork_chat(update.effective_chat.id) is not None:
            update.message.reply_text(f'Already linked from.')
            return
        elif get_base_chat(update.effective_chat.id) is not None:
            update.message.reply_text(f'Already linked to.')
            return

        r.hset("links_from", group_id, update.effective_chat.id)
        r.hdel("links_users", str(update.effective_user.id))
        update.message.reply_text(f'Linked this chat ({update.effective_chat.id}) as separatist of {group_id}!')
        context.bot.send_message(chat_id=group_id,
                text=f"Link to separatist chat successful!")

updater.dispatcher.add_handler(CommandHandler('link', link))

def unlink(update: Update, context: CallbackContext) -> None:
    group_id = r.hget("links_users", update.effective_user.id)
    if group_id is not None:
        r.hdel("links_users", str(update.effective_user.id))
        update.message.reply_text(f'Your link petition has been removed.')
    else:
        if r.hexists("links_from", update.effective_chat.id):
            r.hdel("links_from", update.effective_chat.id)
            update.message.reply_text(f'This group has been unlinked.')
        else:
            update.message.reply_text(f'This group is not being forwarded - do you meant to unlink the source chat group?')

updater.dispatcher.add_handler(CommandHandler('unlink', unlink))


def get_fork_chat(id):
    return r.hget("links_from", id)

def get_base_chat(id):
    values = r.hgetall("links_from")
    inv_map = {v: k for k, v in values.items()}
    return inv_map.get(str(id))


FORWARDS_EXPIRY = 604800
def forward(update, context):
    if update.message is None:
        return

    if get_fork_chat(update.effective_chat.id) is not None and update.message.message_id is not None:
        fork = get_fork_chat(update.effective_chat.id)
        message = context.bot.forward_message(chat_id=fork,
                from_chat_id=update.effective_chat.id,
                message_id=update.message.message_id)
        r.setex("forwards:" + fork + ":" + str(message.message_id),
                FORWARDS_EXPIRY,
                str(update.message.message_id) + ":" + str(update.effective_chat.id))

    elif (update.message.reply_to_message is not None
        and update.message.reply_to_message.from_user.id == context.bot.id
        and update.message.reply_to_message.forward_date is not None):
        forward = r.get("forwards:" + str(update.effective_chat.id) + ":" + str(update.message.reply_to_message.message_id))
        if forward is not None:
            split = forward.split(":")
            if len(split) == 2:
                forward_message_id = int(split[0])
                base_chat_id = int(split[1])
                if forward_message_id:
                    context.bot.send_message(chat_id=base_chat_id,
                            text=format_fwd(update.effective_message.text, update.effective_user),
                            reply_to_message_id=forward_message_id)
                    return

        context.bot.send_message(chat_id=get_base_chat(update.effective_chat.id),
                text=format_fwd(update.effective_message.text, update.effective_user))
    else:
        base_chat_id = get_base_chat(update.effective_chat.id)
        if (base_chat_id is not None
            and update.message.text is not None
            and update.message.text.startswith("!")):
            context.bot.send_message(chat_id=base_chat_id,
                    text=format_fwd(update.effective_message.text[1:], update.effective_user))

def format_fwd(text, user):
    return f"{update.effective_message.text}\n    --{update.effective_user.username if update.effective_user.username is not None else update.effective_user.first_name}, in the separatist group ☭ https://t.me/joinchat/1hWbLIeq-CcyMWFk"

updater.dispatcher.add_handler(MessageHandler((~Filters.command), forward))


def force_forward(update: Update, context: CallbackContext) -> None:
    #  update.message.reply_text(f'Hello {update.effective_user.first_name}')
    base_chat_id = get_base_chat(update.effective_chat.id)
    if base_chat_id is None:
        update.message.reply_text(f'This is not a separatist chat.')
        return
    context.bot.forward_message(chat_id=base_chat_id,
            from_chat_id=update.effective_chat.id,
            message_id=update.message.message_id)

updater.dispatcher.add_handler(CommandHandler('f', force_forward))

if os.getenv("PORT") is None:
    updater.start_polling()
    print("bot started polling.")
else:
    updater.start_webhook(listen="0.0.0.0",
                          port=int(os.environ.get('PORT', '8443')),
                          url_path=os.getenv("SEPARATIST_TOKEN"))
    updater.bot.set_webhook("https://" + os.environ.get("HEROKU_APP_NAME") + ".herokuapp.com/" + os.getenv("SEPARATIST_TOKEN"))
    print("bot started webhook.")
updater.idle()

