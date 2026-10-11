import asyncio
import os
import logging
import json
import sqlite3
import aiohttp
import threading
import uuid

from flask import Flask
from dotenv import load_dotenv

from datetime import datetime, timedelta
from typing import Optional, Any

from aiogram import Bot, Dispatcher, Router, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    BotCommand,
    LinkPreviewOptions,
)

from aiogram.utils.keyboard import InlineKeyboardBuilder

app = Flask(__name__)

@app.route('/')
def home():
    return "Escrow Bot is running live!"

@app.route('/health')
def health():
    return {"status": "online"}

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

flask_thread = threading.Thread(target=run_flask, daemon=True)
flask_thread.start()

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN missing from environment variables!")

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

MIDDLEMEN_IDS = [
    7913633925,
    8258524753,
    967359142,
    8421166266,
    8358390340
]

SUPPORT_ADMIN_ID = 7977452329

escrow_states = {}
admin_states = {}
deal_claims = {}

NET_DISPLAY = {
    "usdtbep20": "USDT BEP20",
    "usdterc20": "USDT ERC20",
    "usdttrc20": "USDT TRC20",
    "usdtsol": "USDT SOL",
    "usdcsol": "USDC SOL",
    "usdcerc20": "USDC ERC20",
    "solana": "Solana",
    "ethereum": "Ethereum",
    "bnbsmartchain": "BNB Smart Chain",
    "tron": "Tron",
    "litecoin": "Litecoin",
    "bitcoin": "Bitcoin",
    "gram": "Gram",
}

INR_FUND_DISPLAY = {
    "safe": "Safe Funds",
    "rat": "Rat Funds",
    "gaming": "Gaming Funds",
    "mix": "Mix Funds",
}

def crypto_buttons_selling(back_data):
    networks = [
        ("USDT BEP20", "usdtbep20", "5771530555048857288"),
        ("USDT ERC20", "usdterc20", "5769374258127965397"),
        ("USDT TRC20", "usdttrc20", "5771583477635877860"),
        ("USDT SOL", "usdtsol", "5771480514384891109"),
        ("USDC SOL", "usdcsol", "5771480514384891109"),
        ("USDC ERC20", "usdcerc20", "5769374258127965397"),
        ("Solana", "solana", "5771480514384891109"),
        ("Ethereum", "ethereum", "5769374258127965397"),
        ("BNB Smart Chain", "bnbsmartchain", "5771530555048857288"),
        ("Tron", "tron", "5771583477635877860"),
        ("Litecoin", "litecoin", "5771379449509448765"),
        ("Bitcoin", "bitcoin", "5771849507910192329"),
        ("Gram", "gram", "5886352111955878352"),
    ]

    builder = InlineKeyboardBuilder()
    for name, key, emoji_id in networks:
        builder.button(text=name, icon_custom_emoji_id=emoji_id, callback_data=f"sellnet_{key}")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="Back", icon_custom_emoji_id="5210952531676504517", callback_data=back_data))
    return builder.as_markup()

def crypto_buttons_paying(back_data):
    networks = [
        ("USDT BEP20", "usdtbep20", "5771530555048857288"),
        ("USDT ERC20", "usdterc20", "5769374258127965397"),
        ("USDT TRC20", "usdttrc20", "5771583477635877860"),
        ("USDT SOL", "usdtsol", "5771480514384891109"),
        ("USDC SOL", "usdcsol", "5771480514384891109"),
        ("USDC ERC20", "usdcerc20", "5769374258127965397"),
        ("Solana", "solana", "5771480514384891109"),
        ("Ethereum", "ethereum", "5769374258127965397"),
        ("BNB Smart Chain", "bnbsmartchain", "5771530555048857288"),
        ("Tron", "tron", "5771583477635877860"),
        ("Litecoin", "litecoin", "5771379449509448765"),
        ("Bitcoin", "bitcoin", "5771849507910192329"),
        ("Gram", "gram", "5886352111955878352"),
    ]

    builder = InlineKeyboardBuilder()
    for name, key, emoji_id in networks:
        builder.button(text=name, icon_custom_emoji_id=emoji_id, callback_data=f"paynet_{key}")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="Back", icon_custom_emoji_id="5210952531676504517", callback_data=back_data))
    return builder.as_markup()

async def get_usdt_inr_price():
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            url = "https://api.binance.com/api/v3/ticker/price?symbol=USDTINR"
            async with session.get(url) as resp:
                if resp.status == 200:
                    ticker = await resp.json()
                    rate = float(ticker["price"])
                    if rate > 0:
                        return rate
    except Exception as e:
        print(f"Binance price fetch error: {e}")
    return 83.0

@router.message(CommandStart())
async def escrow_start(message: Message, state: FSMContext):
    if message.chat.type != "private":
        return

    welcome_text = (
        '<b>Welcome to @middlescrowbot</b>\n\n'
        "Your trusted platform for secure P2P and OTC transactions on Telegram.\n\n"
        '<b><tg-emoji emoji-id="5904238507555033712">⛔️</tg-emoji> Trade safely. Avoid scams.</b>\n'
        "The bot connects you with the best available middleman for your transaction, "
        "helping ensure a safe and smooth deal.\n\n"
        '<tg-emoji emoji-id="5893473283696759404">💰</tg-emoji> <b>ESCROW FEE</b>\n'
        "• P2P: 1.0%\n"
        "• OTC: 2.0% flat\n\n"
        '<tg-emoji emoji-id="5902002809573740949">✅</tg-emoji> <b>Ready to trade?</b> Use /escrow to start a new escrow.\n\n'
        '<tg-emoji emoji-id="5902449142575141204">🔗</tg-emoji> Powered by @AFFUX.'
    )

    welcome_buttons = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Support",
                    icon_custom_emoji_id="5884510167986343350",
                    callback_data="menu_support"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Updates",
                    icon_custom_emoji_id="5771695636411847302",
                    url="https://t.me/AFFUX"
                ),
                InlineKeyboardButton(
                    text="Vouches",
                    icon_custom_emoji_id="5951665890079544884",
                    url="https://t.me/middlemaven"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Terms of Service",
                    icon_custom_emoji_id="5877597667231534929",
                    callback_data="menu_tos"
                )
            ]
        ]
    )

    await state.clear()
    await state.update_data(step="main")

    await message.answer(
        welcome_text,
        reply_markup=welcome_buttons,
        parse_mode=ParseMode.HTML,
        link_preview_options={"is_disabled": True}
    )

    type_text = (
        '🤝 <b>Please select your escrow type below:</b>\n\n'
        '<tg-emoji emoji-id="5832251986635920010">➡️</tg-emoji> <b>P2P</b> — Cryptocurrency Exchange Deals\n'
        '<tg-emoji emoji-id="5832251986635920010">➡️</tg-emoji> <b>POS</b> — Products, Services & NFTs'
    )
    type_buttons = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="P2P", callback_data="cat_p2p"),
                InlineKeyboardButton(text="POS", callback_data="cat_pos")
            ]
        ]
    )

    await message.answer(type_text, reply_markup=type_buttons, parse_mode=ParseMode.HTML)

@router.callback_query(F.data == "cat_p2p")
async def p2p_category(callback: CallbackQuery, state: FSMContext):
    await state.update_data(category="P2P", step="buyer_seller")
    text = "Are you the buyer or the seller?"
    buttons = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Buyer", callback_data="role_buyer"),
                InlineKeyboardButton(text="Seller", callback_data="role_seller")
            ],
            [
                InlineKeyboardButton(
                    text="Back",
                    icon_custom_emoji_id="5210952531676504517",
                    callback_data="back_to_escrow_type"
                )
            ]
        ]
    )
    await callback.message.edit_text(text, reply_markup=buttons, parse_mode=ParseMode.HTML)
    await callback.answer()

@router.callback_query(F.data == "cat_pos")
async def pos_category_handler(callback: CallbackQuery, state: FSMContext):
    await state.update_data(category="POS", step="select_currency_type")
    text = "Do you want to deal in <b>USD</b> or <b>INR</b>?"
    buttons = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="USD", callback_data="pos_curr_usd"),
                InlineKeyboardButton(text="INR", callback_data="pos_curr_inr")
            ],
            [
                InlineKeyboardButton(
                    text="Back",
                    icon_custom_emoji_id="5210952531676504517",
                    callback_data="back_to_escrow_type"
                )
            ]
        ]
    )
    await callback.message.edit_text(text, reply_markup=buttons, parse_mode=ParseMode.HTML)
    await callback.answer()

@router.callback_query(F.data.in_({"pos_curr_usd", "pos_curr_inr"}))
async def pos_currency_selection(callback: CallbackQuery, state: FSMContext):
    curr = callback.data.split("_")[2].upper()
    await state.update_data(currency_type=curr)

    if curr == "INR":
        await state.update_data(step="pos_inr_q1")
        text = (
            "<b>Question 1/3</b>\n\n"
            "What is the deal about? Describe the product or service."
        )
        buttons = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Back",
                        icon_custom_emoji_id="5210952531676504517",
                        callback_data="cat_pos"
                    )
                ]
            ]
        )
        await callback.message.edit_text(text, reply_markup=buttons, parse_mode=ParseMode.HTML)
    else:
        await state.update_data(step="select_usd_network")
        text = "Select USD / Crypto network for POS deal:"
        buttons = crypto_buttons_selling("cat_pos")
        await callback.message.edit_text(text, reply_markup=buttons, parse_mode=ParseMode.HTML)

    await callback.answer()

@router.callback_query(F.data.in_({"role_buyer", "role_seller"}))
async def role_selection(callback: CallbackQuery, state: FSMContext):
    role = callback.data.split("_")[1].capitalize()
    await state.update_data(category="P2P", role=role, step="select_selling_network")
    text = "What are you selling? Select network:"
    buttons = crypto_buttons_selling("back_to_role")
    await callback.message.edit_text(text, reply_markup=buttons, parse_mode=ParseMode.HTML)
    await callback.answer()

@router.message(F.text.regexp(r"^/escrow(?:@\w+)?$"))
async def escrow_command(message: Message, state: FSMContext):
    if message.chat.type != "private":
        return

    type_text = (
        '🤝 <b>Please select your escrow type below:</b>\n\n'
        '<tg-emoji emoji-id="5832251986635920010">➡️</tg-emoji> <b>P2P</b> — Cryptocurrency Exchange Deals\n'
        '<tg-emoji emoji-id="5832251986635920010">➡️</tg-emoji> <b>POS</b> — Products, Services & NFTs'
    )
    buttons = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="P2P", callback_data="cat_p2p"),
                InlineKeyboardButton(text="POS", callback_data="cat_pos")
            ]
        ]
    )

    await state.clear()
    await state.update_data(step="main")
    await message.answer(type_text, reply_markup=buttons, parse_mode=ParseMode.HTML)

@router.callback_query(F.data == "back_to_start")
async def back_to_start(callback: CallbackQuery, state: FSMContext):
    welcome_text = (
        '<b>Welcome to @middlescrowbot</b>\n\n'
        "Your trusted platform for secure P2P and OTC transactions on Telegram.\n\n"
        '<tg-emoji emoji-id="5904238507555033712">⛔</tg-emoji> <b>Trade safely. Avoid scams.</b>\n'
        "The bot connects you with the best available middleman for your transaction, "
        "helping ensure a safe and smooth deal.\n\n"
        '<tg-emoji emoji-id="5893473283696759404">💰</tg-emoji> <b>ESCROW FEE</b>\n'
        "• P2P: 1.0%\n"
        "• OTC: 2.0% flat\n\n"
        '<tg-emoji emoji-id="5902002809573740949">✅</tg-emoji> <b>Ready to trade?</b> Use /escrow to start a new escrow.\n\n'
        '<tg-emoji emoji-id="5902449142575141204">🔗</tg-emoji> Powered by @AFFUX.'
    )

    welcome_buttons = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Support",
                    icon_custom_emoji_id="5884510167986343350",
                    callback_data="menu_support"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Updates",
                    icon_custom_emoji_id="5771695636411847302",
                    url="https://t.me/AFFUX"
                ),
                InlineKeyboardButton(
                    text="Vouches",
                    icon_custom_emoji_id="5951665890079544884",
                    url="https://t.me/middlemaven"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Terms of Service",
                    icon_custom_emoji_id="5877597667231534929",
                    callback_data="menu_tos"
                )
            ]
        ]
    )

    await state.clear()
    await state.update_data(step="main")
    await callback.message.edit_text(welcome_text, reply_markup=welcome_buttons, parse_mode=ParseMode.HTML, link_preview_options={"is_disabled": True})
    await callback.answer()

@router.callback_query(F.data == "back_to_escrow_type")
async def back_to_escrow_type(callback: CallbackQuery, state: FSMContext):
    type_text = (
        '🤝 <b>Please select your escrow type below:</b>\n\n'
        '<tg-emoji emoji-id="5832251986635920010">➡️</tg-emoji> <b>P2P</b> — Cryptocurrency Exchange Deals\n'
        '<tg-emoji emoji-id="5832251986635920010">➡️</tg-emoji> <b>POS</b> — Products, Services & NFTs'
    )
    buttons = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="P2P", callback_data="cat_p2p"),
                InlineKeyboardButton(text="POS", callback_data="cat_pos")
            ]
        ]
    )

    await state.clear()
    await state.update_data(step="main")
    await callback.message.edit_text(type_text, reply_markup=buttons, parse_mode=ParseMode.HTML)
    await callback.answer()

@router.callback_query(F.data == "back_to_role")
async def back_to_role(callback: CallbackQuery, state: FSMContext):
    text = "Are you the buyer or the seller?"
    buttons = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Buyer", callback_data="role_buyer"),
                InlineKeyboardButton(text="Seller", callback_data="role_seller")
            ],
            [
                InlineKeyboardButton(
                    text="Back",
                    icon_custom_emoji_id="5210952531676504517",
                    callback_data="back_to_escrow_type"
                )
            ]
        ]
    )

    await state.update_data(category="P2P", step="buyer_seller")
    await callback.message.edit_text(text, reply_markup=buttons, parse_mode=ParseMode.HTML)
    await callback.answer()

@router.callback_query(F.data.startswith("sellnet_"))
async def sellnet_selection(callback: CallbackQuery, state: FSMContext):
    net_key = callback.data.replace("sellnet_", "")
    data = await state.get_data()
    category = data.get("category")
    sender_id = callback.from_user.id

    net_name = NET_DISPLAY.get(net_key, net_key.upper())

    if category == "POS":
        await state.update_data(paying_currency=net_name, step="pos_crypto_q1")
        escrow_states.setdefault(sender_id, {}).update({"paying_currency": net_name, "step": "pos_crypto_q1"})
        text = "<b>Question 1/3</b>\n\nWhat is the deal about? Describe the product or service."
        buttons = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Back",
                        icon_custom_emoji_id="5210952531676504517",
                        callback_data="cat_pos"
                    )
                ]
            ]
        )
        await callback.message.edit_text(text, reply_markup=buttons, parse_mode=ParseMode.HTML)
        await callback.answer()
        return

    await state.update_data(selling_currency=net_name, step="p2p_amount")
    escrow_states.setdefault(sender_id, {}).update({"selling_currency": net_name, "step": "p2p_amount"})
    text = f"Amount in <b>{net_name}</b>?"
    buttons = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Back",
                    icon_custom_emoji_id="5210952531676504517",
                    callback_data="back_to_role"
                )
            ]
        ]
    )
    await callback.message.edit_text(text, reply_markup=buttons, parse_mode=ParseMode.HTML)
    await callback.answer()

@router.callback_query(F.data.startswith("paynet_"))
async def paynet_selection(callback: CallbackQuery, state: FSMContext):
    net_key = callback.data.replace("paynet_", "")
    net_name = NET_DISPLAY.get(net_key, net_key.upper())

    await state.update_data(paying_currency=net_name, step="p2p_crypto_amount")
    text = f"Amount of {net_name} are you paying?"
    buttons = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Back",
                    icon_custom_emoji_id="5210952531676504517",
                    callback_data="back_to_payment"
                )
            ]
        ]
    )
    await callback.message.edit_text(text, reply_markup=buttons, parse_mode=ParseMode.HTML)
    await callback.answer()

@router.message(F.chat.type == "private", F.text, ~F.text.startswith("/"))
async def handle_all_text_inputs(message: Message, state: FSMContext):
    sender_id = message.from_user.id
    text_input = message.text.strip()

    if admin_states.get(sender_id, {}).get("step") == "waiting_support_reply":
        target_user = admin_states[sender_id]["target_user"]
        try:
            await bot.send_message(target_user, f'<tg-emoji emoji-id="5253742260054409879">✉️</tg-emoji> <b>Support Reply:</b>\n\n{text_input}', parse_mode=ParseMode.HTML)
            await message.answer('<tg-emoji emoji-id="5206607081334906820">✔️</tg-emoji> Reply sent to user!', parse_mode=ParseMode.HTML)
        except Exception as e:
            await message.answer(f'<tg-emoji emoji-id="5210952531676504517">❌</tg-emoji> Failed: {e}', parse_mode=ParseMode.HTML)
        admin_states.pop(sender_id, None)
        return

    if admin_states.get(sender_id, {}).get("step") == "waiting_group_link":
        group_link = text_input
        target_user = admin_states[sender_id]["target_user"]
        user_msg = f'<tg-emoji emoji-id="5902002809573740949">✅</tg-emoji> @affux escrow group for your deal is ready.\n\n{group_link}\n\nPlease share this with the other party.'
        try:
            await bot.send_message(target_user, user_msg, parse_mode=ParseMode.HTML)
            await message.answer('<tg-emoji emoji-id="5206607081334906820">✔️</tg-emoji> Group link successfully sent to the user!', parse_mode=ParseMode.HTML)
        except Exception as e:
            await message.answer(f'<tg-emoji emoji-id="5210952531676504517">❌</tg-emoji> Failed: {e}', parse_mode=ParseMode.HTML)
        admin_states.pop(sender_id, None)
        return

    if sender_id not in escrow_states:
        return

    current_step = escrow_states[sender_id].get("step")

    if current_step == "p2p_condition":
        condition = "None" if text_input.lower() == "skip" else text_input
        escrow_states[sender_id]["condition"] = condition
        await p2p_summary_send(message, sender_id)
        return

    if current_step == "pos_inr_q3":
        condition = "None" if text_input.lower() == "skip" else text_input
        escrow_states[sender_id]["condition"] = condition
        await pos_inr_summary_send(message, sender_id)
        return

    if current_step == "pos_crypto_q3":
        condition = "None" if text_input.lower() == "skip" else text_input
        escrow_states[sender_id]["condition"] = condition
        await pos_crypto_summary_send(message, sender_id)
        return

    if current_step == "p2p_amount":
        raw = text_input.replace("$", "").replace("₹", "").replace(",", "").strip()
        try:
            amount = float(raw)
            if amount <= 0: raise ValueError
        except ValueError:
            await message.answer('<tg-emoji emoji-id="5210952531676504517">❌</tg-emoji> Please enter a valid positive number!', parse_mode=ParseMode.HTML)
            return

        escrow_states[sender_id]["amount"] = amount
        escrow_states[sender_id]["step"] = "p2p_payment_method"
        text = "How are you paying?"
        buttons = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="INR", callback_data="pay_inr"),
                    InlineKeyboardButton(text="Crypto", callback_data="pay_crypto")
                ],
                [
                    InlineKeyboardButton(
                        text="Back",
                        icon_custom_emoji_id="5210952531676504517",
                        callback_data="back_to_role"
                    )
                ]
            ]
        )
        await message.answer(text, reply_markup=buttons, parse_mode=ParseMode.HTML)
        return

    if current_step == "p2p_inr_amount" or current_step == "p2p_crypto_amount":
        raw = text_input.replace("₹", "").replace("$", "").replace(",", "").strip()
        try:
            amount = float(raw)
            if amount <= 0: raise ValueError
        except ValueError:
            await message.answer('<tg-emoji emoji-id="5210952531676504517">❌</tg-emoji> Please enter a valid positive number!', parse_mode=ParseMode.HTML)
            return

        escrow_states[sender_id]["paying_amount"] = amount
        escrow_states[sender_id]["step"] = "p2p_condition"
        text = "Any conditions?"
        buttons = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Cancel",
                        icon_custom_emoji_id="5210952531676504517",
                        callback_data="p2p_cancel"
                    ),
                    InlineKeyboardButton(text="No Condition", callback_data="p2p_no_condition")
                ]
            ]
        )
        await message.answer(text, reply_markup=buttons, parse_mode=ParseMode.HTML)
        return

    if current_step == "pos_inr_q1" or current_step == "pos_crypto_q1":
        escrow_states[sender_id]["deal_info"] = text_input
        escrow_states[sender_id]["step"] = "pos_inr_q2" if current_step == "pos_inr_q1" else "pos_crypto_q2"
        curr_label = "INR (₹)" if current_step == "pos_inr_q1" else "Crypto ($)"
        text = f"<b>Question 2/3</b>\n\nHow much, in <b>{curr_label}</b>? Just the number."
        buttons = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Cancel",
                        icon_custom_emoji_id="5210952531676504517",
                        callback_data="pos_cancel"
                    )
                ]
            ]
        )
        await message.answer(text, reply_markup=buttons, parse_mode=ParseMode.HTML)
        return

    if current_step == "pos_inr_q2" or current_step == "pos_crypto_q2":
        raw = text_input.replace("₹", "").replace("$", "").replace(",", "").strip()
        try:
            amount = float(raw)
            if amount <= 0: raise ValueError
        except ValueError:
            await message.answer('<tg-emoji emoji-id="5210952531676504517">❌</tg-emoji> Please enter a valid positive number!', parse_mode=ParseMode.HTML)
            return

        escrow_states[sender_id]["pos_amount"] = amount
        escrow_states[sender_id]["step"] = "pos_inr_q3" if current_step == "pos_inr_q2" else "pos_crypto_q3"
        text = "<b>Question 3/3</b>\n\nAny conditions? Send them, or <code>skip</code>."
        buttons = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Cancel",
                        icon_custom_emoji_id="5210952531676504517",
                        callback_data="pos_cancel"
                    ),
                    InlineKeyboardButton(text="No Condition", callback_data="pos_no_condition")
                ]
            ]
        )
        await message.answer(text, reply_markup=buttons, parse_mode=ParseMode.HTML)
        return

    if current_step == "waiting_support_query":
        escrow_states[sender_id]["support_query"] = text_input
        escrow_states[sender_id]["step"] = "waiting_support_media"
        buttons = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Skip", callback_data="support_skip_media")]])
        await message.answer("Send a <b>screenshot, image or video</b> for this issue.", reply_markup=buttons, parse_mode=ParseMode.HTML)
        return

async def p2p_summary_send(message: Message, sender_id: int):
    data = escrow_states.get(sender_id, {})
    role = data.get("role")
    try:
        sender = await message.bot.get_chat(sender_id)
    except Exception:
        sender = None

    seller_name = f"@{sender.username}" if sender and sender.username else f"<code>{sender_id}</code>"
    other_party = "Not set"
    seller_display = seller_name if role == "Seller" else other_party
    buyer_display = other_party if role == "Seller" else seller_name

    pay_curr, pay_amt = data.get("paying_currency", "INR"), data.get("paying_amount", "")
    sell_curr, sell_amt = data.get("selling_currency", ""), data.get("amount", "")
    condition = data.get("condition", "None")

    summary_text = (
        f'<b>P2P <tg-emoji emoji-id="5357094458984769398">🔵</tg-emoji> {sell_curr} <tg-emoji emoji-id="5348567359764317130">↔️</tg-emoji> {pay_curr}</b>\n\n'
        f"<b>Seller:</b> {seller_display}\n"
        f"<b>Selling:</b> {sell_curr} ({sell_amt})\n\n"
        f"<b>Buyer:</b> {buyer_display}\n"
        f"<b>Paying:</b> {pay_curr} ({pay_amt})\n\n"
        f"<b>Condition:</b> {condition}"
    )
    buttons = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Submit",
                    icon_custom_emoji_id="5206607081334906820",
                    callback_data="deal_submit"
                ),
                InlineKeyboardButton(
                    text="Cancel",
                    icon_custom_emoji_id="5210952531676504517",
                    callback_data="deal_cancel"
                )
            ]
        ]
    )
    await message.answer(summary_text, reply_markup=buttons, parse_mode=ParseMode.HTML)

async def p2p_summary_edit(callback: CallbackQuery, sender_id: int):
    data = escrow_states.get(sender_id, {})
    role = data.get("role")
    try:
        sender = await callback.bot.get_chat(sender_id)
    except Exception:
        sender = None

    seller_name = f"@{sender.username}" if sender and sender.username else f"<code>{sender_id}</code>"
    other_party = "Not set"
    seller_display = seller_name if role == "Seller" else other_party
    buyer_display = other_party if role == "Seller" else seller_name

    pay_curr, pay_amt = data.get("paying_currency", "INR"), data.get("paying_amount", "")
    sell_curr, sell_amt = data.get("selling_currency", ""), data.get("amount", "")
    condition = data.get("condition", "None")

    summary_text = (
        f'<b>P2P <tg-emoji emoji-id="5357094458984769398">🔵</tg-emoji> {sell_curr} <tg-emoji emoji-id="5348567359764317130">↔️</tg-emoji> {pay_curr}</b>\n\n'
        f"<b>Seller:</b> {seller_display}\n"
        f"<b>Selling:</b> {sell_curr} ({sell_amt})\n\n"
        f"<b>Buyer:</b> {buyer_display}\n"
        f"<b>Paying:</b> {pay_curr} ({pay_amt})\n\n"
        f"<b>Condition:</b> {condition}"
    )
    buttons = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Submit",
                    icon_custom_emoji_id="5206607081334906820",
                    callback_data="deal_submit"
                ),
                InlineKeyboardButton(
                    text="Cancel",
                    icon_custom_emoji_id="5210952531676504517",
                    callback_data="deal_cancel"
                )
            ]
        ]
    )
    await callback.message.edit_text(summary_text, reply_markup=buttons, parse_mode=ParseMode.HTML)
    await callback.answer()

async def pos_inr_summary_send(message: Message, sender_id: int):
    data = escrow_states.get(sender_id, {})
    amount = data.get("pos_amount", 0)
    fee = max(amount * 0.02, 20)
    total = amount + fee
    usdt_rate = await get_usdt_inr_price()
    total_usdt = round(total / usdt_rate, 2)

    summary_text = (
        "<b>Type:</b> POS\n"
        f"<b>Deal info:</b> {data.get('deal_info', '.')}\n"
        f"<b>Amount:</b> ₹{amount:g} + ₹{fee:g} fee = ₹{total:g} (${total_usdt} USDT)\n"
        f"<b>Conditions:</b> {data.get('condition', 'None')}\n\nSubmit this?"
    )
    buttons = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Submit",
                    icon_custom_emoji_id="5206607081334906820",
                    callback_data="pos_submit"
                ),
                InlineKeyboardButton(
                    text="Cancel",
                    icon_custom_emoji_id="5210952531676504517",
                    callback_data="pos_cancel"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Back",
                    icon_custom_emoji_id="5210952531676504517",
                    callback_data="cat_pos"
                )
            ]
        ]
    )
    await message.answer(summary_text, reply_markup=buttons, parse_mode=ParseMode.HTML)

async def pos_inr_summary_edit(callback: CallbackQuery, sender_id: int):
    data = escrow_states.get(sender_id, {})
    amount = data.get("pos_amount", 0)
    fee = max(amount * 0.02, 20)
    total = amount + fee
    usdt_rate = await get_usdt_inr_price()
    total_usdt = round(total / usdt_rate, 2)

    summary_text = (
        "<b>Type:</b> POS\n"
        f"<b>Deal info:</b> {data.get('deal_info', '.')}\n"
        f"<b>Amount:</b> ₹{amount:g} + ₹{fee:g} fee = ₹{total:g} (${total_usdt} USDT)\n"
        f"<b>Conditions:</b> {data.get('condition', 'None')}\n\nSubmit this?"
    )
    buttons = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Submit",
                    icon_custom_emoji_id="5206607081334906820",
                    callback_data="pos_submit"
                ),
                InlineKeyboardButton(
                    text="Cancel",
                    icon_custom_emoji_id="5210952531676504517",
                    callback_data="pos_cancel"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Back",
                    icon_custom_emoji_id="5210952531676504517",
                    callback_data="cat_pos"
                )
            ]
        ]
    )
    await callback.message.edit_text(summary_text, reply_markup=buttons, parse_mode=ParseMode.HTML)
    await callback.answer()

async def pos_crypto_summary_send(message: Message, sender_id: int):
    data = escrow_states.get(sender_id, {})
    amount = data.get("pos_amount", 0)
    fee = max(amount * 0.02, 1)
    total = amount + fee

    summary_text = (
        "<b>Type:</b> POS\n"
        f"<b>Deal info:</b> {data.get('deal_info', '.')}\n"
        f"<b>Amount:</b> ${amount:g} + ${fee:g} fee = ${total:g}\n"
        f"<b>Conditions:</b> {data.get('condition', 'None')}\n\nSubmit this?"
    )
    buttons = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Submit",
                    icon_custom_emoji_id="5206607081334906820",
                    callback_data="pos_submit"
                ),
                InlineKeyboardButton(
                    text="Cancel",
                    icon_custom_emoji_id="5210952531676504517",
                    callback_data="pos_cancel"
                )
            ]
        ]
    )
    await message.answer(summary_text, reply_markup=buttons, parse_mode=ParseMode.HTML)

async def pos_crypto_summary_edit(callback: CallbackQuery, sender_id: int):
    data = escrow_states.get(sender_id, {})
    amount = data.get("pos_amount", 0)
    fee = max(amount * 0.02, 1)
    total = amount + fee

    summary_text = (
        "<b>Type:</b> POS\n"
        f"<b>Deal info:</b> {data.get('deal_info', '.')}\n"
        f"<b>Amount:</b> ${amount:g} + ${fee:g} fee = ${total:g}\n"
        f"<b>Conditions:</b> {data.get('condition', 'None')}\n\nSubmit this?"
    )
    buttons = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Submit",
                    icon_custom_emoji_id="5206607081334906820",
                    callback_data="pos_submit"
                ),
                InlineKeyboardButton(
                    text="Cancel",
                    icon_custom_emoji_id="5210952531676504517",
                    callback_data="pos_cancel"
                )
            ]
        ]
    )
    await callback.message.edit_text(summary_text, reply_markup=buttons, parse_mode=ParseMode.HTML)
    await callback.answer()

@router.callback_query(F.data == "pay_inr")
async def p2p_pay_inr(callback: CallbackQuery, state: FSMContext):
    sender_id = callback.from_user.id
    escrow_states.setdefault(sender_id, {})
    escrow_states[sender_id]["paying_currency"] = "INR"
    escrow_states[sender_id]["step"] = "p2p_inr_fund"

    text = "<b>Which INR funds are you paying with?</b>"
    buttons = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Safe Funds", callback_data="fund_safe"),
                InlineKeyboardButton(text="Rat Funds", callback_data="fund_rat")
            ],
            [
                InlineKeyboardButton(text="Gaming Funds", callback_data="fund_gaming"),
                InlineKeyboardButton(text="Mix Funds", callback_data="fund_mix")
            ],
            [
                InlineKeyboardButton(
                    text="Back",
                    icon_custom_emoji_id="5210952531676504517",
                    callback_data="back_to_payment"
                )
            ]
        ]
    )
    await callback.message.edit_text(text, reply_markup=buttons, parse_mode=ParseMode.HTML)
    await callback.answer()

@router.callback_query(F.data == "pay_crypto")
async def p2p_pay_crypto(callback: CallbackQuery, state: FSMContext):
    sender_id = callback.from_user.id
    escrow_states.setdefault(sender_id, {})
    escrow_states[sender_id]["step"] = "p2p_crypto_network"
    text = "<b>Select the crypto network you're paying with:</b>"
    buttons = crypto_buttons_paying("back_to_payment")
    await callback.message.edit_text(text, reply_markup=buttons, parse_mode=ParseMode.HTML)
    await callback.answer()

@router.callback_query(F.data == "back_to_payment")
async def back_to_payment(callback: CallbackQuery, state: FSMContext):
    sender_id = callback.from_user.id
    escrow_states.setdefault(sender_id, {})
    escrow_states[sender_id]["step"] = "p2p_payment_method"

    text = "<b>How are you paying?</b>"
    buttons = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="INR", callback_data="pay_inr"),
                InlineKeyboardButton(text="Crypto", callback_data="pay_crypto")
            ],
            [
                InlineKeyboardButton(
                    text="Back",
                    icon_custom_emoji_id="5210952531676504517",
                    callback_data="back_to_role"
                )
            ]
        ]
    )
    await callback.message.edit_text(text, reply_markup=buttons, parse_mode=ParseMode.HTML)
    await callback.answer()

@router.callback_query(F.data.startswith("fund_"))
async def fund_selection(callback: CallbackQuery, state: FSMContext):
    sender_id = callback.from_user.id
    fund_key = callback.data.replace("fund_", "")
    fund_name = INR_FUND_DISPLAY.get(fund_key, "Safe Funds")

    escrow_states.setdefault(sender_id, {})
    escrow_states[sender_id]["paying_currency"] = fund_name
    escrow_states[sender_id]["step"] = "p2p_inr_amount"

    text = f"<b>What amount of {fund_name} are you paying?</b>"
    buttons = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Back",
                    icon_custom_emoji_id="5210952531676504517",
                    callback_data="pay_inr"
                )
            ]
        ]
    )
    await callback.message.edit_text(text, reply_markup=buttons, parse_mode=ParseMode.HTML)
    await callback.answer()

@router.callback_query(F.data == "p2p_no_condition")
async def p2p_no_condition(callback: CallbackQuery, state: FSMContext):
    sender_id = callback.from_user.id
    escrow_states.setdefault(sender_id, {})
    escrow_states[sender_id]["condition"] = "None"
    await p2p_summary_edit(callback, sender_id)

@router.callback_query(F.data.in_({"p2p_cancel", "deal_cancel", "pos_cancel"}))
async def cancel_handler(callback: CallbackQuery, state: FSMContext):
    sender_id = callback.from_user.id
    escrow_states.pop(sender_id, None)
    await state.clear()
    await callback.message.edit_text('<tg-emoji emoji-id="5210952531676504517">❌</tg-emoji> <b>Cancelled.</b> /start to open a new one.', parse_mode=ParseMode.HTML)
    await callback.answer()

@router.callback_query(F.data == "deal_submit")
async def deal_submit(callback: CallbackQuery, state: FSMContext):
    sender_id = callback.from_user.id
    data = escrow_states.get(sender_id, {})
    await callback.message.edit_text('<tg-emoji emoji-id="5427181942934088912">💬</tg-emoji> <b>Please wait while we connect you with the best available escrower!</b>\n\n<b>Expected time: ~10 minutes</b>', parse_mode=ParseMode.HTML)
    await callback.answer()

    user = callback.from_user
    first_name = user.first_name or "User"
    deal_claims[sender_id] = {"status": "pending", "approved_by": None, "approved_username": None}

    mm_text = (
        '<tg-emoji emoji-id="5395695537687123235">🚨</tg-emoji> <b>New Deal Request!</b>\n'
        f"From User: <a href='tg://user?id={sender_id}'>{first_name}</a>\n"
        "Category: P2P\n"
        f"Selling: {data.get('amount')} {data.get('selling_currency')}\n"
        f"Paying: {data.get('paying_amount')} {data.get('paying_currency')}\n"
        f"Conditions: {data.get('condition', 'None')}"
    )
    mm_buttons = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Approve",
                    icon_custom_emoji_id="5206607081334906820",
                    callback_data=f"mm_app_{sender_id}"
                ),
                InlineKeyboardButton(
                    text="Reject",
                    icon_custom_emoji_id="5210952531676504517",
                    callback_data=f"mm_rej_{sender_id}"
                )
            ]
        ]
    )

    for mm_id in MIDDLEMEN_IDS:
        try:
            await bot.send_message(mm_id, mm_text, reply_markup=mm_buttons, parse_mode=ParseMode.HTML)
        except Exception as e:
            print(f"Error notifying middleman {mm_id}: {e}")

@router.callback_query(F.data == "pos_no_condition")
async def pos_no_condition(callback: CallbackQuery, state: FSMContext):
    sender_id = callback.from_user.id
    escrow_states.setdefault(sender_id, {})
    escrow_states[sender_id]["condition"] = "None"
    if escrow_states[sender_id].get("currency_type") == "INR":
        await pos_inr_summary_edit(callback, sender_id)
    else:
        await pos_crypto_summary_edit(callback, sender_id)

@router.callback_query(F.data == "pos_submit")
async def pos_submit(callback: CallbackQuery, state: FSMContext):
    sender_id = callback.from_user.id
    data = escrow_states.get(sender_id, {})
    deal_id = uuid.uuid4().hex[:10]
    deal_claims[deal_id] = {"status": "pending", "approved_by": None, "approved_username": None}
    data["deal_id"] = deal_id
    escrow_states[sender_id] = data

    await callback.message.edit_text('<tg-emoji emoji-id="5427181942934088912">💬</tg-emoji> <b>Please wait while we connect you with the best available escrower!</b>\n\n<b>Expected time: ~10 minutes</b>', parse_mode=ParseMode.HTML)
    await callback.answer()

    user = callback.from_user
    first_name = user.first_name or "User"
    mm_text = (
        '<tg-emoji emoji-id="5395695537687123235">🚨</tg-emoji> <b>New Deal Request!</b>\n'
        f"From User: <a href='tg://user?id={sender_id}'>{first_name}</a>\n"
        "Category: POS\n"
        f"Deal Info: {data.get('deal_info', '.')}\n"
        f"Amount: {data.get('pos_amount')} {data.get('currency_type')}\n"
        f"Conditions: {data.get('condition', 'None')}"
    )
    mm_buttons = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Approve",
                    icon_custom_emoji_id="5206607081334906820",
                    callback_data=f"mm_app_{sender_id}_{deal_id}"
                ),
                InlineKeyboardButton(
                    text="Reject",
                    icon_custom_emoji_id="5210952531676504517",
                    callback_data=f"mm_rej_{sender_id}_{deal_id}"
                )
            ]
        ]
    )

    for mm_id in MIDDLEMEN_IDS:
        try:
            await bot.send_message(mm_id, mm_text, reply_markup=mm_buttons, parse_mode=ParseMode.HTML)
        except Exception as e:
            print(f"Error notifying middleman {mm_id}: {e}")

@router.callback_query(F.data == "support_skip_media")
async def support_skip_media(callback: CallbackQuery, state: FSMContext):
    sender_id = callback.from_user.id
    query_text = escrow_states.get(sender_id, {}).get("support_query", "No text query")

    admin_msg = f'<tg-emoji emoji-id="5253742260054409879">✉️</tg-emoji> <b>New Support Ticket! (Skipped Media)</b>\nFrom: <code>{sender_id}</code>\nIssue: {query_text}'
    admin_buttons = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Reply",
                    icon_custom_emoji_id="5395444784611480792",
                    callback_data=f"sup_reply_{sender_id}"
                )
            ]
        ]
    )
    try:
        await bot.send_message(SUPPORT_ADMIN_ID, admin_msg, reply_markup=admin_buttons, parse_mode=ParseMode.HTML)
    except Exception as e:
        print(f"Error sending support admin: {e}")

    await callback.message.edit_text('<tg-emoji emoji-id="5206607081334906820">✔️</tg-emoji> <b>Sent to support.</b>\n\nYou will get a reply here.', parse_mode=ParseMode.HTML)
    await callback.answer()
    escrow_states.pop(sender_id, None)
    await state.clear()

@router.callback_query(F.data.startswith("sup_reply_"))
async def support_reply_click(callback: CallbackQuery, state: FSMContext):
    target_user = int(callback.data.split("_")[2])
    admin_id = callback.from_user.id
    text = f'<tg-emoji emoji-id="5395444784611480792">✏️</tg-emoji> <b>Send your reply for user</b> <code>{target_user}</code>.\n\nIt will be delivered directly to them.'
    await callback.message.answer(text, parse_mode=ParseMode.HTML)
    await callback.answer()
    admin_states[admin_id] = {"step": "waiting_support_reply", "target_user": target_user}

@router.callback_query(F.data.startswith("mm_app_"))
async def mm_approve(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    target_user_id = int(parts[2])
    deal_id = parts[3] if len(parts) > 3 else None
    admin_id = callback.from_user.id

    deal = deal_claims.get(deal_id) if deal_id else deal_claims.get(target_user_id)
    if not deal or deal["status"] != "pending":
        await callback.answer('<tg-emoji emoji-id="5210952531676504517">❌</tg-emoji> This deal has already been claimed.', show_alert=True)
        return

    deal["status"] = "claimed"
    deal["approved_by"] = admin_id
    admin_username = callback.from_user.username
    deal["approved_username"] = f"@{admin_username}" if admin_username else callback.from_user.full_name

    await callback.message.edit_text(f'<tg-emoji emoji-id="5206607081334906820">✔️</tg-emoji> <b>Deal approved!</b>\n\n<b>Middleman:</b> {deal["approved_username"]}\n\nPlease send the Escrow Group Link in chat now:', parse_mode=ParseMode.HTML)
    await callback.answer()
    admin_states[admin_id] = {"step": "waiting_group_link", "target_user": target_user_id, "deal_id": deal_id}

@router.callback_query(F.data.startswith("mm_rej_"))
async def mm_reject(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text('<tg-emoji emoji-id="5210952531676504517">❌</tg-emoji> <b>Deal rejected.</b>', parse_mode=ParseMode.HTML)
    await callback.answer()

@router.callback_query(F.data == "menu_tos")
async def show_tos(callback: CallbackQuery, state: FSMContext):
    tos_text = (
        "<b>Affux Escrow — TOS</b>\n\n"
        "Please read before using <a href='https://t.me/Middlemaven'>AFFUX Escrow</a>.\n\n"
        "1. Neutral third-party service for P2P and legitimate deals.\n"
        "2. Escrow fee is non-refundable once service starts.\n"
        "3. Verify all transaction details before proceeding."
    )
    buttons = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Back",
                    icon_custom_emoji_id="5210952531676504517",
                    callback_data="back_to_start"
                )
            ]
        ]
    )
    await callback.message.edit_text(tos_text, reply_markup=buttons, parse_mode=ParseMode.HTML, link_preview_options={"is_disabled": True})
    await callback.answer()

@router.callback_query(F.data == "menu_support")
async def show_support(callback: CallbackQuery, state: FSMContext):
    support_text = '<tg-emoji emoji-id="5443038326535759644">💬</tg-emoji> <b>Support</b>\n\nWhat is this about?'
    buttons = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Deals", callback_data="support_deals"),
                InlineKeyboardButton(text="Others", callback_data="support_others")
            ],
            [
                InlineKeyboardButton(
                    text="Back",
                    icon_custom_emoji_id="5210952531676504517",
                    callback_data="back_to_start"
                )
            ]
        ]
    )
    await callback.message.edit_text(support_text, reply_markup=buttons, parse_mode=ParseMode.HTML)
    await callback.answer()

@router.callback_query(F.data == "support_deals")
async def support_deals(callback: CallbackQuery, state: FSMContext):
    text = '<tg-emoji emoji-id="5210952531676504517">❌</tg-emoji> <b>You have no completed deals.</b>'
    buttons = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Back",
                    icon_custom_emoji_id="5210952531676504517",
                    callback_data="menu_support"
                )
            ]
        ]
    )
    await callback.message.edit_text(text, reply_markup=buttons, parse_mode=ParseMode.HTML)
    await callback.answer()

@router.callback_query(F.data == "support_others")
async def support_others(callback: CallbackQuery, state: FSMContext):
    sender_id = callback.from_user.id
    escrow_states[sender_id] = {"step": "waiting_support_query"}
    text = '<tg-emoji emoji-id="5443038326535759644">💬</tg-emoji> <b>Support</b>\n\nWhat is the issue? Send it in one message.'
    buttons = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Back",
                    icon_custom_emoji_id="5210952531676504517",
                    callback_data="menu_support"
                )
            ]
        ]
    )
    await callback.message.edit_text(text, reply_markup=buttons, parse_mode=ParseMode.HTML)
    await callback.answer()

async def main():
    print("BOT STARTING...")
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped by user.")
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")