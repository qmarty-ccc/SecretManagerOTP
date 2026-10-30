#-*- coding=utf-8 -*-
#  ____                     _   __  __
# / ___|  ___  ___ _ __ ___| |_|  \/  | __ _ _ __   __ _  __ _  ___ _ __
# \___ \ / _ \/ __| '__/ _ \ __| |\/| |/ _` | '_ \ / _` |/ _` |/ _ \ '__|
#  ___) |  __/ (__| | |  __/ |_| |  | | (_| | | | | (_| | (_| |  __/ |
# |____/ \___|\___|_|  \___|\__|_|  |_|\__,_|_| |_|\__,_|\__, |\___|_|
#                                                       |___/
#
# Secret Manager with OTP feature
# 
# by qmarty@inbox.ru


SCOPE: 
------------

this script will manage secrets for applications, sites, whatever.  Will also provide OTPs (google compatible)

DESCRIPTION:
------------

The program can be used as manager and as a module to retrieve secrets.
The secrets are stored in sqlite3 secrets.db and the master key to be added as user environment variable (as MASTER_KEY) will be saved in .secret_key in a local user accessible path.

CLI USAGE:
------------
The secret record is composed by:
[Key] 		key name, or url
[Secret] 	the secret to hide and store, it can be generated randomly with the lateral button and
		at the same time is copied to clipboard
[Environment] 	the "contest" i.e. can be web, school, etc. if OTP this will be interpreted as OTP see 			below about that.
[Descriptio]	I set usernames here, or whatever if the secret is about a server, rather than a 			connection to something

The prompt is interactive and self explaining:

C:\Tools>python secret_manager.py

============================================================
🔐 SECURE SECRET MANAGER
============================================================

💡 Tip: You can paste values with Ctrl+V
   The value will be visible while typing
============================================================
✅ Using MASTER_KEY from environment

📌 Menu:
1. Add new secret
2. Update secret
3. View secret
4. List all secrets
5. Delete secret
6. Exit

Select option (1-6):
-------------------------------------------------------
In example to add a new secret :

Select option (1-6): 1
Secret key: GIT_ADVISORIES

📝 Enter secret value (you can paste with Ctrl+V):
Secret value: ghp_LX....BVeamsS1uMUZ7
✓ Received 40 characters
Description (optional):
Environment (default: default):
✅ Secret 'GIT_ADVISORIES' added successfully
   Stored 40 characters

-------------------------------------------------------

Then to retrieve the secret from a script, this is the code:

from secret_manager import SecretManager
manager = SecretManager()
token = manager.get_secret('GIT_ADVISORIES')

-------------------------------------------------------

the GUI interface just helps to manage the application easier.
[+] It autoinstalls secret_manager.py to site-packages if necessary, 
[+] it stores the secrets.db in personal folder:
	WIN - C:\Users\<YourUsername>\AppData\Local\SecretManager\
	GNU - ~/.local/share/SecretManager/
	MAC - ~/Library/Application Support/SecretManager/
[+] it auto set the MASTER_KEY as user environment variable
[+] given a saved QR code picture (jpeg) it can provide OTP for that application

if it finds secrests.db in same folder at first run it exports and use that one, otherwise
it will create a new one.

pyinstaller instructions for  secret_manager (windows):
-----------------
pyinstaller secrets_manager_gui.py ^
    --onefile ^
    --windowed ^
    --name SecretManager ^
    --distpath c:\novirus\ ^
    --icon vault.ico ^
    --add-data "vault.ico;." ^
    --collect-binaries cryptography ^
    --collect-data cryptography ^
    --collect-submodules cryptography ^
    --exclude-module cv2 ^
    --hidden-import PIL


pyinstaller instructions for  secret_manager (GNU/linux):
-----------------
pyinstaller secrets_manager_gui.py \
    --onefile \
    --windowed \
    --name SecretManager \
    --distpath ./novirus/ \
    --icon vault.ico \
    --add-data "vault.ico:." \
    --collect-binaries cryptography \
    --collect-data cryptography \
    --collect-submodules cryptography \
    --collect-all pyzbar \
    --hidden-import PIL

TRICKS AND TIPS
-------------------------------------------------------

This tool does not connect to network nor internet, if it does tell me because I didn't code 
that and it shall not.

In the "All secrets" tab you'll see green highlighted rows : those are the ones with OTP as Environment and they differ because while normally the double-click on the row will copy to clipboard the secret in this case the value copied will be the OTP, also shown in a info pop-up.

OTP
----------------

To associate an OTP whenever you see the QR code onscreen, save the QR code picture as .jps. 
Then in "New" secret pick it up with the side button (on the right of the Environment input field where OTP shall be written). Give it a name and then save and you are done.
