import os
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext, MessageHandler, Filters
import redis
import json

updater = Updater(os.getenv("SEPARATIST_TOKEN"))

r = redis.Redis(host='localhost', port=os.getenv("SEPARATIST_REDIS_PORT", 6366), db=0, decode_responses=True)
print(f"redis: {json.dumps(r.hgetall('links_users'))}")

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

def get_fork_chat(id):
    return r.hget("links_from", id)

def get_base_chat(id):
    values = r.hgetall("links_from")
    inv_map = {v: k for k, v in values.items()}
    return inv_map.get(id)


def forward(update, context):
    if get_fork_chat(update.effective_chat.id) is not None and update.message.message_id is not None:
        fork = get_fork_chat(update.effective_chat.id)
        message = context.bot.forward_message(chat_id=fork,
                from_chat_id=update.effective_chat.id,
                message_id=update.message.message_id)
        r.hset("forwards:" + fork, message.message_id, str(update.message.message_id) + ":" + str(update.effective_chat.id))

    elif (update.message.reply_to_message is not None
        and update.message.reply_to_message.from_user.id == context.bot.id
        and update.message.reply_to_message.forward_date is not None):
        forward = r.hget("forwards:" + str(update.effective_chat.id), update.message.reply_to_message.message_id)
        if forward is not None:
            split = forward.split(":")
            if len(split) == 2:
                forward_message_id = int(split[0])
                base_chat_id = int(split[1])
                if forward_message_id:
                    context.bot.send_message(chat_id=base_chat_id,
                            text=f"{update.effective_message.text}\n    --{update.effective_user.first_name}, in the separatist group ☭",
                            reply_to_message_id=forward_message_id)
                    return

        context.bot.send_message(chat_id=get_base_chat(update.effective_chat.id),
                text=f"[unmatched forward] {'@' + update.effective_user.username if update.effective_user.username else update.effective_user.first_name} (in the separatist group):\n{update.effective_message.text}")
    else:
        print(f"Unlinked message / not a target: {update.effective_chat.id}")


updater.dispatcher.add_handler(MessageHandler((~Filters.command), forward))

updater.start_polling()
print("bot started.")
updater.idle()

