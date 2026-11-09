#!/usr/bin/env python3
"""
secret_manager_gui.py - Tkinter GUI for the Secret Manager
by extending secret_manager.py
"""

import os
import sys
import site
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from pathlib import Path

# ---- lazy import of the core manager ----
def _load_secret_manager_class():
    """Works both from source and from a PyInstaller exe."""
    try:
        from secret_manager import SecretManager
        return SecretManager
    except ImportError as e:
        messagebox.showerror(
            "Missing module",
            "secret_manager.py could not be imported.\n"
            "Rebuild the exe with --hidden-import secret_manager,\n"
            f"or make sure secret_manager.py is next to this script.\n\n{e}"
        )
        raise

# ---- master key / environment registration ----------------------------------
def register_master_key_in_user_env():
    """Register MASTER_KEY to user environment if not already there."""
    from paths import key_path
    key_file = key_path()
    
    if not key_file.exists():
        return False

    key_value = key_file.read_text().strip()
    if not key_value:
        return False

    if os.environ.get('MASTER_KEY') == key_value:
        return True

    try:
        if os.name == 'nt':
            subprocess.run(['setx', 'MASTER_KEY', key_value],
                           check=True, capture_output=True, shell=True)
            os.environ['MASTER_KEY'] = key_value
            print("✅ MASTER_KEY registered in user environment (Windows)")
            return True
        else:
            bashrc = Path.home() / '.bashrc'
            line = f'\nexport MASTER_KEY="{key_value}"\n'
            content = bashrc.read_text() if bashrc.exists() else ''
            if 'MASTER_KEY=' not in content:
                with open(bashrc, 'a') as f:
                    f.write(f'\n# secret_manager MASTER_KEY\n{line}')
                print(f"✅ MASTER_KEY appended to {bashrc}")
            os.environ['MASTER_KEY'] = key_value
            return True
    except Exception as e:
        print(f"⚠️  Could not register MASTER_KEY to environment: {e}")
        return False

# ---- main GUI ---------------------------------------------------------------
class SecretManagerGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("🔐 Secret Manager GUI")
        self.root.geometry("1200x640")
        
        # Load Icon
        try:
            if getattr(sys, "frozen", False):
                base_dir = Path(sys._MEIPASS)
            else:
                base_dir = Path(__file__).resolve().parent
                
            png_path = base_dir / "vault.png"
            ico_path = base_dir / "vault.ico"
            
            if png_path.exists():
                self.root.iconphoto(True, tk.PhotoImage(file=str(png_path)))
            elif ico_path.exists():
                self.root.iconbitmap(str(ico_path))
        except Exception as e:
            print(f"Could not load icon: {e}")

        self.manager = None
        SecretManager = _load_secret_manager_class()
        
        # 1. BUILD THE UI FIRST
        self._build_style()
        self._build_ui()

        # 2. THEN INITIALIZE THE MANAGER
        is_portable = "--portable" in sys.argv
        try:
            if is_portable:
                idx = sys.argv.index("--portable")
                if len(sys.argv) > idx + 1:
                    path_arg = sys.argv[idx + 1]
                    # os.pathsep is ';' on Windows, ':' on Linux
                    paths = path_arg.split(os.pathsep) 
                    db_path = paths[0]
                    key_path = paths[1] if len(paths) > 1 else None
                    
                    self.manager = SecretManager(db_path=db_path, key_file=key_path, use_keyring=False)
                    self.root.title("🔐 Secret Manager GUI (Portable Mode)")
                else:
                    sep = ";" if os.name == 'nt' else ":"
                    messagebox.showerror("Error", f"Please provide paths for DB and Key. Example:\n--portable C:\\Temp\\secrets.db{sep}C:\\Temp\\.master_key")
                    self.root.destroy()
                    return
            else:
                self.manager = SecretManager()
                
            register_master_key_in_user_env()
            # 3. NOW IT IS SAFE TO LOAD DATA INTO THE UI
            self.refresh_secret_list()
            self.root.after_idle(self.search_entry.focus_set)
        except Exception as e:
            messagebox.showerror("Init error", f"Cannot initialise SecretManager:\n{e}")
            self.root.destroy()
            return

    def on_close(self):
        self.root.destroy()

    def _build_style(self):
        style = ttk.Style()
        try:
            style.theme_use('clam')
        except tk.TclError:
            pass
        style.configure("TNotebook.Tab", padding=(12, 6))
        style.configure("Copy.TButton", font=("Segoe UI", 10, "bold"))
        style.configure("Treeview", rowheight=30, font=("Segoe UI",10))
        style.configure("Treeview.Heading", font=("Segoe UI",10,"bold"))

    # ---- UI ----
    def _build_ui(self):
        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill='both', expand=True, padx=8, pady=8)

        self.tab_search = ttk.Frame(self.nb)
        self.nb.add(self.tab_search, text="🔎  Secrets")

        # Status bar for temporary messages
        self.status_var = tk.StringVar()
        self.status_label = ttk.Label(self.root, textvariable=self.status_var, foreground="green", font=("Segoe UI", 10, "bold"))
        self.status_label.pack(side='bottom', fill='x', padx=10, pady=5)
        
        self._build_search_tab()

    def _build_search_tab(self):
        f = self.tab_search

        top = ttk.Frame(f)
        top.pack(fill='x', padx=10, pady=(10, 4))

        ttk.Label(top, text="Search (case-insensitive):").pack(side='left')
        self.search_var = tk.StringVar()
        self.search_var.trace_add('write', lambda *_: self._filter_secrets())
        self.search_entry = ttk.Entry(top, textvariable=self.search_var)
        self.search_entry.pack(side='left', fill='x', expand=True, padx=8)
    
        ttk.Button(top, text="Clear", command=lambda: self.search_var.set('')).pack(side='left')

        mid = ttk.Frame(f)
        mid.pack(fill='both', expand=True, padx=10, pady=4)

        self.result_text = scrolledtext.ScrolledText(
            mid, height=14, wrap='none', font=("Consolas", 10)
        )

        self.result_text = scrolledtext.ScrolledText(
            mid, height=14, wrap='none', font=("Consolas", 10)
        )
        self.result_text.pack(fill='both', expand=True)
        self.result_text.bind("<Button-1>", self._on_result_click)
        self.result_text.bind("<Double-Button-1>", self._on_result_double_click)
        self.result_text.config(cursor="hand2")
        
        # --- ADD THESE TAGS FOR THE HEADER ---
        self.result_text.tag_configure("header", font=("Consolas", 10, "bold"), background="#e0e0e0")
        self.result_text.tag_configure("otp", foreground="green")
        self.result_text.tag_configure("sel", background="#cce5ff")
        
        # selected key display
        sel_frame = ttk.Frame(f)
        sel_frame.pack(fill='x', padx=10, pady=(4, 10))

        ttk.Label(sel_frame, text="Selected key:").pack(side='left')
        self.selected_key_var = tk.StringVar(value="<none>")
        ttk.Label(sel_frame, textvariable=self.selected_key_var,
                  font=("Consolas", 10, "bold"),
                  foreground="#0066cc").pack(side='left', padx=8)

        # --- BUTTONS ON THE RIGHT ---
        ttk.Button(sel_frame, text="✏️ Edit", command=self._edit_selected).pack(side='right', padx=4)
        ttk.Button(sel_frame, text="🗑️ Erase", command=self._erase_selected).pack(side='right', padx=4)
        ttk.Button(sel_frame, text="➕ New", command=self._new_secret).pack(side='right', padx=4)
        
        self.copy_btn = ttk.Button(sel_frame, text="📋 Copy to clipboard",
                                   style="Copy.TButton",
                                   command=self._copy_selected,
                                   state='disabled')
        self.copy_btn.pack(side='right', padx=10)

        self._filtered_keys = []
        
    def _on_result_click(self, event):
        idx = self.result_text.index(f"@{event.x},{event.y}")
        line_no = int(idx.split('.')[0])
        
        # Header is now only 1 line
        if line_no == 1:
            return
            
        lines = [l for l in self.result_text.get("1.0", "end-1c").split('\n') if l.strip()]
        
        # Subtract 1 to skip the header line
        data_idx = line_no - 2 
        
        if 0 <= data_idx < len(lines) - 1:
            raw = lines[data_idx + 1].strip() 
            key = raw.partition(" (")[0].strip() 
            self._select_key(key)
            
    def _on_result_double_click(self, event):
        # First, let the single-click handler select the key
        self._on_result_click(event)
        # Then trigger the copy action
        self._copy_selected()

    def _select_key(self, key):
        self.selected_key_var.set(key)
        self.copy_btn.config(state='normal')
        
        self.result_text.tag_remove("sel", "1.0", "end")
        content = self.result_text.get("1.0", "end-1c").split('\n')
        for i, line in enumerate(content, start=1):
            if line.strip().startswith(key):
                self.result_text.tag_add("sel", f"{i}.0", f"{i}.end")
                break
        self.result_text.tag_config("sel", background="#cce5ff")

    def _filter_secrets(self):
        if not self.manager:
            return
        q = self.search_var.get().lower().strip()

        import sqlite3
        with sqlite3.connect(self.manager.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT key_name, environment, description, updated_at FROM secrets ORDER BY key_name"
            ).fetchall()

        keys = [(r['key_name'], r['environment'], r['description'] or '', r['updated_at'] or '') for r in rows]
        
        if q:
            keys = [k for k in keys if q in k[0].lower() or q in k[2].lower()]

        self._filtered_keys = [k[0] for k in keys]

        self.result_text.config(state='normal')
        self.result_text.delete("1.0", "end")
        
        if not keys:
            self.result_text.insert("1.0", "(no matches)")
        else:
            # Calculate max lengths for padding based on actual data
            max_key_len = max(len(k[0]) for k in keys) + 2
            max_env_len = max(len(k[1]) for k in keys) + 4
            max_desc_len = max(len(k[2]) for k in keys) + 2
            
            # Create the header string using the EXACT same padding logic
            header_key = "Key".ljust(max_key_len)
            header_env = "Env".ljust(max_env_len)
            header_desc = "Description".ljust(max_desc_len)
            header_upd = "Updated"
            
            header = f" {header_key} {header_env} {header_desc} {header_upd}\n"
            
            # Insert header (1 line)
            self.result_text.insert("end", header, ("header", "no_select"))
            
            for k, e, d, u in keys:
                # Data rows use the EXACT same padding logic as the header
                line = f" {k.ljust(max_key_len)} {('(' + e + ')').ljust(max_env_len)} {d.ljust(max_desc_len)} {u}\n"
                
                if e == 'OTP':
                    self.result_text.insert("end", line, ('otp',))
                else:
                    self.result_text.insert("end", line)

        self.result_text.config(state='disabled')

        if self.selected_key_var.get() not in self._filtered_keys:
            self.selected_key_var.set("<none>")
            self.copy_btn.config(state='disabled')

    def _copy_selected(self):
        key = self.selected_key_var.get()
        if not key or key == "<none>":
            return
        if not self.manager:
            return
            
        # Fetch environment to check if it's an OTP
        import sqlite3
        with sqlite3.connect(self.manager.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT environment FROM secrets WHERE key_name = ?", (key,)).fetchone()
            env = row['environment'] if row else 'default'

        val = self.manager.get_secret(key)
        if val is None:
            messagebox.showwarning("Not found", f"Secret '{key}' could not be read")
            return

        if env == 'OTP':
            secret = val
            if val.startswith("otpauth://"):
                import urllib.parse
                parsed = urllib.parse.urlparse(val)
                params = urllib.parse.parse_qs(parsed.query)
                secret = params.get('secret', [None])[0]

            if not secret:
                # messagebox.showerror("OTP Error", f"No secret found in URI for '{key}'")
                messagebox.showerror("OTP Error", f"Failed to generate OTP for '{key}':\n{repr(e)}\n\nCheck if cryptography is loaded.")
                return

            try:
                from larztotp import totp
                otp_code = totp(secret)
            except Exception as e:
                messagebox.showerror("OTP Error", f"Failed to generate OTP for '{key}':\n{e}")
                return

            self.root.clipboard_clear()
            self.root.clipboard_append(otp_code)
            self.root.update()
            
            # Keep the messagebox for OTP so the user has time to read the code
            messagebox.showinfo("OTP Copied", f"OTP for '{key}':\n\n{otp_code}\n\n(Copied to clipboard)")
            return

        # For normal secrets, copy and show temporary status
        self.root.clipboard_clear()
        self.root.clipboard_append(val)
        self.root.update()
        
        self._show_temporary_status(f"✅ Secret '{key}' copied to clipboard ({len(val)} chars)")

    def _show_temporary_status(self, message, duration=3000):
        """Shows a message in the status bar and clears it after `duration` ms."""
        self.status_var.set(message)
        # Cancel any previous timer so they don't overlap
        if hasattr(self, '_status_timer') and self._status_timer:
            self.root.after_cancel(self._status_timer)
        # Start a new timer
        self._status_timer = self.root.after(duration, lambda: self.status_var.set(""))
 
    def refresh_secret_list(self):
        self._filter_secrets()

    def _new_secret(self):
        SecretDialog(self.root, self.manager, on_save=self.refresh_secret_list)

    def _edit_selected(self):
        key = self.selected_key_var.get()
        if key == "<none>" or not key:
            messagebox.showinfo("No selection", "Please select a secret to edit.")
            return
        SecretDialog(self.root, self.manager, key_name=key, on_save=self.refresh_secret_list)

    def _erase_selected(self):
        key = self.selected_key_var.get()
        if key == "<none>" or not key:
            messagebox.showinfo("No selection", "Please select a secret to erase.")
            return
        
        confirm = messagebox.askyesno("Confirm Delete", f"Are you sure you want to permanently erase '{key}'?")
        if confirm:
            self.manager.delete_secret(key)
            self.selected_key_var.set("<none>")
            self.copy_btn.config(state='disabled')
            self.refresh_secret_list()

class SecretDialog(tk.Toplevel):
    def __init__(self, parent, manager, key_name=None, on_save=None):
        super().__init__(parent)
        self.manager = manager
        self.key_name = key_name
        self.on_save = on_save
        self.is_edit = key_name is not None

        self.title("Edit Secret" if self.is_edit else "New Secret")
        self.geometry("520x350")
        self.resizable(False, False)
        
        self.transient(parent)
        self.grab_set()

        pad = 10
        
        # Row 0: Key Name
        ttk.Label(self, text="Key Name:").grid(row=0, column=0, sticky='e', padx=pad, pady=pad)
        self.key_var = tk.StringVar(value=self.key_name if self.is_edit else "")
        self.key_entry = ttk.Entry(self, textvariable=self.key_var)
        self.key_entry.grid(row=0, column=1, sticky='ew', padx=pad, pady=pad)
        if self.is_edit:
            self.key_entry.config(state='disabled')

        # Row 1: Secret Value
        ttk.Label(self, text="Secret Value:").grid(row=1, column=0, sticky='e', padx=pad, pady=pad)
        val_frame = ttk.Frame(self)
        val_frame.grid(row=1, column=1, sticky='ew', padx=pad, pady=pad)
        
        self.val_entry = ttk.Entry(val_frame)
        self.val_entry.grid(row=0, column=0, sticky='ew')
        
        ttk.Button(val_frame, text="🎲 Generate", command=self._generate_password).grid(row=0, column=1, padx=(6, 0), sticky='e')
        val_frame.columnconfigure(0, weight=1)
        val_frame.columnconfigure(1, weight=0)

        # Row 2: Environment (with Image Scan button)
        ttk.Label(self, text="Environment:").grid(row=2, column=0, sticky='e', padx=pad, pady=pad)
        env_frame = ttk.Frame(self)
        env_frame.grid(row=2, column=1, sticky='ew', padx=pad, pady=pad)
        
        self.env_var = tk.StringVar(value="default")
        self.env_entry = ttk.Entry(env_frame, textvariable=self.env_var)
        self.env_entry.grid(row=0, column=0, sticky='ew')
        
        # Changed to "Load Image"
        self.scan_btn = ttk.Button(env_frame, text="🖼️ Load Image", command=self._scan_qr)
        self.scan_btn.grid(row=0, column=1, padx=(6, 0), sticky='e')
        
        env_frame.columnconfigure(0, weight=1)
        env_frame.columnconfigure(1, weight=0)

        # Row 3: Description (Restored)
        ttk.Label(self, text="Description:").grid(row=3, column=0, sticky='e', padx=pad, pady=pad)
        self.desc_entry = ttk.Entry(self)
        self.desc_entry.grid(row=3, column=1, sticky='ew', padx=pad, pady=pad)

        # Row 4: Buttons
        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=4, column=0, columnspan=2, pady=20)
        ttk.Button(btn_frame, text="Save", command=self._save).pack(side='left', padx=10)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side='left', padx=10)

        self.columnconfigure(1, weight=1)

        if self.is_edit:
            self._prefill()
        else:
            self.key_entry.focus_set()
            
    def _scan_qr(self):
        from tkinter import filedialog
        from PIL import Image
        from pyzbar.pyzbar import decode
        
        # Ask the user to select the image file
        file_path = filedialog.askopenfilename(
            parent=self,
            title="Select QR Code Image",
            filetypes=[("Image Files", "*.png *.jpg *.jpeg *.bmp")]
        )
        if not file_path:
            return
            
        try:
            # Read the image and decode it
            img = Image.open(file_path)
            decoded = decode(img)
            
            if decoded:
                qr_data = decoded[0].data.decode('utf-8')
                
                # If it's an otpauth URI, automatically set the environment to 'OTP'
                if qr_data.startswith("otpauth://"):
                    self.env_var.set("OTP")
                    
                self.val_entry.delete(0, 'end')
                self.val_entry.insert(0, qr_data)
                messagebox.showinfo("QR Scanned", "QR code successfully scanned and inserted!", parent=self)
            else:
                messagebox.showwarning("Scan Failed", "No QR code found in the selected image.", parent=self)
                
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read image:\n{e}", parent=self)

    def _qr_success(self, data):
        # If it's an otpauth URI, automatically set the environment to 'OTP'
        if data.startswith("otpauth://"):
            self.env_var.set("OTP")
            
        # Put the scanned string into the Secret Value box
        self.val_entry.delete(0, 'end')
        self.val_entry.insert(0, data)
        
        messagebox.showinfo("QR Scanned", "QR code successfully scanned and inserted!", parent=self)
        
    def _prefill(self):
        import sqlite3
        with sqlite3.connect(self.manager.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT environment, description FROM secrets WHERE key_name = ?", (self.key_name,)).fetchone()
            if row:
                self.env_var.set(row['environment'])
                self.desc_entry.insert(0, row['description'] or "")
        
        current_val = self.manager.get_secret(self.key_name)
        if current_val:
            self.val_entry.insert(0, current_val)
            
        self.val_entry.focus_set()
    def _generate_password(self):
        import secrets
        import string
        
        # Define the character pool
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*_-+="
        
        # Generate a secure 16-character password
        password = ''.join(secrets.choice(alphabet) for _ in range(16))
        
        # Update the entry box
        self.val_entry.delete(0, 'end')
        self.val_entry.insert(0, password)
        
        # Copy to clipboard
        self.clipboard_clear()
        self.clipboard_append(password)
        self.update() # Ensure clipboard persists
        
        # Optional: show a quick visual confirmation
        messagebox.showinfo("Password Generated", "A secure password has been generated and copied to your clipboard.", parent=self)
    def _save(self):
        key = self.key_var.get().strip()
        val = self.val_entry.get().strip()
        env = self.env_var.get().strip() or 'default'
        desc = self.desc_entry.get().strip() or None

        if not key or not val:
            messagebox.showerror("Error", "Key and Value cannot be empty.", parent=self)
            return

        success = False
        if self.is_edit:
            success = self.manager.update_secret(key, val, desc)
            if success and env != 'default': 
                import sqlite3
                with sqlite3.connect(self.manager.db_path) as conn:
                    conn.execute("UPDATE secrets SET environment = ? WHERE key_name = ?", (env, key))
                    conn.commit()
        else:
            success = self.manager.add_secret(key, val, desc, env)

        if success:
            if self.on_save:
                self.on_save()
            self.destroy()

# ---- entry point ------------------------------------------------------------
# ---- entry point ------------------------------------------------------------
def main():
    # replicate the .pth registration from the CLI script
    if not getattr(sys, "frozen", False):
        # Only run if executing as a .py file, NOT the .exe
        try:
            import sysconfig
            script_dir = Path(__file__).resolve().parent
            
            # Get user-level site-packages (no admin rights needed)
            if os.name == 'nt':
                user_site = Path(sysconfig.get_path('purelib', scheme='nt_user'))
            else:
                user_site = Path(site.getusersitepackages())
                
            user_site.mkdir(parents=True, exist_ok=True)
            pth_file = user_site / "secret_manager.pth"
            
            # If the .pth doesn't exist or points to a different folder, update it
            if not pth_file.exists() or str(script_dir) not in pth_file.read_text():
                with open(pth_file, "w") as f:
                    f.write(str(script_dir) + "\n")
                print(f"✅ Auto-configured Python path: Created {pth_file}")
        except Exception as e:
            print(f"(skip .pth setup: {e})")

    root = tk.Tk()
    try:
        app = SecretManagerGUI(root)
    except Exception as e:
        messagebox.showerror("Init error", f"Cannot initialise SecretManager:\n{e}")
        root.destroy()
        return
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()