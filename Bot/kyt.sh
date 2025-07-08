#!/bin/bash
# Script Installer Bot Panel - Versi Perbaikan Final

# --- 1. PEMBERSIHAN INSTALASI LAMA ---
echo "Membersihkan instalasi lama..."
sudo systemctl stop kyt.service > /dev/null 2>&1
sudo systemctl disable kyt.service > /dev/null 2>&1
sudo rm -f /etc/systemd/system/kyt.service
sudo rm -rf /usr/bin/kyt /usr/bin/bot
sudo rm -f /usr/bin/bot-*
sudo rm -rf /etc/bot

# --- 2. INSTALASI DEPENDENSI DASAR ---
echo "Menginstall dependensi sistem..."
sudo apt-get update > /dev/null 2>&1
sudo apt-get install -y python3 python3-pip git unzip neofetch lolcat figlet

# --- 3. MENGUNDUH & MENATA KEDUA KOMPONEN BOT ---
echo "Mengunduh dan menata file bot..."
cd /tmp
# Hapus sisa unduhan lama
rm -rf kyt kyt.zip bot bot.zip

# Mengunduh Aplikasi Utama (kyt.zip)
wget -q -O kyt.zip https://raw.githubusercontent.com/hokagelegend9999/bot_telegram/main/Bot/kyt.zip
# Mengunduh Skrip Bantuan (bot.zip)
wget -q -O bot.zip https://raw.githubusercontent.com/hokagelegend9999/bot_telegram/main/Bot/bot.zip

# Ekstrak kedua file zip
unzip -o kyt.zip
unzip -o bot.zip

# Pindahkan file ke lokasi yang benar
sudo mv kyt /usr/bin/     # Memindahkan aplikasi utama ke /usr/bin/kyt
sudo mv bot/* /usr/bin/    # Memindahkan semua skrip bantuan ke /usr/bin/
sudo chmod +x /usr/bin/bot* # Memberikan izin eksekusi

# --- 4. INSTALASI DEPENDENSI PYTHON ---
echo "Menginstall library Python..."
# Menggunakan requirements.txt dari aplikasi utama
sudo pip3 install --break-system-packages -r /usr/bin/kyt/requirements.txt

# --- 5. KONFIGURASI BOT ---
export domain=$(cat /etc/xray/domain)
export NS=$(cat /etc/xray/dns)
export PUB=$(cat /etc/slowdns/server.pub)
clear
figlet "Setup Bot" | lolcat
echo -e "\033[1;36m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m"
read -e -p "Masukkan Bot Token Anda : " bottoken
read -e -p "Masukkan ID Telegram Admin Anda : " admin

# Membuat direktori dan file konfigurasi bot
sudo mkdir -p /etc/bot
echo -e "#bot# $bottoken $admin" | sudo tee /etc/bot/.bot.db
# Menulis konfigurasi ke file var.txt di dalam folder aplikasi
echo -e BOT_TOKEN='"'$bottoken'"' | sudo tee /usr/bin/kyt/var.txt
echo -e ADMIN='"'$admin'"' | sudo tee -a /usr/bin/kyt/var.txt
echo -e DOMAIN='"'$domain'"' | sudo tee -a /usr/bin/kyt/var.txt
echo -e PUB='"'$PUB'"' | sudo tee -a /usr/bin/kyt/var.txt
echo -e HOST='"'$NS'"' | sudo tee -a /usr/bin/kyt/var.txt

# --- 6. MEMBUAT & MENJALANKAN SERVICE ---
echo "Membuat dan menjalankan servis bot..."
sudo cat > /etc/systemd/system/kyt.service << END
[Unit]
Description=Kyt Telegram Bot
After=network.target

[Service]
WorkingDirectory=/usr/bin
ExecStart=/usr/bin/python3 -m kyt
Restart=always

[Install]
WantedBy=multi-user.target
END

sudo systemctl daemon-reload
sudo systemctl enable kyt.service
sudo systemctl restart kyt.service

# --- 7. FINALISASI ---
# Membersihkan file sisa di /tmp
rm -rf /tmp/kyt /tmp/kyt.zip /tmp/bot /tmp/bot.zip

clear
echo "================================================"
echo "      INSTALASI BOT SELESAI"
echo "================================================"
echo "Token Bot     : $bottoken"
echo "Admin ID      : $admin"
echo ""
echo "Bot Anda sudah berjalan."
echo "Ketik /start pada bot Telegram Anda untuk memulai."
echo "================================================"
