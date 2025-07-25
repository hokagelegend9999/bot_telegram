#!/usr/bin/python3
# -*- coding: utf-8 -*-

import logging
import sqlite3
import datetime as DT
import os
import paramiko
import asyncio
import httpx

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters, ConversationHandler
from telegram.error import BadRequest

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# --- KONFIGURASI ---
BOT_TOKEN = '7948291780:AAGMIaOD1cS2l_SZZq6DejAU14VlAWu-sDU'
ADMIN_IDS = [1234567890]
DB_FILE = '/usr/bin/jualan.db'
SSH_HOST = "127.0.0.1"
SSH_USERNAME = os.getenv("SSH_USERNAME", "root")
SSH_PASSWORD = os.getenv("SSH_PASSWORD", "hokage")
SSH_PORT = 2269
ACCOUNT_COST_IDR = 10000.0
QRIS_IMAGE_PATH = "/usr/bin/qris.jpg"
QRIS_IMAGE_URL_FALLBACK = "http://aws.hokagelegend.web.id:89/qris.jpg"
TELEGRAM_ADMIN_USERNAME = "HookageLegend"
TRIAL_COOLDOWN_HOURS = 24

# --- STATES UNTUK CONVERSATIONS ---
(VMESS_GET_USERNAME, VMESS_GET_EXPIRED_DAYS, VMESS_GET_QUOTA, VMESS_GET_IP_LIMIT,
 SHADOWSOCKS_GET_USERNAME, SHADOWSOCKS_GET_EXPIRED_DAYS, SHADOWSOCKS_GET_QUOTA,
 SSH_OVPN_GET_USERNAME, SSH_OVPN_GET_PASSWORD, SSH_OVPN_GET_EXPIRED_DAYS, SSH_OVPN_GET_QUOTA, SSH_OVPN_GET_IP_LIMIT,
 ADD_BALANCE_GET_USER_ID, ADD_BALANCE_GET_AMOUNT,
 CHECK_BALANCE_GET_USER_ID,
 VIEW_USER_TX_GET_USER_ID,
 SETTINGS_MENU,
 VLESS_GET_USERNAME, VLESS_GET_EXPIRED_DAYS, VLESS_GET_QUOTA, VLESS_GET_IP_LIMIT,
 GET_RESTORE_LINK,
 GET_SSH_USER_TO_DELETE, GET_TROJAN_USER_TO_DELETE, GET_VLESS_USER_TO_DELETE,
 GET_VMESS_USER_TO_DELETE, GET_SHADOWSOCKS_USER_TO_DELETE) = range(27)

# --- FUNGSI DATABASE ---
def get_db_connection(): conn = sqlite3.connect(DB_FILE); conn.row_factory = sqlite3.Row; return conn
def migrate_db():
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(users)")
        columns = [info[1] for info in cursor.fetchall()]
        if 'last_trial_at' not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN last_trial_at TEXT")
        conn.commit()
    except sqlite3.Error as e: logger.error(f"Gagal migrasi database: {e}")
    finally: conn.close()
def init_db():
    conn = get_db_connection()
    conn.cursor().execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance REAL DEFAULT 0.0, registered_at TEXT, last_trial_at TEXT)')
    conn.cursor().execute('CREATE TABLE IF NOT EXISTS transactions (transaction_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, type TEXT NOT NULL, amount REAL NOT NULL, timestamp TEXT NOT NULL, description TEXT, FOREIGN KEY (user_id) REFERENCES users (user_id))')
    conn.commit(); conn.close()
    migrate_db()
def get_user_balance(user_id: int) -> float: conn = get_db_connection(); result = conn.cursor().execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)).fetchone(); conn.close(); return result['balance'] if result else 0.0
def update_user_balance(user_id: int, amount: float, transaction_type: str, description: str, is_deduction: bool = False) -> bool:
    conn = get_db_connection()
    try:
        if is_deduction and get_user_balance(user_id) < amount: return False
        cursor = conn.cursor(); cursor.execute(f"UPDATE users SET balance = balance {'-' if is_deduction else '+'} ? WHERE user_id = ?", (amount, user_id))
        ts = DT.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("INSERT INTO transactions (user_id, type, amount, timestamp, description) VALUES (?, ?, ?, ?, ?)", (user_id, transaction_type, amount if not is_deduction else -amount, ts, description))
        conn.commit(); return True
    except sqlite3.Error as e: logger.error(f"DB Error: {e}"); conn.rollback(); return False
    finally:
        if conn: conn.close()
def get_user_transactions(user_id: int, limit: int = 10) -> list: conn = get_db_connection(); txs = conn.cursor().execute("SELECT * FROM transactions WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?", (user_id, limit)).fetchall(); conn.close(); return [dict(row) for row in txs]
def get_all_transactions(limit: int = 20) -> list: conn = get_db_connection(); txs = conn.cursor().execute("SELECT * FROM transactions ORDER BY timestamp DESC LIMIT ?", (limit,)).fetchall(); conn.close(); return [dict(row) for row in txs]
def count_all_users() -> int: conn = get_db_connection(); count = conn.cursor().execute("SELECT COUNT(user_id) FROM users").fetchone()[0]; conn.close(); return count
def get_recent_users(limit: int = 20) -> list: conn = get_db_connection(); users = conn.cursor().execute("SELECT user_id, registered_at FROM users ORDER BY registered_at DESC LIMIT ?", (limit,)).fetchall(); conn.close(); return [dict(row) for row in users]
init_db()

def is_admin(user_id: int) -> bool: return user_id in ADMIN_IDS

# --- KEYBOARDS ---
def get_main_menu_keyboard(): return ReplyKeyboardMarkup([[KeyboardButton('🚀 SSH & OVPN')], [KeyboardButton('⚡ VMess'), KeyboardButton('🌀 VLess')], [KeyboardButton('🛡️ Trojan'), KeyboardButton('👻 Shadowsocks')], [KeyboardButton('💰 Cek Saldo Saya'), KeyboardButton('📄 Riwayat Saya')], [KeyboardButton('💳 Top Up Saldo')], [KeyboardButton('🔄 Refresh')]], resize_keyboard=True)
def get_admin_main_menu_keyboard(): return ReplyKeyboardMarkup([[KeyboardButton('🚀 SSH & OVPN'), KeyboardButton('⚡ VMess'), KeyboardButton('🌀 VLess')], [KeyboardButton('🛡️ Trojan'), KeyboardButton('👻 Shadowsocks')], [KeyboardButton('📈 Status Layanan'), KeyboardButton('🛠️ Pengaturan')], [KeyboardButton('👤 Manajemen User')], [KeyboardButton('💳 Top Up Saldo'), KeyboardButton('🧾 Semua Transaksi')], [KeyboardButton('🔄 Refresh')]], resize_keyboard=True)
def get_manage_users_menu_keyboard(): return ReplyKeyboardMarkup([[KeyboardButton('💵 Tambah Saldo'), KeyboardButton('📊 Cek Saldo User')], [KeyboardButton('📑 Riwayat User'), KeyboardButton('👑 Cek Admin & Saldo')], [KeyboardButton('👥 Jumlah User'), KeyboardButton('🆕 User Terbaru')], [KeyboardButton('🗑️ Hapus User')], [KeyboardButton('⬅️ Kembali ke Menu Admin')]], resize_keyboard=True)
def get_settings_menu_keyboard(): return ReplyKeyboardMarkup([[KeyboardButton('💾 Backup VPS'), KeyboardButton('🔄 Restore VPS')], [KeyboardButton('👁️ Cek Koneksi Aktif'), KeyboardButton('🔄 Restart Layanan')], [KeyboardButton('🧹 Clear Cache')], [KeyboardButton('⚙️ Pengaturan Lain (Soon)')], [KeyboardButton('⬅️ Kembali ke Menu Admin')]], resize_keyboard=True)
def get_ssh_ovpn_menu_keyboard(): return ReplyKeyboardMarkup([[KeyboardButton('➕ Buat Akun SSH Premium'), KeyboardButton('🗑️ Hapus Akun SSH')], [KeyboardButton('🆓 Coba Gratis SSH & OVPN')], [KeyboardButton('ℹ️ Info Layanan SSH')], [KeyboardButton('⬅️ Kembali')]], resize_keyboard=True)
def get_vmess_creation_menu_keyboard(): return ReplyKeyboardMarkup([[KeyboardButton('➕ Buat Akun VMess Premium'), KeyboardButton('🗑️ Hapus Akun VMess')], [KeyboardButton('🆓 Coba Gratis VMess')], [KeyboardButton('📊 Cek Layanan VMess')], [KeyboardButton('⬅️ Kembali')]], resize_keyboard=True)
def get_vless_menu_keyboard(): return ReplyKeyboardMarkup([[KeyboardButton('➕ Buat Akun VLess Premium'), KeyboardButton('🗑️ Hapus Akun VLess')], [KeyboardButton('🆓 Coba Gratis VLess')], [KeyboardButton('📊 Cek Layanan VLess')], [KeyboardButton('⬅️ Kembali')]], resize_keyboard=True)
def get_trojan_menu_keyboard(): return ReplyKeyboardMarkup([[KeyboardButton('➕ Buat Akun Trojan Premium'), KeyboardButton('🗑️ Hapus Akun Trojan')], [KeyboardButton('🆓 Coba Gratis Trojan')], [KeyboardButton('📊 Cek Layanan Trojan')], [KeyboardButton('⬅️ Kembali')]], resize_keyboard=True)
def get_shadowsocks_menu_keyboard(): return ReplyKeyboardMarkup([[KeyboardButton('➕ Buat Akun Shadowsocks'), KeyboardButton('🗑️ Hapus Akun Shadowsocks')], [KeyboardButton('🆓 Coba Gratis Shadowsocks')], [KeyboardButton('📊 Cek Layanan Shadowsocks')], [KeyboardButton('⬅️ Kembali')]], resize_keyboard=True)

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
async def check_and_handle_trial(update: Update, context: ContextTypes.DEFAULT_TYPE, script_path: str, loading_text: str, error_text: str, return_keyboard: ReplyKeyboardMarkup) -> None:
    user_id = update.effective_user.id
    if is_admin(user_id):
        await handle_general_script_button(update, context, script_path, loading_text, error_text, return_keyboard)
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT last_trial_at FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    can_create_trial = True
    if result and result['last_trial_at']:
        last_trial_time = DT.datetime.strptime(result['last_trial_at'], "%Y-%m-%d %H:%M:%S")
        time_since_last_trial = DT.datetime.now() - last_trial_time
        if time_since_last_trial < DT.timedelta(hours=TRIAL_COOLDOWN_HOURS):
            can_create_trial = False
            remaining_time = DT.timedelta(hours=TRIAL_COOLDOWN_HOURS) - time_since_last_trial
            hours, remainder = divmod(remaining_time.seconds, 3600)
            minutes, _ = divmod(remainder, 60)
            await update.message.reply_text(f"🚫 Anda sudah mengambil akun trial hari ini.\n\nSilakan coba lagi dalam <b>{hours} jam {minutes} menit</b>.", parse_mode='HTML', reply_markup=return_keyboard)
    if can_create_trial:
        await update.message.reply_text(f"⏳ *{loading_text}*", parse_mode='HTML')
        creation_result = await run_ssh_command(f"bash {script_path}")
        if "Error:" in creation_result or "Terjadi Kesalahan" in creation_result:
            await update.message.reply_text(f"❌ *{error_text}*\n{creation_result}", parse_mode='HTML', reply_markup=return_keyboard)
        else:
            now_str = DT.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("UPDATE users SET last_trial_at = ? WHERE user_id = ?", (now_str, user_id))
            conn.commit()
            await update.message.reply_text(f"✅ *Hasil:*\n<pre>{creation_result}</pre>", parse_mode='HTML', reply_markup=return_keyboard)
    conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id, user_name = update.effective_user.id, update.effective_user.first_name
    conn = get_db_connection()
    if not conn.cursor().execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,)).fetchone():
        ts = DT.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.cursor().execute("INSERT INTO users (user_id, balance, registered_at, last_trial_at) VALUES (?, ?, ?, NULL)", (user_id, 0.0, ts))
        conn.commit()
        msg = f"🎉 Halo, <b>{user_name}</b>! Selamat datang & selamat terdaftar."
    else: msg = f"👋 Selamat datang kembali, <b>{user_name}</b>!"
    conn.close()
    keyboard = get_admin_main_menu_keyboard() if is_admin(user_id) else get_main_menu_keyboard()
    if is_admin(user_id): msg += "\n\n🛡️ <i>Anda masuk sebagai <b>Admin</b>.</i>"
    await update.message.reply_text(msg, reply_markup=keyboard, parse_mode='HTML')

async def show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = get_admin_main_menu_keyboard() if is_admin(update.effective_user.id) else get_main_menu_keyboard()
    await update.message.reply_text('✨ Silakan pilih layanan:', reply_markup=keyboard, parse_mode='HTML')
async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = get_admin_main_menu_keyboard() if is_admin(update.effective_user.id) else get_main_menu_keyboard()
    await update.message.reply_text('↩️ Operasi dibatalkan.', reply_markup=keyboard); context.user_data.clear(); return ConversationHandler.END
async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = get_admin_main_menu_keyboard() if is_admin(update.effective_user.id) else get_main_menu_keyboard()
    await update.message.reply_text('🤔 Perintah tidak dikenali.', reply_markup=keyboard)
async def handle_general_script_button(update: Update, context: ContextTypes.DEFAULT_TYPE, script: str, loading: str, error: str, keyboard: ReplyKeyboardMarkup) -> None:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("🚫 Perintah ini hanya untuk Admin."); return
    await update.message.reply_text(f"⏳ *{loading}*", parse_mode='HTML')
    result = await run_ssh_command(f"bash {script}")
    if "Error:" in result or "Terjadi Kesalahan" in result:
        await update.message.reply_text(f"❌ *{error}*\n{result}", parse_mode='HTML', reply_markup=keyboard)
    else: await update.message.reply_text(f"✅ *Hasil:*\n<pre>{result}</pre>", parse_mode='HTML', reply_markup=keyboard)

async def menu_ssh_ovpn_main(u,c): await u.message.reply_text("🚀 *Menu SSH & OVPN*", reply_markup=get_ssh_ovpn_menu_keyboard(), parse_mode='HTML')
async def menu_vmess_main(u,c): await u.message.reply_text("⚡ *Menu VMess*", reply_markup=get_vmess_creation_menu_keyboard(), parse_mode='HTML')
async def menu_vless_main(u,c): await u.message.reply_text("🌀 *Menu VLess*", reply_markup=get_vless_menu_keyboard(), parse_mode='HTML')
async def menu_trojan_main(u,c): await u.message.reply_text("🛡️ *Menu Trojan*", reply_markup=get_trojan_menu_keyboard(), parse_mode='HTML')
async def menu_shdwsk_main(u,c): await u.message.reply_text("👻 *Menu Shadowsocks*", reply_markup=get_shadowsocks_menu_keyboard(), parse_mode='HTML')
async def back_to_main_menu(u,c): await show_menu(u, c)

async def create_trial_ssh_handler(u,c): await check_and_handle_trial(u,c,'/usr/bin/bot-trial','Membuat trial SSH...','Gagal membuat trial SSH.',get_ssh_ovpn_menu_keyboard())
async def create_trial_vless_handler(u,c): await check_and_handle_trial(u,c,'/usr/bin/bot-trialvless','Membuat trial VLESS...','Gagal membuat trial VLESS.',get_vless_menu_keyboard())
async def create_trial_trojan_handler(u,c): await check_and_handle_trial(u,c,'/usr/bin/bot-trialtrojan','Membuat trial Trojan...','Gagal membuat trial Trojan.',get_trojan_menu_keyboard())
async def create_trial_vmess_handler(u,c): await check_and_handle_trial(u,c,'/usr/bin/bot-trialws','Membuat trial VMess...','Gagal membuat trial VMess.',get_vmess_creation_menu_keyboard())
async def create_trial_shdwsk_handler(u,c): await check_and_handle_trial(u,c,'/usr/bin/bot-trialss','Membuat trial Shadowsocks...','Gagal membuat trial Shadowsocks.',get_shadowsocks_menu_keyboard())
async def topup_saldo_handler(u,c):
    user_id = u.effective_user.id; current_balance = get_user_balance(user_id); wa_number = "6287726917005"
    caption = (f"💰*TOP UP SALDO | HOKAGE LEGEND*💰\n══════════════════════\n\n"
               f"Saldo Anda Saat Ini: <b>Rp {current_balance:,.0f},-</b>\n\n"
               f"<b><u>Metode Pembayaran:</u></b>\n"
               f"1. Silakan transfer ke rekening di bawah ini atau scan QRIS (jika tersedia).\n"
               f"   🏦 <b>Bank:</b> [BANK MANDIRI]\n"
               f"   💳 <b>No. Rekening:</b> [164-00-0291548-8]\n"
               f"   👤 <b>Atas Nama:</b> [DEDEN IRWANSYAH ATMAJA.]\n\n"
               f"<b><u>Setelah Transfer:</u></b>\n"
               f"Mohon kirim bukti transfer beserta User ID Telegram Anda di bawah ini untuk konfirmasi:\n"
               f"<code>{user_id}</code> (klik untuk salin)\n\n"
               f"👇 **Kirim Konfirmasi Ke:** 👇\n"
               f"💬 <a href='https://wa.me/{wa_number}?text=Halo%20admin,%20saya%20mau%20konfirmasi%20top%20up%20saldo.%0AUser%20ID:%20{user_id}'><b>Konfirmasi via WhatsApp</b></a>\n"
               f"✈️ <a href='https://t.me/{TELEGRAM_ADMIN_USERNAME}'><b>Konfirmasi via Telegram</b></a>\n\n"
               f"<i>Saldo akan ditambahkan oleh Admin setelah verifikasi. Terima kasih!</i>")
    keyboard = get_admin_main_menu_keyboard() if is_admin(user_id) else get_main_menu_keyboard()
    if os.path.exists(QRIS_IMAGE_PATH):
        try:
            with open(QRIS_IMAGE_PATH, 'rb') as photo: await u.message.reply_photo(photo=photo, caption=caption, parse_mode='HTML', reply_markup=keyboard)
        except Exception as e: logger.error(f"Gagal mengirim foto QRIS: {e}"); await u.message.reply_text(f"Gagal memuat gambar QRIS.\n\n{caption}", parse_mode='HTML', reply_markup=keyboard)
    else: await u.message.reply_text(caption, parse_mode='HTML', reply_markup=keyboard)

async def check_balance_user_handler(u,c): await u.message.reply_text(f"💰 Saldo Anda: <b>Rp {get_user_balance(u.effective_user.id):,.0f}</b>", parse_mode='HTML')
async def view_transactions_user_handler(u,c):
    txs = get_user_transactions(u.effective_user.id)
    msg = "📄 *Riwayat Transaksi:*\n\n" + "\n".join([f"<b>{'🟢 +' if tx['amount'] >= 0 else '🔴'} Rp {abs(tx['amount']):,.0f}</b> - <i>{tx['type'].replace('_', ' ').title()}</i>\n<pre>  {tx['timestamp']}</pre>" for tx in txs]) if txs else "📂 Riwayat Kosong."
    await u.message.reply_text(msg, parse_mode='HTML')
async def manage_users_main(u,c):
    if not is_admin(u.effective_user.id): return
    await u.message.reply_text("👤 *Manajemen Pengguna*", reply_markup=get_manage_users_menu_keyboard(), parse_mode='HTML')
async def view_admins_handler(u,c):
    if not is_admin(u.effective_user.id): return
    await u.message.reply_text("⏳ Mengambil data admin...", parse_mode='HTML')
    info = ["👑 *Daftar Admin & Saldo*"]
    for admin_id in ADMIN_IDS:
        try: chat = await c.bot.get_chat(admin_id); name = f"{chat.first_name} (@{chat.username or 'N/A'})"
        except: name = "<i>(Gagal ambil nama)</i>"
        info.append(f"👤 <b>{name}</b>\n   - ID: <code>{admin_id}</code>\n   - Saldo: <b>Rp {get_user_balance(admin_id):,.0f}</b>")
    await u.message.reply_text("\n\n".join(info), parse_mode='HTML', reply_markup=get_manage_users_menu_keyboard())
async def total_users_handler(u,c):
    if not is_admin(u.effective_user.id): return
    await u.message.reply_text(f"📊 Total Pengguna: <b>{count_all_users()}</b>", parse_mode='HTML', reply_markup=get_manage_users_menu_keyboard())
async def recent_users_handler(u,c):
    if not is_admin(u.effective_user.id): return
    users = get_recent_users()
    msg = "🆕 *20 Pengguna Terbaru*\n\n" + "\n".join([f"👤 <code>{u['user_id']}</code> (Daftar: <i>{u['registered_at']}</i>)" for u in users]) if users else "ℹ️ Belum ada pengguna."
    await u.message.reply_text(msg, parse_mode='HTML', reply_markup=get_manage_users_menu_keyboard())
async def settings_main_menu(u,c): await u.message.reply_text("🛠️ *Pengaturan*", reply_markup=get_settings_menu_keyboard(), parse_mode='HTML')
async def backup_vps_handler(u,c): await handle_general_script_button(u,c,'/usr/bin/bot-backup','Memulai backup...','Gagal backup.',get_settings_menu_keyboard())
async def check_connections_handler(u,c): await handle_general_script_button(u,c,'/usr/bin/bot-cek-login-ssh','Memeriksa koneksi...','Gagal periksa koneksi.',get_settings_menu_keyboard())
async def restart_services_handler(u,c): await handle_general_script_button(u,c,'/usr/bin/resservice','Merestart semua layanan...','Gagal merestart layanan.',get_settings_menu_keyboard())
async def clear_cache_handler(u,c): await handle_general_script_button(u,c,'/usr/bin/bot-clearcache','Membersihkan RAM Cache...','Gagal membersihkan cache.',get_settings_menu_keyboard())
async def check_vmess_service_handler(u,c):
    if not is_admin(u.effective_user.id): await u.message.reply_text("🚫 Hanya untuk Admin."); return
    await handle_general_script_button(u,c,'/usr/bin/bot-cek-ws', 'Memeriksa Pengguna Login...', 'Gagal memeriksa pengguna.', get_vmess_creation_menu_keyboard())
async def check_vless_service_handler(u,c):
    if not is_admin(u.effective_user.id): await u.message.reply_text("🚫 Hanya untuk Admin."); return
    await handle_general_script_button(u,c,'/usr/bin/bot-cek-vless', 'Memeriksa Pengguna Login...', 'Gagal memeriksa pengguna.', get_vless_menu_keyboard())
async def check_trojan_service_handler(u,c):
    if not is_admin(u.effective_user.id): await u.message.reply_text("🚫 Hanya untuk Admin."); return
    await handle_general_script_button(u,c,'/usr/bin/bot-cek-tr', 'Memeriksa Pengguna Login...', 'Gagal memeriksa pengguna.', get_trojan_menu_keyboard())
async def check_shadowsocks_service_handler(u,c):
    if not is_admin(u.effective_user.id): await u.message.reply_text("🚫 Hanya untuk Admin."); return
    await handle_general_script_button(u,c,'/usr/bin/bot-cek-ss', 'Memeriksa Pengguna Login...', 'Gagal memeriksa pengguna.', get_shadowsocks_menu_keyboard())
async def check_service_admin_handler(u,c):
    if not is_admin(u.effective_user.id): return
    await handle_general_script_button(u,c, '/usr/bin/resservice', 'Memeriksa status layanan...', 'Gagal memeriksa status.', get_admin_main_menu_keyboard())
async def view_all_transactions_admin_handler(u,c):
    if not is_admin(u.effective_user.id): return
    txs = get_all_transactions()
    msg = "🧾 *20 Transaksi Terbaru*\n\n" + "".join([f"👤 <code>{tx['user_id']}</code>: {'🟢 +' if tx['amount'] >= 0 else '🔴'}<b>Rp {abs(tx['amount']):,.0f}</b>\n<i>({tx['type'].replace('_', ' ').title()})</i>\n" for tx in txs]) if txs else "📂 Belum ada transaksi."
    await u.message.reply_text(msg, parse_mode='HTML', reply_markup=get_admin_main_menu_keyboard())
def create_conversation_prompt(prompt_text: str) -> str: return f"{prompt_text}\n\n<i>Ketik /cancel untuk batal.</i>"
async def start_account_creation(u,c,srv,cost,next_st,kbd):
    user_id = u.effective_user.id
    if is_admin(user_id):
        await u.message.reply_text(create_conversation_prompt(f"👑 <b>Mode Admin</b>\n📝 Masukkan <b>Username</b> untuk {srv}:"), parse_mode='HTML'); return next_st
    balance = get_user_balance(user_id)
    if balance < cost:
        await u.message.reply_text(f"🚫 <b>Saldo Tidak Cukup!</b>\n\nSaldo Anda: <b>Rp {balance:,.0f}</b>\nBiaya Akun: <b>Rp {cost:,.0f}</b>", reply_markup=kbd, parse_mode='HTML'); return ConversationHandler.END
    else:
        await u.message.reply_text(create_conversation_prompt(f"✅ Saldo Cukup.\n📝 Masukkan <b>Username</b> untuk {srv}:"), parse_mode='HTML'); return next_st
async def get_valid_username(u,c,key,next_st,prompt):
    if not (uname := u.message.text) or not uname.isalnum() and "_" not in uname: await u.message.reply_text(create_conversation_prompt("⚠️ Username tdk valid."), parse_mode='HTML'); return c.state
    c.user_data[key] = uname; await u.message.reply_text(create_conversation_prompt(f"✅ OK. {prompt}"), parse_mode='HTML'); return next_st
async def get_numeric_input(u,c,key,next_st,field,prompt):
    if not (inp := u.message.text).isdigit() or int(inp) <= 0: await u.message.reply_text(create_conversation_prompt(f"⚠️ {field} harus angka."), parse_mode='HTML'); return c.state
    c.user_data[key] = int(inp); await u.message.reply_text(create_conversation_prompt(f"✅ OK. {prompt}"), parse_mode='HTML'); return next_st
async def process_account_creation(u,c,srv,scr,params,cost,kbd):
    uid, is_adm = u.effective_user.id, is_admin(u.effective_user.id)
    if not is_adm:
        if get_user_balance(uid) < cost: await u.message.reply_text("🚫 Saldo habis.", reply_markup=kbd); return ConversationHandler.END
        update_user_balance(uid, cost, 'creation', f"Buat {srv}: {params[0]}", True); await u.message.reply_text(f"💸 Saldo dikurangi. Sisa: Rp{get_user_balance(uid):,.0f}\n⏳ Membuat akun...", parse_mode='HTML')
    else: await u.message.reply_text(f"👑 Membuat akun {srv}...", parse_mode='HTML')
    res = await run_ssh_command(f"bash {scr} {' '.join(map(str, params))}")
    if "Error:" in res or "Terjadi Kesalahan" in res:
        if not is_adm: update_user_balance(uid, cost, 'refund', f"Gagal {srv}: {params[0]}"); await u.message.reply_text(f"❌ Gagal!\n{res}\n✅ Saldo dikembalikan.", reply_markup=kbd, parse_mode='HTML')
        else: await u.message.reply_text(f"❌ Gagal (Admin)!\n{res}", reply_markup=kbd, parse_mode='HTML')
    else: await u.message.reply_text(f"🎉 Akun {srv} Dibuat!\n<pre>{res}</pre>", reply_markup=kbd, parse_mode='HTML')
    c.user_data.clear(); return ConversationHandler.END
async def create_akun_ssh_start(u,c): return await start_account_creation(u,c,"SSH & OVPN",ACCOUNT_COST_IDR,SSH_OVPN_GET_USERNAME,get_ssh_ovpn_menu_keyboard())
async def ssh_get_username(u,c): return await get_valid_username(u,c,'username',SSH_OVPN_GET_PASSWORD,"Masukkan Password:")
async def ssh_get_password(u,c): c.user_data['password']=u.message.text; return await get_numeric_input(u,c,'expired_days',SSH_OVPN_GET_EXPIRED_DAYS,"Password","Masa Aktif (hari):")
async def ssh_get_expired_days(u,c): return await get_numeric_input(u,c,'expired_days',SSH_OVPN_GET_QUOTA,"Masa Aktif","Kuota (GB):")
async def ssh_get_quota(u,c): return await get_numeric_input(u,c,'quota',SSH_OVPN_GET_IP_LIMIT,"Kuota","Batas IP:")
async def ssh_get_ip_limit(u,c): await get_numeric_input(u,c,'ip_limit',-1,"Batas IP",""); params=[c.user_data['username'],c.user_data.get('password','12345'),c.user_data['expired_days'],c.user_data['quota'],c.user_data['ip_limit']]; return await process_account_creation(u,c,"SSH & OVPN","/usr/bin/addssh-bot",params,ACCOUNT_COST_IDR,get_ssh_ovpn_menu_keyboard())
async def create_akun_vmess_start(u,c): return await start_account_creation(u,c,"VMess",ACCOUNT_COST_IDR,VMESS_GET_USERNAME,get_vmess_creation_menu_keyboard())
async def vmess_get_username(u,c): return await get_valid_username(u,c,'username',VMESS_GET_EXPIRED_DAYS,"Masa Aktif (hari):")
async def vmess_get_expired_days(u,c): return await get_numeric_input(u,c,'expired_days',VMESS_GET_QUOTA,"Masa Aktif","Kuota (GB):")
async def vmess_get_quota(u,c): return await get_numeric_input(u,c,'quota',VMESS_GET_IP_LIMIT,"Kuota","Batas IP:")
async def vmess_get_ip_limit(u,c): await get_numeric_input(u,c,'ip_limit',-1,"Batas IP",""); params = [c.user_data['username'], c.user_data['expired_days'], c.user_data['quota'], c.user_data['ip_limit']]; return await process_account_creation(u,c,"VMess","/usr/bin/addws-bot",params,ACCOUNT_COST_IDR,get_vmess_creation_menu_keyboard())
async def create_akun_vless_start(u,c): return await start_account_creation(u,c,"VLess",ACCOUNT_COST_IDR,VLESS_GET_USERNAME,get_vless_menu_keyboard())
async def vless_get_username(u,c): return await get_valid_username(u,c,'username',VLESS_GET_EXPIRED_DAYS,"Masa Aktif (hari):")
async def vless_get_expired_days(u,c): return await get_numeric_input(u,c,'expired_days',VLESS_GET_QUOTA,"Masa Aktif","Kuota (GB):")
async def vless_get_quota(u,c): return await get_numeric_input(u,c,'quota',VLESS_GET_IP_LIMIT,"Kuota","Batas IP:")
async def vless_get_ip_limit(u,c): await get_numeric_input(u,c,'ip_limit',-1,"Batas IP",""); params = [c.user_data['username'], c.user_data['expired_days'], c.user_data['quota'], c.user_data['ip_limit']]; return await process_account_creation(u,c,"VLess","/usr/bin/addvless-bot",params,ACCOUNT_COST_IDR,get_vless_menu_keyboard())
async def create_akun_shdwsk_start(u,c): return await start_account_creation(u,c,"Shadowsocks",ACCOUNT_COST_IDR,SHADOWSOCKS_GET_USERNAME,get_shadowsocks_menu_keyboard())
async def shdwsk_get_username(u,c): return await get_valid_username(u,c,'username',SHADOWSOCKS_GET_EXPIRED_DAYS,"Masa Aktif (hari):")
async def shdwsk_get_expired_days(u,c): return await get_numeric_input(u,c,'expired_days',SHADOWSOCKS_GET_QUOTA,"Masa Aktif","Kuota (GB):")
async def shdwsk_get_quota(u,c): await get_numeric_input(u,c,'quota',-1,"Kuota",""); params = [c.user_data['username'], c.user_data['expired_days'], c.user_data['quota']]; return await process_account_creation(u,c,"Shadowsocks","/usr/bin/addss-bot",params,ACCOUNT_COST_IDR,get_shadowsocks_menu_keyboard())
async def add_balance_conversation_start(u,c):
    if not is_admin(u.effective_user.id): return ConversationHandler.END
    await u.message.reply_text(create_conversation_prompt("👤 Masukkan *User ID* target:"), parse_mode='HTML'); return ADD_BALANCE_GET_USER_ID
async def add_balance_get_user_id_step(u,c):
    if not (uid_str := u.message.text).isdigit(): await u.message.reply_text(create_conversation_prompt("⚠️ User ID tidak valid."), parse_mode='HTML'); return ADD_BALANCE_GET_USER_ID
    c.user_data['target_user_id'] = int(uid_str); await u.message.reply_text(create_conversation_prompt(f"✅ OK.\n💵 Masukkan *jumlah saldo*:"), parse_mode='HTML'); return ADD_BALANCE_GET_AMOUNT
async def add_balance_get_amount_step(u,c):
    if not (amount_str := u.message.text).replace('.', '', 1).isdigit() or float(amount_str) <= 0: await u.message.reply_text(create_conversation_prompt("⚠️ Jumlah tidak valid."), parse_mode='HTML'); return ADD_BALANCE_GET_AMOUNT
    target_id, amount = c.user_data['target_user_id'], float(amount_str)
    if update_user_balance(target_id, amount, 'topup_admin', f"Topup oleh admin {u.effective_user.id}"):
        await u.message.reply_text(f"✅ Saldo user <code>{target_id}</code> ditambah Rp {amount:,.0f}.\nSaldo baru: <b>Rp {get_user_balance(target_id):,.0f}</b>", parse_mode='HTML', reply_markup=get_manage_users_menu_keyboard())
    else: await u.message.reply_text("❌ Gagal menambah saldo.", reply_markup=get_manage_users_menu_keyboard())
    return ConversationHandler.END
async def check_user_balance_conversation_start(u,c):
    if not is_admin(u.effective_user.id): return ConversationHandler.END
    await u.message.reply_text(create_conversation_prompt("👤 Masukkan *User ID* yang ingin dicek:"), parse_mode='HTML'); return CHECK_BALANCE_GET_USER_ID
async def check_user_balance_get_user_id_step(u,c):
    if not (uid_str := u.message.text).isdigit(): await u.message.reply_text(create_conversation_prompt("⚠️ User ID tidak valid."), parse_mode='HTML'); return CHECK_BALANCE_GET_USER_ID
    target_id = int(uid_str); await u.message.reply_text(f"📊 Saldo user <code>{target_id}</code>: <b>Rp {get_user_balance(target_id):,.0f},-</b>", parse_mode='HTML', reply_markup=get_manage_users_menu_keyboard()); return ConversationHandler.END
async def view_user_tx_conversation_start(u,c):
    if not is_admin(u.effective_user.id): return ConversationHandler.END
    await u.message.reply_text(create_conversation_prompt("👤 Masukkan *User ID* untuk lihat riwayat:"), parse_mode='HTML'); return VIEW_USER_TX_GET_USER_ID
async def view_user_tx_get_user_id_step(u,c):
    if not (uid_str := u.message.text).isdigit(): await u.message.reply_text(create_conversation_prompt("⚠️ User ID tidak valid."), parse_mode='HTML'); return VIEW_USER_TX_GET_USER_ID
    target_id, txs = int(uid_str), get_user_transactions(int(uid_str))
    msg = f"📑 Riwayat Transaksi User {target_id}:\n\n" + "\n".join([f"<b>{'🟢 +' if tx['amount'] >= 0 else '🔴'} Rp {abs(tx['amount']):,.0f}</b> - <i>{tx['type'].replace('_', ' ').title()}</i>" for tx in txs]) if txs else f"📂 Riwayat user <code>{target_id}</code> kosong."
    await u.message.reply_text(msg, parse_mode='HTML', reply_markup=get_manage_users_menu_keyboard()); return ConversationHandler.END
async def restore_vps_start(u,c):
    if not is_admin(u.effective_user.id): return ConversationHandler.END
    await u.message.reply_text(create_conversation_prompt("⚠️ *PERINGATAN!* ⚠️\nProses ini akan menimpa data.\n\nKirimkan **link download** `backup.zip`:"), parse_mode='HTML'); return GET_RESTORE_LINK
async def get_restore_link_and_run(u,c):
    link = u.message.text
    if not link or not link.startswith('http'): await u.message.reply_text("❌ Link tidak valid.", reply_markup=get_settings_menu_keyboard()); return ConversationHandler.END
    await u.message.reply_text("⏳ *Memulai restore...*", parse_mode='HTML')
    result = await run_ssh_command(f"bash /usr/bin/bot-restore '{link}'")
    await u.message.reply_text(f"✅ *Hasil Restore:*\n<pre>{result}</pre>", parse_mode='HTML', reply_markup=get_admin_main_menu_keyboard()); return ConversationHandler.END
async def delete_ssh_start(u,c):
    if not is_admin(u.effective_user.id): return ConversationHandler.END
    user_list = await run_ssh_command("bash /usr/bin/bot-list-ssh"); await u.message.reply_text(f"<pre>{user_list}</pre>\n\n" + create_conversation_prompt("👆 Ketik *Username* yang ingin dihapus:"), parse_mode='HTML'); return GET_SSH_USER_TO_DELETE
async def delete_ssh_get_user(u,c):
    username = u.message.text.strip()
    if not username: await u.message.reply_text("Username kosong.", reply_markup=get_ssh_ovpn_menu_keyboard()); return ConversationHandler.END
    result = await run_ssh_command(f"bash /usr/bin/bot-delssh '{username}'")
    await u.message.reply_text(result, reply_markup=get_ssh_ovpn_menu_keyboard()); return ConversationHandler.END
async def delete_trojan_start(u,c):
    if not is_admin(u.effective_user.id): return ConversationHandler.END
    user_list = await run_ssh_command("bash /usr/bin/bot-list-trojan"); await u.message.reply_text(f"<pre>{user_list}</pre>\n\n" + create_conversation_prompt("👆 Ketik *Username* yang ingin dihapus:"), parse_mode='HTML'); return GET_TROJAN_USER_TO_DELETE
async def delete_trojan_get_user(u,c):
    username = u.message.text.strip()
    if not username: await u.message.reply_text("Username kosong.", reply_markup=get_trojan_menu_keyboard()); return ConversationHandler.END
    result = await run_ssh_command(f"bash /usr/bin/bot-del-trojan '{username}'")
    await u.message.reply_text(result, reply_markup=get_trojan_menu_keyboard()); return ConversationHandler.END
async def delete_vless_start(u,c):
    if not is_admin(u.effective_user.id): return ConversationHandler.END
    user_list = await run_ssh_command("bash /usr/bin/bot-list-vless"); await u.message.reply_text(f"<pre>{user_list}</pre>\n\n" + create_conversation_prompt("👆 Ketik *Username* yang ingin dihapus:"), parse_mode='HTML'); return GET_VLESS_USER_TO_DELETE
async def delete_vless_get_user(u,c):
    username = u.message.text.strip()
    if not username: await u.message.reply_text("Username kosong.", reply_markup=get_vless_menu_keyboard()); return ConversationHandler.END
    result = await run_ssh_command(f"bash /usr/bin/bot-del-vless '{username}'")
    await u.message.reply_text(result, reply_markup=get_vless_menu_keyboard()); return ConversationHandler.END
async def delete_vmess_start(u,c):
    if not is_admin(u.effective_user.id): return ConversationHandler.END
    user_list = await run_ssh_command("bash /usr/bin/bot-list-vmess"); await u.message.reply_text(f"<pre>{user_list}</pre>\n\n" + create_conversation_prompt("👆 Ketik *Username* yang ingin dihapus:"), parse_mode='HTML'); return GET_VMESS_USER_TO_DELETE
async def delete_vmess_get_user(u,c):
    username = u.message.text.strip()
    if not username: await u.message.reply_text("Username kosong.", reply_markup=get_vmess_creation_menu_keyboard()); return ConversationHandler.END
    result = await run_ssh_command(f"bash /usr/bin/bot-del-vmess '{username}'")
    await u.message.reply_text(result, reply_markup=get_vmess_creation_menu_keyboard()); return ConversationHandler.END
async def delete_shadowsocks_start(u,c):
    if not is_admin(u.effective_user.id): return ConversationHandler.END
    user_list = await run_ssh_command("bash /usr/bin/bot-list-shadowsocks"); await u.message.reply_text(f"<pre>{user_list}</pre>\n\n" + create_conversation_prompt("👆 Ketik *Username* yang ingin dihapus:"), parse_mode='HTML'); return GET_SHADOWSOCKS_USER_TO_DELETE
async def delete_shadowsocks_get_user(u,c):
    username = u.message.text.strip()
    if not username: await u.message.reply_text("Username kosong.", reply_markup=get_shadowsocks_menu_keyboard()); return ConversationHandler.END
    result = await run_ssh_command(f"bash /usr/bin/bot-del-ss '{username}'")
    await u.message.reply_text(result, reply_markup=get_shadowsocks_menu_keyboard()); return ConversationHandler.END

def main() -> None:
    application = Application.builder().token(BOT_TOKEN).build()

    # job_queue = application.job_queue
    # if job_queue:
    #     job_queue.run_repeating(periodic_license_check, interval=DT.timedelta(hours=LICENSE_CHECK_INTERVAL_HOURS))

    cancel_handler = CommandHandler("cancel", cancel_conversation)

    conv_handlers = [
        ConversationHandler(entry_points=[MessageHandler(filters.Regex(r'Buat Akun SSH Premium$'), create_akun_ssh_start)], states={SSH_OVPN_GET_USERNAME:[MessageHandler(filters.TEXT&~filters.COMMAND, ssh_get_username)], SSH_OVPN_GET_PASSWORD:[MessageHandler(filters.TEXT&~filters.COMMAND, ssh_get_password)], SSH_OVPN_GET_EXPIRED_DAYS:[MessageHandler(filters.TEXT&~filters.COMMAND, ssh_get_expired_days)], SSH_OVPN_GET_QUOTA:[MessageHandler(filters.TEXT&~filters.COMMAND, ssh_get_quota)], SSH_OVPN_GET_IP_LIMIT:[MessageHandler(filters.TEXT&~filters.COMMAND, ssh_get_ip_limit)]}, fallbacks=[cancel_handler]),
        ConversationHandler(entry_points=[MessageHandler(filters.Regex(r'Buat Akun VMess Premium$'), create_akun_vmess_start)], states={VMESS_GET_USERNAME:[MessageHandler(filters.TEXT&~filters.COMMAND, vmess_get_username)], VMESS_GET_EXPIRED_DAYS:[MessageHandler(filters.TEXT&~filters.COMMAND, vmess_get_expired_days)], VMESS_GET_QUOTA:[MessageHandler(filters.TEXT&~filters.COMMAND, vmess_get_quota)], VMESS_GET_IP_LIMIT:[MessageHandler(filters.TEXT&~filters.COMMAND, vmess_get_ip_limit)]}, fallbacks=[cancel_handler]),
        ConversationHandler(entry_points=[MessageHandler(filters.Regex(r'Buat Akun VLess Premium$'), create_akun_vless_start)], states={VLESS_GET_USERNAME:[MessageHandler(filters.TEXT&~filters.COMMAND, vless_get_username)], VLESS_GET_EXPIRED_DAYS:[MessageHandler(filters.TEXT&~filters.COMMAND, vless_get_expired_days)], VLESS_GET_QUOTA:[MessageHandler(filters.TEXT&~filters.COMMAND, vless_get_quota)], VLESS_GET_IP_LIMIT:[MessageHandler(filters.TEXT&~filters.COMMAND, vless_get_ip_limit)]}, fallbacks=[cancel_handler]),
        ConversationHandler(entry_points=[MessageHandler(filters.Regex(r'Buat Akun Shadowsocks$'), create_akun_shdwsk_start)], states={SHADOWSOCKS_GET_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, shdwsk_get_username)], SHADOWSOCKS_GET_EXPIRED_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, shdwsk_get_expired_days)], SHADOWSOCKS_GET_QUOTA: [MessageHandler(filters.TEXT & ~filters.COMMAND, shdwsk_get_quota)]}, fallbacks=[cancel_handler]),
        ConversationHandler(entry_points=[MessageHandler(filters.Regex(r'^💵 Tambah Saldo$'), add_balance_conversation_start)], states={ADD_BALANCE_GET_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_balance_get_user_id_step)], ADD_BALANCE_GET_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_balance_get_amount_step)]}, fallbacks=[cancel_handler]),
        ConversationHandler(entry_points=[MessageHandler(filters.Regex(r'^📊 Cek Saldo User$'), check_user_balance_conversation_start)], states={CHECK_BALANCE_GET_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, check_user_balance_get_user_id_step)]}, fallbacks=[cancel_handler]),
        ConversationHandler(entry_points=[MessageHandler(filters.Regex(r'^📑 Riwayat User$'), view_user_tx_conversation_start)], states={VIEW_USER_TX_GET_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, view_user_tx_get_user_id_step)]}, fallbacks=[cancel_handler]),
        ConversationHandler(entry_points=[MessageHandler(filters.Regex(r'^🔄 Restore VPS$'), restore_vps_start)], states={GET_RESTORE_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_restore_link_and_run)]}, fallbacks=[cancel_handler]),
        ConversationHandler(entry_points=[MessageHandler(filters.Regex(r'Hapus Akun SSH$'), delete_ssh_start)], states={GET_SSH_USER_TO_DELETE: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_ssh_get_user)]}, fallbacks=[cancel_handler]),
        ConversationHandler(entry_points=[MessageHandler(filters.Regex(r'Hapus Akun Trojan$'), delete_trojan_start)], states={GET_TROJAN_USER_TO_DELETE: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_trojan_get_user)]}, fallbacks=[cancel_handler]),
        ConversationHandler(entry_points=[MessageHandler(filters.Regex(r'Hapus Akun VLess$'), delete_vless_start)], states={GET_VLESS_USER_TO_DELETE: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_vless_get_user)]}, fallbacks=[cancel_handler]),
        ConversationHandler(entry_points=[MessageHandler(filters.Regex(r'Hapus Akun VMess$'), delete_vmess_start)], states={GET_VMESS_USER_TO_DELETE: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_vmess_get_user)]}, fallbacks=[cancel_handler]),
        ConversationHandler(entry_points=[MessageHandler(filters.Regex(r'Hapus Akun Shadowsocks$'), delete_shadowsocks_start)], states={GET_SHADOWSOCKS_USER_TO_DELETE: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_shadowsocks_get_user)]}, fallbacks=[cancel_handler]),
    ]
    application.add_handlers(conv_handlers)

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", show_menu))

    message_handlers = {
        r'^🚀 SSH & OVPN$': menu_ssh_ovpn_main, r'^⚡ VMess$': menu_vmess_main,
        r'^🌀 VLess$': menu_vless_main, r'^🛡️ Trojan$': menu_trojan_main,
        r'^👻 Shadowsocks$': menu_shdwsk_main, r'^⬅️ Kembali': back_to_main_menu,
        r'^💰 Cek Saldo Saya$': check_balance_user_handler, r'^📄 Riwayat Saya$': view_transactions_user_handler,
        r'^💳 Top Up Saldo$': topup_saldo_handler, r'^🔄 Refresh$': show_menu,
        r'^🆓 Coba Gratis SSH & OVPN$': create_trial_ssh_handler,
        r'^🆓 Coba Gratis VLess$': create_trial_vless_handler,
        r'^🆓 Coba Gratis VMess$': create_trial_vmess_handler,
        r'^🆓 Coba Gratis Trojan$': create_trial_trojan_handler,
        r'^🆓 Coba Gratis Shadowsocks$': create_trial_shdwsk_handler,
        r'^👤 Manajemen User$': manage_users_main,
        r'^🛠️ Pengaturan$': settings_main_menu,
        r'^💾 Backup VPS$': backup_vps_handler,
        r'^📈 Status Layanan$': check_service_admin_handler,
        r'^👑 Cek Admin & Saldo$': view_admins_handler,
        r'^👥 Jumlah User$': total_users_handler,
        r'^🆕 User Terbaru$': recent_users_handler,
        r'^👁️ Cek Koneksi Aktif$': check_connections_handler,
        r'^🧾 Semua Transaksi$': view_all_transactions_admin_handler,
        r'^🔄 Restart Layanan$': restart_services_handler,
        r'^🧹 Clear Cache$': clear_cache_handler,
        r'^📊 Cek Layanan VMess$': check_vmess_service_handler,
        r'^📊 Cek Layanan VLess$': check_vless_service_handler,
        r'^📊 Cek Layanan Trojan$': check_trojan_service_handler,
        r'^📊 Cek Layanan Shadowsocks$': check_shadowsocks_service_handler
    }
    for regex, func in message_handlers.items(): application.add_handler(MessageHandler(filters.Regex(regex), func))

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown))

    logger.info("Bot is running...")
    application.run_polling()

if __name__ == "__main__":
    main()
