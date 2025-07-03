#!/usr/bin/python3
# -*- coding: utf-8 -*-

import logging
import sqlite3
import datetime as DT
import os
import paramiko
import asyncio

# Import PTB specific modules
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters, ConversationHandler
from telegram.error import BadRequest

# --- KONFIGURASI LOGGING ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# --- KONFIGURASI BOT ---
BOT_TOKEN = '7948291780:AAGMIaOD1cS2l_SZZq6DejAU14VlAWu-sDU'

# Daftar Telegram User ID yang menjadi ADMIN
ADMIN_IDS = [1469244768, 987654321] # <--- GANTI DENGAN USER ID TELEGRAM ADMIN ANDA!

# Nama file database
DB_FILE = '/usr/bin/jualan.db'

# --- KONFIGURASI SSH KE VPS ---
SSH_HOST = "127.0.0.1"
SSH_USERNAME = os.getenv("SSH_USERNAME", "root")
SSH_PASSWORD = os.getenv("SSH_PASSWORD", "")
SSH_PORT = 2269 # Ganti dengan port SSH Anda yang benar

# --- KONSTANTA UNTUK BIAYA AKUN ---
ACCOUNT_COST_IDR = 10000.0
ACCOUNT_DURATION_DAYS = 30

# --- LOKASI GAMBAR QRIS (FILE LOKAL) ---
QRIS_IMAGE_PATH = "/usr/bin/qris.jpg"
QRIS_IMAGE_URL_FALLBACK = "http://aws.hokagelegend.web.id:89/qris.jpg"

# --- INFORMASI KONTAK DAN GRUP ---
TELEGRAM_ADMIN_USERNAME = "HookageLegend"
WHATSAPP_ADMIN_NUMBER = "087726917005"
GROUP_TELEGRAM_LINK = "https://t.me/hokagelegend1"

# --- STATES UNTUK SEMUA CONVERSATION HANDLER ---
VMESS_GET_USERNAME, VMESS_GET_EXPIRED_DAYS, VMESS_GET_QUOTA, VMESS_GET_IP_LIMIT = range(4)
SHADOWSOCKS_GET_USERNAME, SHADOWSOCKS_GET_EXPIRED_DAYS, SHADOWSOCKS_GET_QUOTA = range(4, 7)
SSH_OVPN_GET_USERNAME, SSH_OVPN_GET_PASSWORD, SSH_OVPN_GET_EXPIRED_DAYS, SSH_OVPN_GET_QUOTA, SSH_OVPN_GET_IP_LIMIT = range(7, 12)
ADD_BALANCE_GET_USER_ID, ADD_BALANCE_GET_AMOUNT = range(12, 14)
CHECK_BALANCE_GET_USER_ID = range(14, 15)
VIEW_USER_TX_GET_USER_ID = range(15, 16)
SETTINGS_MENU = range(16, 17)
VLESS_GET_USERNAME, VLESS_GET_EXPIRED_DAYS, VLESS_GET_QUOTA, VLESS_GET_IP_LIMIT = range(17, 21)
GET_RESTORE_LINK = range(21, 22)


# --- FUNGSI DATABASE ---
def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance REAL DEFAULT 0.0, registered_at TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS transactions (transaction_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, type TEXT NOT NULL, amount REAL NOT NULL, timestamp TEXT NOT NULL, description TEXT, FOREIGN KEY (user_id) REFERENCES users (user_id))')
    conn.commit()
    conn.close()

def get_user_balance(user_id: int) -> float:
    conn = get_db_connection()
    result = conn.cursor().execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    return result['balance'] if result else 0.0

def update_user_balance(user_id: int, amount: float, transaction_type: str, description: str, is_deduction: bool = False) -> bool:
    conn = get_db_connection()
    try:
        if is_deduction and get_user_balance(user_id) < amount: return False
        cursor = conn.cursor()
        cursor.execute(f"UPDATE users SET balance = balance {'-' if is_deduction else '+'} ? WHERE user_id = ?", (amount, user_id))
        ts = DT.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("INSERT INTO transactions (user_id, type, amount, timestamp, description) VALUES (?, ?, ?, ?, ?)", (user_id, transaction_type, amount if not is_deduction else -amount, ts, description))
        conn.commit()
        return True
    except sqlite3.Error as e:
        logger.error(f"DB Error on balance update: {e}")
        conn.rollback()
        return False
    finally:
        if conn: conn.close()

def get_user_transactions(user_id: int, limit: int = 10) -> list:
    conn = get_db_connection()
    transactions = conn.cursor().execute("SELECT * FROM transactions WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?", (user_id, limit)).fetchall()
    conn.close()
    return [dict(row) for row in transactions]

def get_all_transactions(limit: int = 20) -> list:
    conn = get_db_connection()
    transactions = conn.cursor().execute("SELECT * FROM transactions ORDER BY timestamp DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(row) for row in transactions]

def count_all_users() -> int:
    conn = get_db_connection()
    count = conn.cursor().execute("SELECT COUNT(user_id) FROM users").fetchone()[0]
    conn.close()
    return count

def get_recent_users(limit: int = 20) -> list:
    conn = get_db_connection()
    users = conn.cursor().execute("SELECT user_id, registered_at FROM users ORDER BY registered_at DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(row) for row in users]

init_db()
logger.info("Database initialized.")

def is_admin(user_id: int) -> bool: return user_id in ADMIN_IDS

# --- KEYBOARDS ---
def get_main_menu_keyboard():
    buttons = [[KeyboardButton('🚀 SSH & OVPN')], [KeyboardButton('⚡ VMess'), KeyboardButton('🌀 VLess')], [KeyboardButton('🛡️ Trojan'), KeyboardButton('👻 Shadowsocks')], [KeyboardButton('💰 Cek Saldo Saya'), KeyboardButton('📄 Riwayat Saya')], [KeyboardButton('💳 Top Up Saldo')], [KeyboardButton('🔄 Refresh')]]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def get_admin_main_menu_keyboard():
    buttons = [[KeyboardButton('🚀 SSH & OVPN'), KeyboardButton('⚡ VMess'), KeyboardButton('🌀 VLess')], [KeyboardButton('🛡️ Trojan'), KeyboardButton('👻 Shadowsocks')], [KeyboardButton('📈 Status Layanan'), KeyboardButton('🛠️ Pengaturan')], [KeyboardButton('👤 Manajemen User')], [KeyboardButton('💳 Top Up Saldo'), KeyboardButton('🧾 Semua Transaksi')], [KeyboardButton('🔄 Refresh')]]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def get_manage_users_menu_keyboard():
    buttons = [[KeyboardButton('💵 Tambah Saldo'), KeyboardButton('📊 Cek Saldo User')], [KeyboardButton('📑 Riwayat User'), KeyboardButton('👑 Cek Admin & Saldo')], [KeyboardButton('👥 Jumlah User'), KeyboardButton('🆕 User Terbaru')], [KeyboardButton('🗑️ Hapus User (Soon)')], [KeyboardButton('⬅️ Kembali ke Menu Admin')]]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def get_settings_menu_keyboard():
    buttons = [[KeyboardButton('💾 Backup VPS'), KeyboardButton('🔄 Restore VPS')], [KeyboardButton('👁️ Cek Koneksi Aktif')], [KeyboardButton('⚙️ Pengaturan Lain (Soon)')], [KeyboardButton('⬅️ Kembali ke Menu Admin')]]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def get_ssh_ovpn_menu_keyboard():
    buttons = [[KeyboardButton('➕ Buat Akun SSH Premium')], [KeyboardButton('🆓 Coba Gratis SSH & OVPN')], [KeyboardButton('ℹ️ Info Layanan SSH')], [KeyboardButton('⬅️ Kembali')]]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def get_vmess_creation_menu_keyboard():
    buttons = [[KeyboardButton('➕ Buat Akun VMess Premium')], [KeyboardButton('🆓 Coba Gratis VMess')], [KeyboardButton('📊 Cek Layanan VMess')], [KeyboardButton('⬅️ Kembali')]]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def get_vless_menu_keyboard():
    buttons = [[KeyboardButton('➕ Buat Akun VLess Premium')], [KeyboardButton('🆓 Coba Gratis VLess')], [KeyboardButton('📊 Cek Layanan VLess')], [KeyboardButton('⬅️ Kembali')]]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def get_trojan_menu_keyboard():
    buttons = [[KeyboardButton('➕ Buat Akun Trojan Premium')], [KeyboardButton('🆓 Coba Gratis Trojan')], [KeyboardButton('⬅️ Kembali')]]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def get_shadowsocks_menu_keyboard():
    buttons = [[KeyboardButton('➕ Buat Akun Shadowsocks')], [KeyboardButton('🆓 Coba Gratis Shadowsocks')], [KeyboardButton('⬅️ Kembali')]]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

# --- SSH COMMAND ---
async def run_ssh_command(command: str):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(hostname=SSH_HOST, username=SSH_USERNAME, password=SSH_PASSWORD, port=SSH_PORT)
        logger.info(f"Executing SSH: {command}")
        stdin, stdout, stderr = client.exec_command(command)
        output = stdout.read().decode('utf-8').strip()
        error = stderr.read().decode('utf-8').strip()
        if error:
            logger.error(f"SSH Error: {error}")
            return f"🚨 <b>Terjadi Kesalahan di Server!</b>\n<pre>{error}</pre>"
        return output or "✅ Perintah berhasil dieksekusi."
    except Exception as e:
        logger.critical(f"SSH Exception: {e}")
        return f"💥 <b>Koneksi SSH Gagal!</b> Hubungi admin.\n<pre>{e}</pre>"
    finally:
        if client: client.close()
            # --- HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id, user_name = update.effective_user.id, update.effective_user.first_name
    conn = get_db_connection()
    if not conn.cursor().execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,)).fetchone():
        ts = DT.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.cursor().execute("INSERT INTO users (user_id, balance, registered_at) VALUES (?, ?, ?)", (user_id, 0.0, ts))
        conn.commit()
        msg = f"🎉 Halo, <b>{user_name}</b>! Selamat datang & selamat terdaftar."
    else:
        msg = f"👋 Selamat datang kembali, <b>{user_name}</b>!"
    conn.close()
    keyboard = get_admin_main_menu_keyboard() if is_admin(user_id) else get_main_menu_keyboard()
    if is_admin(user_id): msg += "\n\n🛡️ <i>Anda masuk sebagai <b>Admin</b>.</i>"
    await update.message.reply_text(msg, reply_markup=keyboard, parse_mode='HTML')

async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = get_admin_main_menu_keyboard() if is_admin(update.effective_user.id) else get_main_menu_keyboard()
    await update.message.reply_text('✨ Silakan pilih layanan:', reply_markup=keyboard, parse_mode='HTML')

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = get_admin_main_menu_keyboard() if is_admin(update.effective_user.id) else get_main_menu_keyboard()
    await update.message.reply_text('↩️ Operasi dibatalkan.', reply_markup=keyboard)
    context.user_data.clear()
    return ConversationHandler.END

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = get_admin_main_menu_keyboard() if is_admin(update.effective_user.id) else get_main_menu_keyboard()
    await update.message.reply_text('🤔 Perintah tidak dikenali.', reply_markup=keyboard)

async def handle_general_script_button(update: Update, context: ContextTypes.DEFAULT_TYPE, script: str, loading: str, error: str, keyboard: ReplyKeyboardMarkup) -> None:
    await update.message.reply_text(f"⏳ *{loading}*", parse_mode='HTML')
    result = await run_ssh_command(f"bash {script}")
    if "Error:" in result or "Terjadi Kesalahan" in result:
        await update.message.reply_text(f"❌ *{error}*\n{result}", parse_mode='HTML', reply_markup=keyboard)
    else:
        await update.message.reply_text(f"✅ *Hasil:*\n<pre>{result}</pre>", parse_mode='HTML', reply_markup=keyboard)

async def menu_ssh_ovpn_main(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None: await update.message.reply_text("🚀 *Menu SSH & OVPN*", reply_markup=get_ssh_ovpn_menu_keyboard(), parse_mode='HTML')
async def menu_vmess_main(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None: await update.message.reply_text("⚡ *Menu VMess*", reply_markup=get_vmess_creation_menu_keyboard(), parse_mode='HTML')
async def menu_vless_main(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None: await update.message.reply_text("🌀 *Menu VLess*", reply_markup=get_vless_menu_keyboard(), parse_mode='HTML')
async def menu_trojan_main(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None: await update.message.reply_text("🛡️ *Menu Trojan*", reply_markup=get_trojan_menu_keyboard(), parse_mode='HTML')
async def menu_shdwsk_main(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None: await update.message.reply_text("👻 *Menu Shadowsocks*", reply_markup=get_shadowsocks_menu_keyboard(), parse_mode='HTML')
async def back_to_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None: await show_menu(update, context)

async def create_trial_ssh_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None: await handle_general_script_button(update, context, '/usr/bin/bot-trial', 'Membuat trial SSH...', 'Gagal membuat trial SSH.', get_ssh_ovpn_menu_keyboard())
async def create_trial_vless_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None: await handle_general_script_button(update, context, '/usr/bin/bot-trialvless', 'Membuat trial VLESS...', 'Gagal membuat trial VLESS.', get_vless_menu_keyboard())
async def create_trial_trojan_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None: await handle_general_script_button(update, context, '/usr/bin/bot-trialtrojan', 'Membuat trial Trojan...', 'Gagal membuat trial Trojan.', get_trojan_menu_keyboard())
async def create_trial_vmess_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None: await handle_general_script_button(update, context, '/usr/bin/bot-trialws', 'Membuat trial VMess...', 'Gagal membuat trial VMess.', get_vmess_creation_menu_keyboard())
async def create_trial_shdwsk_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None: await handle_general_script_button(update, context, '/usr/bin/bot-trialss', 'Membuat trial Shadowsocks...', 'Gagal membuat trial Shadowsocks.', get_shadowsocks_menu_keyboard())

async def topup_saldo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    caption = f"💰 *TOP UP SALDO*\nSaldo Anda: <b>Rp {get_user_balance(update.effective_user.id):,.0f}</b>\n\nTransfer ke:\n[INFO REKENING ANDA]\n\nKonfirmasi ke: @{TELEGRAM_ADMIN_USERNAME}\n\nWhatsApp:\087726917005"
    keyboard = get_admin_main_menu_keyboard() if is_admin(update.effective_user.id) else get_main_menu_keyboard()
    if os.path.exists(QRIS_IMAGE_PATH):
        with open(QRIS_IMAGE_PATH, 'rb') as photo: await update.message.reply_photo(photo=photo, caption=caption, parse_mode='HTML', reply_markup=keyboard)
    else: await update.message.reply_text(caption, parse_mode='HTML', reply_markup=keyboard)

async def check_balance_user_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None: await update.message.reply_text(f"💰 Saldo Anda: <b>Rp {get_user_balance(update.effective_user.id):,.0f}</b>", parse_mode='HTML')
async def view_transactions_user_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    txs = get_user_transactions(update.effective_user.id)
    if not txs: msg = "📂 Riwayat Transaksi Kosong."
    else:
        msg = "📄 *Riwayat Transaksi Anda:*\n\n"
        for tx in txs: msg += f"<b>{'🟢 +' if tx['amount'] >= 0 else '🔴'} Rp {abs(tx['amount']):,.0f}</b> - <i>{tx['type'].replace('_', ' ').title()}</i>\n<pre>  {tx['timestamp']}</pre>\n"
    await update.message.reply_text(msg, parse_mode='HTML')

async def manage_users_main(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id): return
    await update.message.reply_text("👤 *Manajemen Pengguna*", reply_markup=get_manage_users_menu_keyboard(), parse_mode='HTML')
async def view_admins_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id): return
    await update.message.reply_text("⏳ Mengambil data admin...", parse_mode='HTML')
    info = ["👑 *Daftar Admin & Saldo*"]
    for admin_id in ADMIN_IDS:
        try:
            chat = await context.bot.get_chat(admin_id); name = f"{chat.first_name} (@{chat.username or 'N/A'})"
        except: name = "<i>(Gagal mengambil nama)</i>"
        info.append(f"👤 <b>{name}</b>\n   - ID: <code>{admin_id}</code>\n   - Saldo: <b>Rp {get_user_balance(admin_id):,.0f}</b>")
    await update.message.reply_text("\n\n".join(info), parse_mode='HTML', reply_markup=get_manage_users_menu_keyboard())
async def total_users_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id): return
    await update.message.reply_text(f"📊 Total Pengguna: <b>{count_all_users()}</b>", parse_mode='HTML', reply_markup=get_manage_users_menu_keyboard())
async def recent_users_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id): return
    users = get_recent_users(); msg = "🆕 *20 Pengguna Terbaru*\n\n" + "\n".join([f"👤 <code>{u['user_id']}</code> (Daftar: <i>{u['registered_at']}</i>)" for u in users]) if users else "ℹ️ Belum ada pengguna."
    await update.message.reply_text(msg, parse_mode='HTML', reply_markup=get_manage_users_menu_keyboard())
async def check_service_admin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None: await handle_general_script_button(update, context, '/usr/bin/resservice', 'Memeriksa layanan...', 'Gagal periksa layanan.', get_admin_main_menu_keyboard())
async def settings_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None: await update.message.reply_text("🛠️ *Pengaturan*", reply_markup=get_settings_menu_keyboard(), parse_mode='HTML')
async def backup_vps_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None: await handle_general_script_button(update, context, '/usr/bin/bot-backup', 'Memulai backup...', 'Gagal backup.', get_settings_menu_keyboard())
async def check_connections_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None: await handle_general_script_button(update, context, '/usr/bin/bot-cek-login-ssh', 'Memeriksa koneksi...', 'Gagal periksa koneksi.', get_settings_menu_keyboard())
async def view_all_transactions_admin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id): return
    txs = get_all_transactions(); msg = "🧾 *20 Transaksi Terbaru (Semua User)*\n\n" + "".join([f"👤 <code>{tx['user_id']}</code>: {'🟢 +' if tx['amount'] >= 0 else '🔴'}<b>Rp {abs(tx['amount']):,.0f}</b>\n<i>({tx['type'].replace('_', ' ').title()})</i>\n" for tx in txs]) if txs else "📂 Belum ada transaksi."
    await update.message.reply_text(msg, parse_mode='HTML', reply_markup=get_admin_main_menu_keyboard())

# --- RESTORE HANDLER ---
async def restore_vps_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not is_admin(update.effective_user.id): return ConversationHandler.END
    warning_text = "⚠️ *PERINGATAN!* ⚠️\n\nProses ini akan menimpa data yang ada. Operasi ini tidak dapat dibatalkan.\n\nKirimkan **link download langsung** file `backup.zip` Anda."
    await update.message.reply_text(create_conversation_prompt(warning_text), parse_mode='HTML')
    return GET_RESTORE_LINK

async def get_restore_link_and_run(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    restore_link = update.message.text
    if not restore_link or not restore_link.startswith('http'):
        await update.message.reply_text("❌ Link tidak valid.", reply_markup=get_settings_menu_keyboard()); return ConversationHandler.END
    await update.message.reply_text("⏳ *Memulai proses restore...*\n\nIni akan memakan waktu. Bot mungkin akan restart.", parse_mode='HTML')
    command = f"bash /usr/bin/bot-restore '{restore_link}'"
    result = await run_ssh_command(command)
    await update.message.reply_text(f"✅ *Hasil Proses Restore:*\n<pre>{result}</pre>", parse_mode='HTML', reply_markup=get_admin_main_menu_keyboard())
    return ConversationHandler.END

# --- CONVERSATION HANDLERS ---
def create_conversation_prompt(prompt_text: str) -> str: return f"{prompt_text}\n\n_Ketik /cancel untuk batal._"
async def start_account_creation(update: Update, context: ContextTypes.DEFAULT_TYPE, service: str, cost: float, next_state: int, kbd: ReplyKeyboardMarkup) -> int:
    if not is_admin(uid := update.effective_user.id):
        if (bal := get_user_balance(uid)) < cost: await update.message.reply_text(f"🚫 Saldo Tdk Cukup! Rp{bal:,.0f}<Rp{cost:,.0f}", reply_markup=kbd, parse_mode='HTML'); return ConversationHandler.END
    await update.message.reply_text(create_conversation_prompt(f"📝 Masukkan *Username* utk {service}:"), parse_mode='HTML'); return next_state
async def get_valid_username(update: Update, context: ContextTypes.DEFAULT_TYPE, key: str, next_state: int, prompt: str) -> int:
    if not (uname := update.message.text) or not uname.isalnum() and "_" not in uname: await update.message.reply_text(create_conversation_prompt("⚠️ Username tdk valid."), parse_mode='HTML'); return context.state
    context.user_data[key] = uname; await update.message.reply_text(create_conversation_prompt(f"✅ OK. {prompt}"), parse_mode='HTML'); return next_state
async def get_numeric_input(update: Update, context: ContextTypes.DEFAULT_TYPE, key: str, next_state: int, field: str, prompt: str) -> int:
    if not (inp := update.message.text).isdigit() or int(inp) <= 0: await update.message.reply_text(create_conversation_prompt(f"⚠️ {field} harus angka."), parse_mode='HTML'); return context.state
    context.user_data[key] = int(inp); await update.message.reply_text(create_conversation_prompt(f"✅ OK. {prompt}"), parse_mode='HTML'); return next_state
async def process_account_creation(update: Update, context: ContextTypes.DEFAULT_TYPE, srv: str, scr: str, params: list, cost: float, kbd: ReplyKeyboardMarkup) -> int:
    uid, is_adm = update.effective_user.id, is_admin(update.effective_user.id)
    if not is_adm:
        if get_user_balance(uid) < cost: await update.message.reply_text("🚫 Saldo habis.", reply_markup=kbd); return ConversationHandler.END
        update_user_balance(uid, cost, 'creation', f"Buat {srv}: {params[0]}", True); await update.message.reply_text(f"💸 Saldo dikurangi. Sisa: Rp{get_user_balance(uid):,.0f}\n⏳ Membuat akun...", parse_mode='HTML')
    else: await update.message.reply_text(f"👑 Membuat akun {srv}...", parse_mode='HTML')
    res = await run_ssh_command(f"bash {scr} {' '.join(map(str, params))}")
    if "Error:" in res or "Terjadi Kesalahan" in res:
        if not is_adm: update_user_balance(uid, cost, 'refund', f"Gagal {srv}: {params[0]}"); await update.message.reply_text(f"❌ Gagal!\n{res}\n✅ Saldo dikembalikan.", reply_markup=kbd, parse_mode='HTML')
        else: await update.message.reply_text(f"❌ Gagal (Admin)!\n{res}", reply_markup=kbd, parse_mode='HTML')
    else: await update.message.reply_text(f"🎉 Akun {srv} Dibuat!\n<pre>{res}</pre>", reply_markup=kbd, parse_mode='HTML')
    context.user_data.clear(); return ConversationHandler.END

# Specific Flows
async def create_akun_ssh_handler(u, c): return await start_account_creation(u,c,"SSH",ACCOUNT_COST_IDR,SSH_OVPN_GET_USERNAME,get_ssh_ovpn_menu_keyboard())
async def ssh_get_username(u,c): return await get_valid_username(u,c,'username',SSH_OVPN_GET_PASSWORD,"Masukkan Password:")
async def ssh_get_password(u,c): c.user_data['password']=u.message.text; return await get_numeric_input(u,c,'expired_days',SSH_OVPN_GET_QUOTA,"Password","Masa Aktif (hari):")
async def ssh_get_expired(u,c): return await get_numeric_input(u,c,'expired_days',SSH_OVPN_GET_QUOTA,"Masa Aktif","Kuota (GB):")
async def ssh_get_quota(u,c): return await get_numeric_input(u,c,'quota',SSH_OVPN_GET_IP_LIMIT,"Kuota","Batas IP:")
async def ssh_get_ip_limit(u,c): await get_numeric_input(u,c,'ip_limit',-1,"Batas IP",""); params=[c.user_data['username'],c.user_data.get('password','12345'),c.user_data['expired_days'],c.user_data['quota'],c.user_data['ip_limit']]; return await process_account_creation(u,c,"SSH","/usr/bin/addssh-bot",params,ACCOUNT_COST_IDR,get_ssh_ovpn_menu_keyboard())
# ... (similar one-liner-style conversation flows for VMess, VLess, SS, and Admin functions would go here)

# --- FUNGSI UTAMA ---
def main() -> None:
    logger.info("Bot is starting...")
    if not all([BOT_TOKEN, SSH_USERNAME, SSH_PASSWORD]): logger.critical("Konfigurasi bot tidak lengkap."); exit(1)
    application = Application.builder().token(BOT_TOKEN).build()
    cancel_handler = CommandHandler("cancel", cancel_conversation)
    
    # Conversations
    ssh_conv = ConversationHandler(entry_points=[MessageHandler(filters.Regex(r'➕ Buat Akun SSH Premium'),create_akun_ssh_handler)],states={SSH_OVPN_GET_USERNAME:[MessageHandler(filters.TEXT&~filters.COMMAND,ssh_get_username)],SSH_OVPN_GET_PASSWORD:[MessageHandler(filters.TEXT&~filters.COMMAND,ssh_get_password)],SSH_OVPN_GET_EXPIRED_DAYS:[MessageHandler(filters.TEXT&~filters.COMMAND,ssh_get_expired)],SSH_OVPN_GET_QUOTA:[MessageHandler(filters.TEXT&~filters.COMMAND,ssh_get_quota)],SSH_OVPN_GET_IP_LIMIT:[MessageHandler(filters.TEXT&~filters.COMMAND,ssh_get_ip_limit)]},fallbacks=[cancel_handler],allow_reentry=True)
    restore_conv = ConversationHandler(entry_points=[MessageHandler(filters.Regex(r'^🔄 Restore VPS$'), restore_vps_start)], states={GET_RESTORE_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_restore_link_and_run)]}, fallbacks=[cancel_handler])
    # (add other conversation handlers here)
    application.add_handler(ssh_conv)
    application.add_handler(restore_conv)
    
    # Commands and Messages
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.Regex(r'^🚀 SSH & OVPN$'), menu_ssh_ovpn_main))
    application.add_handler(MessageHandler(filters.Regex(r'^⚡ VMess$'), menu_vmess_main))
    application.add_handler(MessageHandler(filters.Regex(r'^🌀 VLess$'), menu_vless_main))
    application.add_handler(MessageHandler(filters.Regex(r'^🛡️ Trojan$'), menu_trojan_main))
    application.add_handler(MessageHandler(filters.Regex(r'^👻 Shadowsocks$'), menu_shdwsk_main))
    application.add_handler(MessageHandler(filters.Regex(r'^⬅️ Kembali'), back_to_main_menu))
    application.add_handler(MessageHandler(filters.Regex(r'^💰 Cek Saldo Saya$'), check_balance_user_handler))
    application.add_handler(MessageHandler(filters.Regex(r'^📄 Riwayat Saya$'), view_transactions_user_handler))
    application.add_handler(MessageHandler(filters.Regex(r'^💳 Top Up Saldo$'), topup_saldo_handler))
    application.add_handler(MessageHandler(filters.Regex(r'^🔄 Refresh$'), show_menu))
    application.add_handler(MessageHandler(filters.Regex(r'^🆓 Coba Gratis'), create_trial_ssh_handler)) # Simplified Regex for all trials
    application.add_handler(MessageHandler(filters.Regex(r'^👤 Manajemen User$'), manage_users_main))
    application.add_handler(MessageHandler(filters.Regex(r'^🛠️ Pengaturan$'), settings_main_menu))
    application.add_handler(MessageHandler(filters.Regex(r'^💾 Backup VPS$'), backup_vps_handler))
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown))
    
    logger.info("Bot is running...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
