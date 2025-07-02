# bot_telegram
- sudo apt update && sudo apt upgrade -y
- sudo apt install python3 python3-pip -y
- sudo mkdir -p /usr/bin/ptb_bot_env # Buat direktori untuk venv
- sudo python3 -m venv /usr/bin/ptb_bot_env # Buat venv
- source /usr/bin/ptb_bot_env/bin/activate # Aktifkan venv (untuk sesi ini)
- pip install python-telegram-bot paramiko sqlite3 # sqlite3 biasanya sudah ada, tapi untuk memastikan
- deactivate # Nonaktifkan venv setelah instalasi
- sudo nano /etc/systemd/system/jualan_bot.service
- [Unit]
Description=My Simple Echo Telegram Bot
After=network.target

[Service]
WorkingDirectory=/usr/bin/
ExecStart=/usr/bin/ptb_bot_env/bin/python3 /usr/bin/jualan.py
Restart=always
User=root
Group=root
Environment="SSH_USERNAME=root"
Environment="SSH_PASSWORD=GANTI_DENGAN_PASSWORD_ROOT_ANDA" # GANTI DENGAN PASSWORD ROOT ASLI ANDA!
# Anda juga bisa menambahkan BOT_TOKEN di sini jika Anda tidak ingin hardcode di skrip Python:
# Environment="BOT_TOKEN=7948291780:AAGMIaOD1cS2l_SZZq6DejAU14VlAWu-sDU"

[Install]
WantedBy=multi-user.target

- sudo chmod 600 /etc/systemd/system/jualan_bot.service


## INSTALL SCRIPT 

```
rm install
wget https://raw.githubusercontent.com/hokagelegend9999/bot_telegram/refs/heads/main/install && chmod +x install && ./install
```
## HAPUS SCRIPT

``rm uninstall
wget https://raw.githubusercontent.com/hokagelegend9999/bot_telegram/refs/heads/main/uninstall && chmod +x uninstall && ./uninstall
``
