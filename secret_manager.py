#!/usr/bin/env python3
#  _           _      _ 
# (_)         (_)    | |
#  _ _ __  ___ _  ___| |
# | | '_ \/ __| |/ _ \ |
# | | | | \__ \ |  __/ |
# |_|_| |_|___/_|\___|_|
#
# programma per la gestione delle credenziali 
# 
# by lino.molaro@insiel.it
#
#
# secret_manager.py - Updated with input() for better paste support
import os
import sys
import site
import sqlite3
import shutil
from pathlib import Path
from contextlib import contextmanager

from cryptography.fernet import Fernet

from paths import db_path as default_db_path, key_path as default_key_path, legacy_candidates


class SecretManager:
    # ---------- construction ----------

    def __init__(self, db_path=None, key_file=None, use_keyring=True):
        self.db_path   = Path(db_path)   if db_path   else default_db_path()
        self._key_file = Path(key_file)  if key_file  else default_key_path()
        self._use_keyring = use_keyring
        
        # migrate any old files *before* touching crypto
        self._migrate_legacy(legacy_candidates())
        self.master_key = self._get_master_key()
        self.cipher     = Fernet(self.master_key)
        self._init_database()

    # ---------- legacy migration ----------

    def _migrate_legacy(self, legacy_dirs):
        """
        Copy secrets.db / .master_key from any legacy dir into the new per-user
        location, only if the destination does not already exist.
        Safe on every startup.
        """
        target_dir = self.db_path.parent.resolve()

        for legacy_dir in legacy_dirs:
            legacy_dir = Path(legacy_dir)
            try:
                if not legacy_dir.exists():
                    continue
                if legacy_dir.resolve() == target_dir:
                    continue
            except OSError:
                continue

            legacy_db  = legacy_dir / "secrets.db"
            legacy_key = legacy_dir / ".master_key"

            # key FIRST: _get_master_key() must see the migrated key
            if legacy_key.exists() and not self._key_file.exists():
                self._key_file.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(legacy_key, self._key_file)
                print(f"🔁 Migrated key   {legacy_key} -> {self._key_file}")

            if legacy_db.exists() and not self.db_path.exists():
                self.db_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(legacy_db, self.db_path)
                print(f"🔁 Migrated db    {legacy_db} -> {self.db_path}")

    # ---------- key handling ----------

    def _get_master_key(self):
        env_key = os.environ.get("MASTER_KEY")
        if env_key:
            return env_key.encode()
            
        if self._use_keyring:    
            try:
                import keyring
                stored_key = keyring.get_password("SecretManager", "master_key")
                if stored_key:
                    return stored_key.encode()
            except ImportError:
                pass
            
        key_file = self._key_file
        if key_file.exists():
            with open(key_file, "rb") as f:
                print(f"✅ Using MASTER_KEY from {key_file}")
                return f.read()

        print("\n🔑 First time setup - Creating master key...")
        new_key = Fernet.generate_key()

        key_file.parent.mkdir(parents=True, exist_ok=True)
        with open(key_file, "wb") as f:
            f.write(new_key)

        try:
            os.chmod(key_file, 0o400)
        except OSError:
            pass  # Windows

        print(f"✅ Master key created and saved to {key_file}")
        print("⚠️  BACKUP THIS FILE! If lost, you cannot decrypt your secrets.")
        
        if self._use_keyring:
            try:
                import keyring
                keyring.set_password("SecretManager", "master_key", new_key.decode())
            except ImportError:
                pass   
        return new_key
        
    
# ---------- db ----------

    def _init_database(self):
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS secrets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key_name TEXT UNIQUE NOT NULL,
                    encrypted_value TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    description TEXT,
                    environment TEXT DEFAULT 'default'
                )
            """)
            conn.commit()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def add_secret(self, key_name, value, description=None, environment='default'):
        """Add a new secret - automatically strips whitespace"""
        # Strip whitespace from the value
        value = value.strip()
        
        if not value:
            print("❌ Value cannot be empty after stripping")
            return False
        
        encrypted_value = self.cipher.encrypt(value.encode('utf-8')).decode('utf-8')
        
        with self._get_connection() as conn:
            try:
                conn.execute('''
                    INSERT INTO secrets (key_name, encrypted_value, description, environment)
                    VALUES (?, ?, ?, ?)
                ''', (key_name, encrypted_value, description, environment))
                conn.commit()
                print(f"✅ Secret '{key_name}' added successfully")
                print(f"   Stored {len(value)} characters")
                return True
            except sqlite3.IntegrityError:
                print(f"❌ Secret '{key_name}' already exists")
                return False

    def update_secret(self, key_name, value, description=None):
        """Update an existing secret - automatically strips whitespace"""
        # Strip whitespace from the value
        value = value.strip()
        
        if not value:
            print("❌ Value cannot be empty after stripping")
            return False
        
        encrypted_value = self.cipher.encrypt(value.encode('utf-8')).decode('utf-8')
        
        with self._get_connection() as conn:
            if description:
                conn.execute('''
                    UPDATE secrets 
                    SET encrypted_value = ?, description = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE key_name = ?
                ''', (encrypted_value, description, key_name))
            else:
                conn.execute('''
                    UPDATE secrets 
                    SET encrypted_value = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE key_name = ?
                ''', (encrypted_value, key_name))
            
            if conn.total_changes == 0:
                print(f"❌ Secret '{key_name}' not found")
                return False
            
            conn.commit()
            print(f"✅ Secret '{key_name}' updated successfully")
            return True
    
    def get_secret(self, key_name, environment=None):
        """Retrieve a secret from the database"""
        with self._get_connection() as conn:
            if environment is not None:
                result = conn.execute('''
                    SELECT encrypted_value FROM secrets 
                    WHERE key_name = ? AND environment = ?
                ''', (key_name, environment)).fetchone()
                if result:
                    try:
                        decrypted = self.cipher.decrypt(result['encrypted_value'].encode('utf-8'))
                        return decrypted.decode('utf-8')
                    except Exception as e:
                        print(f"⚠️ Decryption error: {e}")
                        return None
            
            result = conn.execute('''
                SELECT encrypted_value FROM secrets 
                WHERE key_name = ?
            ''', (key_name,)).fetchone()
            
            if result:
                try:
                    decrypted = self.cipher.decrypt(result['encrypted_value'].encode('utf-8'))
                    return decrypted.decode('utf-8')
                except Exception as e:
                    print(f"⚠️ Decryption error: {e}")
                    return None
            
            result = conn.execute('''
                SELECT key_name, environment FROM secrets 
                WHERE key_name = ?
            ''', (key_name,)).fetchone()
            
            if result:
                print(f"⚠️ Secret '{key_name}' exists in environment '{result['environment']}'")
            else:
                print(f"❌ Secret '{key_name}' not found")
            
            return None
    
    def list_secrets(self):
        """List all secrets"""
        with self._get_connection() as conn:
            results = conn.execute('''
                SELECT key_name, description, environment, created_at, updated_at
                FROM secrets 
                ORDER BY key_name
            ''').fetchall()
            
            if not results:
                print("\n📭 No secrets found")
                return
            
            print("\n📋 Stored Secrets:")
            print("=" * 80)
            for row in results:
                print(f"  • {row['key_name']} (env: {row['environment']})")
                if row['description']:
                    print(f"    Description: {row['description']}")
                print(f"    Updated: {row['updated_at']}")
                print()
    
    def delete_secret(self, key_name):
        """Delete a secret"""
        with self._get_connection() as conn:
            conn.execute('DELETE FROM secrets WHERE key_name = ?', (key_name,))
            conn.commit()
            if conn.total_changes > 0:
                print(f"✅ Secret '{key_name}' deleted")
                return True
            print(f"❌ Secret '{key_name}' not found")
            return False
def gui_input(prompt=""):
    if prompt:
        print(prompt, end="", flush=True)
        sys.stdout.flush()
    return input()
        
def main():
     
    """Interactive menu"""
    print("\n" + "=" * 60)
    print("🔐 SECURE SECRET MANAGER")
    print("=" * 60)
    print("\n💡 Tip: You can paste values with Ctrl+V")
    print("   The value will be visible while typing")
    print("=" * 60)
    
    manager = SecretManager()
    
    while True:
        print("\n📌 Menu:")
        print("1. Add new secret")
        print("2. Update secret")
        print("3. View secret")
        print("4. List all secrets")
        print("5. Delete secret")
        print("6. Exit")
        
        choice = gui_input("\nSelect option (1-6): ").strip()
        
        if choice == '1':
            key = gui_input("Secret key: ").strip()
            if not key:
                print("❌ Key cannot be empty")
                continue
            
            print("\n📝 Enter secret value (you can paste with Ctrl+V):")
            value = gui_input("Secret value: ")
            
            if not value:
                print("❌ Value cannot be empty")
                continue
            
            print(f"✓ Received {len(value)} characters")
            
            desc = gui_input("Description (optional): ").strip()
            env = gui_input("Environment (default: default): ").strip() or 'default'
            
            manager.add_secret(key, value, desc or None, env)
        
        elif choice == '2':
            key = gui_input("Secret key to update: ").strip()
            if not key:
                print("❌ Key cannot be empty")
                continue
            
            print("\n📝 Enter new secret value (you can paste with Ctrl+V):")
            value = gui_input("New value: ")
            
            if not value:
                print("❌ Value cannot be empty")
                continue
            
            print(f"✓ Received {len(value)} characters")
            
            desc = gui_input("New description (optional): ").strip()
            manager.update_secret(key, value, desc or None)
        
        elif choice == '3':
            key = gui_input("Secret key to view: ").strip()
            if not key:
                print("❌ Key cannot be empty")
                continue
            
            value = manager.get_secret(key)
            if value:
                print(f"\n🔑 {key} = {value}")
            else:
                print(f"❌ Secret '{key}' not found")
        
        elif choice == '4':
            manager.list_secrets()
        
        elif choice == '5':
            key = gui_input("Secret key to delete: ").strip()
            if not key:
                print("❌ Key cannot be empty")
                continue
            
            confirm = gui_input(f"Delete '{key}'? (y/n): ").lower()
            if confirm == 'y':
                manager.delete_secret(key)
        
        elif choice == '6':
            print("\n👋 Goodbye!")
            break
        
        else:
            print("❌ Invalid option")

if __name__ == "__main__":
    
    import argparse
    import sqlite3
    import subprocess
    import getpass
    import site
    
    parser = argparse.ArgumentParser(description="Secret Manager CLI")
    parser.add_argument("action", nargs="?", help="get, set, list")
    parser.add_argument("key", nargs="?", help="The secret key")
    parser.add_argument("--env", default=None, help="Environment")
    parser.add_argument("--exec", dest="exec_cmd", nargs=argparse.REMAINDER, help="Run a command with secrets injected")
    parser.add_argument("--portable", nargs='+', metavar=("DB_PATH", "KEY_PATH"), help="Use specific db and key file, bypass keyring")
    args = parser.parse_args()
if __name__ == "__main__":
    # ... (argparse setup) ...

    # RETRO-COMPATIBLE: If no arguments are passed, run the classic menu
    if not args.action and not args.exec_cmd and not args.portable:
        
        # Only do .pth install when running the menu from source
        if not getattr(sys, "frozen", False):
            try:
                import sysconfig
                script_dir = Path(__file__).resolve().parent
                
                # Get USER site-packages (no sudo required)
                if os.name == 'nt':
                    user_site = Path(sysconfig.get_path('purelib', scheme='nt_user'))
                else:
                    user_site = Path(site.getusersitepackages())
                    
                user_site.mkdir(parents=True, exist_ok=True)
                pth_file = user_site / "secret_manager.pth"
                
                # Create or update the .pth file
                if not pth_file.exists() or str(script_dir) not in pth_file.read_text():
                    with open(pth_file, "w") as f:
                        f.write(str(script_dir) + "\n")
                    print(f"✅ Site-packages updated: Created {pth_file}")
            except Exception as e:
                print(f"(skip .pth setup: {e})")
                
        main() 
        sys.exit(0)

    if args.portable:
        # Handle both formats: "--portable db;key" and "--portable db key"
        if len(args.portable) == 1 and os.pathsep in args.portable[0]:
            paths = args.portable[0].split(os.pathsep)
            db_path = paths[0]
            key_file = paths[1] if len(paths) > 1 else None
        elif len(args.portable) >= 2:
            db_path = args.portable[0]
            key_file = args.portable[1]
        else:
            db_path = args.portable[0]
            key_file = None
            
        manager = SecretManager(db_path=db_path, key_file=key_file, use_keyring=False)
    else:
        manager = SecretManager()
    
    if args.exec_cmd:
        # Load ALL secrets into a dictionary
        env = os.environ.copy()
        with sqlite3.connect(manager.db_path) as conn:
            conn.row_factory = sqlite3.Row
            for row in conn.execute("SELECT key_name FROM secrets"):
                key = row['key_name']
                if key.isidentifier(): 
                    val = manager.get_secret(key)
                    if val:
                        env[key] = val
                
        try:
            subprocess.run(args.exec_cmd, env=env, check=True)
        except KeyboardInterrupt:
            sys.exit(130)
        sys.exit(0)


    if args.action == "get":
        if not args.key:
            print("Error: key required", file=sys.stderr)
            sys.exit(1)
        old_stdout = sys.stdout
        sys.stdout = sys.stderr
        try:
            val = manager.get_secret(args.key, environment=args.env)
        finally:
            sys.stdout = old_stdout
            
        if val:
            print(val) # This goes to the REAL stdout
        else:
            sys.exit(1)
        # val = manager.get_secret(args.key, environment=args.env)
        # if val:
            # print(val) # Print raw to stdout for scripts
        # else:
            # sys.exit(1) # Exit code 1 if not found (standard OS behavior)

    elif args.action == "set":
        if not args.key:
            print("Error: key required", file=sys.stderr)
            sys.exit(1)
            
        import getpass
        # Secure prompt (doesn't save to bash history or echo to screen)
        val = getpass.getpass(f"Enter value for {args.key}: ")
        
        old_stdout = sys.stdout
        sys.stdout = sys.stderr
        try:
            manager.add_secret(args.key, val, environment=args.env or 'default')
        finally:
            sys.stdout = old_stdout

    elif args.action == "list":
        manager.list_secrets()
        
    else:
        print(f"Unknown action: {args.action}", file=sys.stderr)
        sys.exit(1)
