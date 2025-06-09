# Decode creds.json from base64 (Render deployment)
import os
import base64

creds_b64 = os.getenv("GOOGLE_CREDENTIALS_B64")
if creds_b64:
    with open("creds.json", "wb") as f:
        f.write(base64.b64decode(creds_b64))

# BBS Telegram Bot - Full System with Admin Tools & Auto Refunds

import logging
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, ConversationHandler
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Google Sheets Setup
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("creds.json", scope)
client = gspread.authorize(creds)
sheet = client.open("BBS_UserData").sheet1
match_sheet = client.open("BBS_Matches").sheet1

# States
REGISTER_PHONE, MAIN_MENU = range(2)

# Environment
BOT_TOKEN = os.getenv("BOT_TOKEN")
NOWPAYMENTS_API_KEY = os.getenv("NOWPAYMENTS_API_KEY")
ADMIN_IDS = [123456789]  # Replace with actual admin user IDs

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.message.from_user
    keyboard = [[KeyboardButton(text="Send Phone Number", request_contact=True)]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text("Welcome to BBS! Please verify your phone number to continue:", reply_markup=reply_markup)
    return REGISTER_PHONE

async def phone_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    contact = update.message.contact
    user_id = update.message.from_user.id
    sheet.append_row([str(user_id), contact.phone_number, 0])  # 0 BBSCoin initial balance
    await update.message.reply_text("✅ Registration complete! Use /wallet or /matches to get started.")
    return MAIN_MENU

async def wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    records = sheet.get_all_records()
    for row in records:
        if str(row["user_id"]) == user_id:
            balance = row["balance"]
            await update.message.reply_text(f"💰 Your BBSCoin Balance: {balance}")
            return
    await update.message.reply_text("User not registered. Use /start first.")

async def buy_bbscoin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    amount_eur = 60
    headers = {"x-api-key": NOWPAYMENTS_API_KEY, "Content-Type": "application/json"}
    payload = {
        "price_amount": amount_eur,
        "price_currency": "eur",
        "pay_currency": "xmr",
        "order_id": str(user_id),
        "order_description": "Buy BBSCoin",
        "ipn_callback_url": "https://yourdomain.com/callback"
    }
    response = requests.post("https://api.nowpayments.io/v1/invoice", json=payload, headers=headers)
    invoice_url = response.json().get("invoice_url", "")
    await update.message.reply_text(f"💳 Pay here: {invoice_url}")

async def matches(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = match_sheet.get_all_records()
    keyboard = []
    for idx, match in enumerate(data):
        match_text = f"[{match['category']}] {match['title']} | Odds: {match['odds']} | Price: {match['price']} BBSCoin"
        keyboard.append([InlineKeyboardButton(match_text, callback_data=f"buy_{idx}")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Available Matches:", reply_markup=reply_markup)

async def match_buy_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    match_index = int(query.data.split("_")[1])
    data = match_sheet.get_all_records()
    match = data[match_index]

    user_id = str(query.from_user.id)
    user_data = sheet.get_all_records()
    for i, row in enumerate(user_data):
        if str(row["user_id"]) == user_id:
            balance = int(row["balance"])
            price = int(match["price"])
            if balance >= price:
                sheet.update_cell(i+2, 3, balance - price)
                await query.edit_message_text(f"✅ Match Purchased! You will receive your prediction shortly.")
            else:
                await query.edit_message_text(f"❌ Insufficient BBSCoin. Use /buy to top up.")
            return
    await query.edit_message_text("User not found. Use /start to register.")

async def mark_result(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Unauthorized access.")
        return
    try:
        match_id, result = context.args[0], context.args[1]
        row = int(match_id) + 2
        match_sheet.update_cell(row, 5, result)  # Assuming column E is result
        await update.message.reply_text(f"Result set for match {match_id}: {result}")

        if result == "❌":
            purchases = []  # Implement user-match tracking in extended version
            users = sheet.get_all_records()
            for i, user in enumerate(users):
                # Simulated: refund 20% to all users (actual logic needs match-user tracking)
                balance = int(user['balance'])
                refund = int(0.2 * 60)  # 60 assumed investment
                sheet.update_cell(i+2, 3, balance + refund)
            await update.message.reply_text("💸 Refunds processed.")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

# Main function
if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    reg_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            REGISTER_PHONE: [MessageHandler(filters.CONTACT, phone_received)]
        },
        fallbacks=[]
    )

    app.add_handler(reg_handler)
    app.add_handler(CommandHandler("wallet", wallet))
    app.add_handler(CommandHandler("buy", buy_bbscoin))
    app.add_handler(CommandHandler("matches", matches))
    app.add_handler(CallbackQueryHandler(match_buy_handler, pattern=r"^buy_\\d+$"))
    app.add_handler(CommandHandler("markresult", mark_result))

    print("Bot running...")
    app.run_polling()
