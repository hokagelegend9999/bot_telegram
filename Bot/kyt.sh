#!/bin/bash
# --- Skrip Installer Final (Menggabungkan kyt.zip dan bot.zip) ---

# 1. Pembersihan total instalasi lama
echo "--- Membersihkan semua versi bot lama ---"
sudo systemctl stop kyt.service > /dev/null 2>&1
sudo systemctl disable kyt.service > /dev/null 2>&1
sudo rm -f /etc/systemd/system/kyt.service
sudo rm -rf /usr/bin/kyt /usr/bin/bot
sudo rm -f /usr/bin/bot*

# 2. Instalasi dependensi sistem
echo "--- Menginstall dependensi sistem ---"
sudo apt-get update > /dev/null 2>&1
sudo apt-get install -y python3 python3-pip git unzip

# 3. Mengunduh KEDUA file ZIP
echo "--- Mengunduh kedua komponen bot ---"
cd /tmp
rm -rf kyt kyt.zip bot bot.zip
# Mengunduh Aplikasi Utama
wget -q -O kyt.zip https://github.com/hokagelegend9999/bot_telegram/raw/main/Bot/kyt.zip
# Mengunduh Skrip Bantuan
wget -q -O bot.zip https://github.com/hokagelegend9999/bot_telegram/raw/main/Bot/bot.zip

# 4. Mengekstrak dan Menata File
echo "--- Mengekstrak dan menata file ---"
# Ekstrak aplikasi utama, akan membuat folder 'kyt'
unzip -o kyt.zip
# Ekstrak skrip bantuan, akan membuat folder 'bot'
unzip -o bot.zip
# Pindahkan folder aplikasi utama ke /usr/bin/
sudo mv kyt /usr/bin/
# Pindahkan SEMUA skrip bantuan ke /usr/bin/
sudo mv bot/* /usr/bin/
# Berikan izin eksekusi
sudo chmod +x /usr/bin/bot*

# 5. Instalasi dependensi Python dari file yang benar
echo "--- Menginstall library Python ---"
sudo pip3 install --break-system-packages -r /usr/bin/kyt/requirements.txt

# 6. Konfigurasi Bot
export domain=$(cat /etc/xray/domain)
export NS=$(cat /etc/xray/dns)
export PUB=$(cat /etc/slowdns/server.pub)
clear
echo "--- Memasukkan Konfigurasi Bot ---"
read -e -p "Masukkan Bot Token Anda: " bottoken
read -e -p "Masukkan ID Telegram Admin Anda: " admin

# Menulis konfigurasi ke file var.txt di dalam folder 'kyt'
sudo rm -f /usr/bin/kyt/var.txt
echo -e BOT_TOKEN='"'$bottoken'"' | sudo tee /usr/bin/kyt/var.txt
echo -e ADMIN='"'$admin'"' | sudo tee -a /usr/bin/kyt/var.txt
echo -e DOMAIN='"'$domain'"' | sudo tee -a /usr/bin/kyt/var.txt
echo -e PUB='"'$PUB'"' | sudo tee -a /usr/bin/kyt/var.txt
echo -e HOST='"'$NS'"' | sudo tee -a /usr/bin/kyt/var.txt

# 7. Membuat & Menjalankan Service dengan konfigurasi yang benar
echo "--- Membuat dan menjalankan servis bot ---"
sudo cat > /etc/systemd/system/kyt.service << END
[Unit]
Description=Kyt Bot
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

# 8. Finalisasi
rm -rf /tmp/kyt /tmp/kyt.zip /tmp/bot /tmp/bot.zip
clear
echo "================================================"
echo "      INSTALASI LENGKAP & BENAR SELESAI"
echo "================================================"
echo "Bot Anda sudah terinstal dengan kedua komponen."
echo "Silakan cek status: sudo systemctl status kyt.service"
echo "dan coba bot di Telegram."
echo "================================================"
