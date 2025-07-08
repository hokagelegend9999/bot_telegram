#!/bin/bash
# Script Installer Bot Panel - Versi Perbaikan Final & Lengkap

# --- 1. PEMBERSIHAN TOTAL INSTALASI LAMA ---
echo "Membersihkan instalasi lama secara menyeluruh..."
sudo systemctl stop kyt.service > /dev/null 2>&1
sudo systemctl disable kyt.service > /dev/null 2>&1
sudo rm -f /etc/systemd/system/kyt.service
sudo rm -rf /usr/bin/kyt
sudo rm -rf /usr/bin/bot
sudo rm -f /usr/bin/bot*

# --- 2. INSTALASI DEPENDENSI SISTEM ---
echo "Menginstall dependensi sistem (python, pip, git)..."
sudo apt-get update > /dev/null 2>&1
sudo apt-get install -y python3 python3-pip git

# --- 3. MENGUNDUH & MENGEkstrak BOT VERSI BARU (V2) ---
echo "Mengunduh bot versi V2 yang stabil..."
cd /tmp
wget -O bot.zip https://raw.githubusercontent.com/hokagelegend9999/bot_telegram/refs/heads/main/Bot/bot.zip
unzip -o bot.zip

# --- 4. MEMINDAHKAN SEMUA FILE KE LOKASI YANG BENAR ---
echo "Menata file bot dan semua skrip bantuan..."
sudo mv bot /usr/bin/
sudo mv /usr/bin/bot/shell/* /usr/bin/
sudo chmod +x /usr/bin/bot*

# --- 5. INSTALASI DEPENDENSI PYTHON ---
echo "Menginstall library Python yang dibutuhkan..."
sudo pip3 install --break-system-packages -r /usr/bin/bot/requirements.txt

# --- 6. KONFIGURASI BOT ---
export domain=$(cat /etc/xray/domain)
export NS=$(cat /etc/xray/dns)
export PUB=$(cat /etc/slowdns/server.pub)
clear
echo "----------------------------------------"
echo "Masukkan Konfigurasi Bot Baru"
echo "----------------------------------------"
read -e -p "Masukkan Bot Token Anda: " bottoken
read -e -p "Masukkan ID Telegram Admin Anda: " admin

sudo rm -f /usr/bin/bot/var.txt
echo -e BOT_TOKEN='"'$bottoken'"' | sudo tee /usr/bin/bot/var.txt
echo -e ADMIN='"'$admin'"' | sudo tee -a /usr/bin/bot/var.txt
echo -e DOMAIN='"'$domain'"' | sudo tee -a /usr/bin/bot/var.txt
echo -e PUB='"'$PUB'"' | sudo tee -a /usr/bin/bot/var.txt
echo -e HOST='"'$NS'"' | sudo tee -a /usr/bin/bot/var.txt

# --- 7. MEMBUAT & MENJALANKAN SERVICE BARU ---
echo "Membuat dan menjalankan servis bot V2..."
sudo cat > /etc/systemd/system/kyt.service << END
[Unit]
Description=Kyt Bot V2
After=network.target

[Service]
WorkingDirectory=/usr/bin/bot
ExecStart=/usr/bin/python3 -m bot
Restart=always

[Install]
WantedBy=multi-user.target
END

sudo systemctl daemon-reload
sudo systemctl enable kyt.service
sudo systemctl start kyt.service

# --- 8. FINALISASI ---
rm -f /tmp/bot.zip
rm -rf /tmp/bot
clear
echo "================================================"
echo "      INSTALASI ULANG BERHASIL"
echo "================================================"
echo "Bot versi V2 Anda sudah berjalan."
echo "Silakan cek status dengan: sudo systemctl status kyt.service"
echo "dan coba bot di Telegram."
echo "================================================"
