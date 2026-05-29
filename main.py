import os
import requests
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from web_server import keep_alive
import database as db

# --- Anilist Fetcher (No API Key Required) ---
def get_anilist_info(query):
    gql_query = """
    query ($search: String) {
      Media (search: $search, type: ANIME) {
        title { english romaji }
        description
        averageScore
        genres
        bannerImage
      }
    }
    """
    url = 'https://graphql.anilist.co'
    response = requests.post(url, json={'query': gql_query, 'variables': {'search': query}})
    if response.status_code == 200:
        return response.json()['data']['Media']
    return None

# --- Formatting Helper ---
def format_post(name, ep, info, links):
    desc = info['description'].replace('<br>', '').replace('<i>', '').replace('</i>', '')
    # Hide half of synopsis
    mid = len(desc) // 2
    synopsis = f"{desc[:mid]}||{desc[mid:]}||"
    
    # Text in Bold as requested
    text = (
        f"<b>{name} Episode {ep}</b>\n"
        f"⟣────────────────────⟢\n"
        f"<b>‣ Audio ⌯ [Chinese | Eng-Sub]</b>\n"
        f"<b>‣ Rating ⌯ {info['averageScore']/10} IMDB</b>\n"
        f"<b>‣ Quality ⌯ 480p | 720p | 1080p</b>\n"
        f"<b>‣ Episode ⌯ {ep}</b>\n"
        f"<b>‣ Genres ⌯ {', '.join(['#'+g for g in info['genres']])}</b>\n"
        f"⟣────────────────────⟢\n"
        f"<b>‣ Synopsis ⌯</b>\n"
        f"<b>{synopsis}</b>\n\n"
        f"🔗 <b>Our Network @Donghua_Xin</b>"
    )
    
    # Create buttons from links
    keyboard = []
    link_pairs = re.findall(r'(\d+p)\s*:\s*(https?://\S+)', links)
    for q, l in link_pairs:
        keyboard.append([InlineKeyboardButton(f"🚀 {q} Download", url=l)])
    
    return text, InlineKeyboardMarkup(keyboard)

# --- Bot Commands ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("<b>Welcome! Use /addchannel to setup and /post to create.</b>", parse_mode='HTML')

async def add_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        return await update.message.reply_text("<b>Usage: /addchannel -100123456 NameTag</b>", parse_mode='HTML')
    c_id, tag = context.args[0], " ".join(context.args[1:])
    db.save_channel(update.effective_user.id, c_id, tag)
    await update.message.reply_text(f"<b>Channel {tag} added!</b>", parse_mode='HTML')

async def post_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Format: /post Name | Ep | ImgLink | Links (480p: url 720p: url)
    try:
        parts = update.message.text.split('|')
        name, ep, img, links = parts[0].replace('/post', '').strip(), parts[1].strip(), parts[2].strip(), parts[3].strip()
        
        info = db.get_anime_data(name)
        if not info:
            info = get_anilist_info(name)
            db.save_anime_data(name, info)
        
        text, markup = format_post(name, ep, info, links)
        context.user_data['pending_post'] = (text, markup, img)
        
        # Show channel selection
        channels = db.get_channels(update.effective_user.id)
        buttons = [[InlineKeyboardButton(c['name'], callback_data=f"sel_{c['channel_id']}")] for c in channels]
        buttons.append([InlineKeyboardButton("✅ DONE", callback_data="done_post")])
        
        await update.message.reply_photo(photo=img, caption=text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode='HTML')
    except:
        await update.message.reply_text("<b>Error! Use: /post Name | Ep | Img | Quality: Link</b>", parse_mode='HTML')

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    if data.startswith("sel_"):
        cid = data.split("_")[1]
        selected = context.user_data.get('selected_channels', [])
        if cid in selected: selected.remove(cid)
        else: selected.append(cid)
        context.user_data['selected_channels'] = selected
        await query.answer("Channel Toggled")
        
    elif data == "done_post":
        text, markup, img = context.user_data['pending_post']
        for cid in context.user_data.get('selected_channels', []):
            await context.bot.send_photo(chat_id=cid, photo=img, caption=text, reply_markup=markup, parse_mode='HTML')
        await query.edit_message_caption("<b>✅ Posted successfully!</b>", parse_mode='HTML')

# --- Main Entry ---
if __name__ == '__main__':
    keep_alive() # Start Koyeb Health Check
    app = Application.builder().token(os.getenv("BOT_TOKEN")).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addchannel", add_channel))
    app.add_handler(CommandHandler("post", post_handler))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.run_polling()
