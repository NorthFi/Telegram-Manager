import asyncio
import threading
import json
import os
from datetime import datetime
from tkinter import *
from tkinter import ttk, scrolledtext, messagebox, filedialog
from telethon import TelegramClient, events
from dotenv import load_dotenv
import configparser

class TelegramBotGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Telegram Message Manager")
        self.root.geometry("1200x800")
        
        # Load environment variables
        load_dotenv()
        
        # Bot state
        self.client = None
        self.is_running = False
        self.response_mode = "normal"  # normal, away, custom
        self.current_session_name = None
        self.phone_code_hash = None
        self.message_queue = []  # Store messages when away
        self.selected_chat = None
        self.chats = {}  # Store chat information
        self.loop = None
        self.loop_thread = None
        self.bot_username = None  # Store bot's username for tagging
        
        # Configuration
        self.config_file = "telegram_bot_config.ini"
        self.responses_file = "custom_responses.json"
        
        # Load configurations
        self.load_config()
        self.load_responses()
        
        # Setup GUI
        self.setup_gui()
        
        # Set default responses if not exists
        if not self.responses:
            self.responses = {
                "away_message": "I'm currently away and will respond to your message when I return. Thank you for your patience! 🏖️",
                "custom_responses": {},
                "group_settings": {
                    "respond_when_tagged": True,
                    "respond_to_replies": True,
                    "ignore_bot_commands": True
                }
            }
            self.save_responses()
        
        # Start the asyncio event loop in a separate thread
        self.start_event_loop()
    
    def start_event_loop(self):
        """Start the asyncio event loop in a separate thread"""
        def run_loop():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.run_forever()
        
        self.loop_thread = threading.Thread(target=run_loop, daemon=True)
        self.loop_thread.start()
    
    def run_async(self, coroutine, callback=None):
        """Run an async function in the event loop"""
        if not self.loop:
            return
        
        def done_callback(future):
            if callback:
                try:
                    result = future.result()
                    self.root.after(0, lambda: callback(result))
                except Exception as e:
                    self.root.after(0, lambda: self.log_message(f"Error: {e}"))
        
        future = asyncio.run_coroutine_threadsafe(coroutine, self.loop)
        if callback:
            future.add_done_callback(done_callback)
        
        return future
    
    def setup_gui(self):
        # Create main paned window
        main_paned = PanedWindow(self.root, orient=HORIZONTAL)
        main_paned.pack(fill=BOTH, expand=True, padx=5, pady=5)
        
        # Left panel - Chats and Messages
        left_frame = Frame(main_paned)
        main_paned.add(left_frame, width=400)
        
        # Right panel - Controls
        right_frame = Frame(main_paned)
        main_paned.add(right_frame, width=800)
        
        # Setup left panel (chats)
        self.setup_chat_panel(left_frame)
        
        # Setup right panel (message display and controls)
        self.setup_message_panel(right_frame)
        
        # Status bar
        self.status_bar = ttk.Label(self.root, text="Not connected", relief=SUNKEN, anchor=W)
        self.status_bar.pack(side=BOTTOM, fill=X)
    
    def setup_chat_panel(self, parent):
        # Chat list
        chat_frame = LabelFrame(parent, text="Recent Chats", padx=5, pady=5)
        chat_frame.pack(fill=BOTH, expand=True)
        
        # Chat listbox
        self.chat_listbox = Listbox(chat_frame, height=20)
        self.chat_listbox.pack(side=LEFT, fill=BOTH, expand=True)
        self.chat_listbox.bind('<<ListboxSelect>>', self.on_chat_select)
        
        # Scrollbar
        scrollbar = Scrollbar(chat_frame)
        scrollbar.pack(side=RIGHT, fill=Y)
        self.chat_listbox.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.chat_listbox.yview)
        
        # Chat info
        self.chat_info = Label(chat_frame, text="No chat selected", wraplength=350)
        self.chat_info.pack(side=BOTTOM, fill=X, pady=5)
        
        # Refresh button
        Button(chat_frame, text="Refresh Chats", command=self.load_chats).pack(pady=5)
    
    def setup_message_panel(self, parent):
        # Create notebook for tabs
        self.notebook = ttk.Notebook(parent)
        self.notebook.pack(fill=BOTH, expand=True)
        
        # Tab 1: Messages
        self.messages_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.messages_frame, text="Messages")
        self.setup_messages_tab()
        
        # Tab 2: Auto-Responder
        self.responder_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.responder_frame, text="Auto-Responder")
        self.setup_responder_tab()
        
        # Tab 3: Broadcast
        self.broadcast_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.broadcast_frame, text="Broadcast")
        self.setup_broadcast_tab()
        
        # Tab 4: Connection
        self.connection_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.connection_frame, text="Connection")
        self.setup_connection_tab()
        
        # Tab 5: Group Settings
        self.group_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.group_frame, text="Group Settings")
        self.setup_group_tab()
        
        # Tab 6: Logs
        self.logs_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.logs_frame, text="Logs")
        self.setup_logs_tab()
    
    def setup_messages_tab(self):
        # Message display
        msg_frame = Frame(self.messages_frame)
        msg_frame.pack(fill=BOTH, expand=True, padx=5, pady=5)
        
        self.message_display = scrolledtext.ScrolledText(msg_frame, height=20, width=80, state=DISABLED)
        self.message_display.pack(fill=BOTH, expand=True)
        
        # Configure tags for different message types
        self.message_display.tag_config("received", foreground="blue")
        self.message_display.tag_config("sent", foreground="green")
        self.message_display.tag_config("system", foreground="orange")
        self.message_display.tag_config("group_mention", foreground="purple")
        
        # Message input area
        input_frame = Frame(self.messages_frame)
        input_frame.pack(fill=X, padx=5, pady=5)
        
        Label(input_frame, text="Message:").pack(anchor=W)
        self.message_input = Text(input_frame, height=4, width=80)
        self.message_input.pack(fill=X, pady=5)
        
        # Buttons
        btn_frame = Frame(input_frame)
        btn_frame.pack(fill=X, pady=5)
        
        Button(btn_frame, text="Send Message", command=self.send_message, 
               bg="blue", fg="white", width=15).pack(side=LEFT, padx=5)
        Button(btn_frame, text="Clear", command=lambda: self.message_input.delete(1.0, END), 
               width=10).pack(side=LEFT, padx=5)
        
        # Quick responses
        quick_frame = LabelFrame(self.messages_frame, text="Quick Responses")
        quick_frame.pack(fill=X, padx=5, pady=5)
        
        quick_responses = [
            "Thanks! I'll get back to you soon.",
            "Got it, thanks!",
            "I'm currently away. Will respond later.",
            "Let me check on that.",
            "👍",
            "👋"
        ]
        
        for i, response in enumerate(quick_responses):
            btn = Button(quick_frame, text=response[:20], 
                        command=lambda r=response: self.insert_quick_response(r))
            btn.grid(row=i//3, column=i%3, sticky=EW, padx=2, pady=2)
    
    def setup_group_tab(self):
        """Setup group settings tab"""
        group_frame = LabelFrame(self.group_frame, text="Group Message Handling", padx=10, pady=10)
        group_frame.pack(fill=BOTH, expand=True, padx=10, pady=10)
        
        # Group response settings
        settings_frame = Frame(group_frame)
        settings_frame.pack(fill=X, pady=10)
        
        self.respond_when_tagged = BooleanVar(value=self.responses.get("group_settings", {}).get("respond_when_tagged", True))
        self.respond_to_replies = BooleanVar(value=self.responses.get("group_settings", {}).get("respond_to_replies", True))
        self.ignore_bot_commands = BooleanVar(value=self.responses.get("group_settings", {}).get("ignore_bot_commands", True))
        
        Checkbutton(settings_frame, text="Respond when tagged (@username)", 
                   variable=self.respond_when_tagged,
                   command=self.save_group_settings).pack(anchor=W, pady=5)
        
        Checkbutton(settings_frame, text="Respond to replies to bot's messages", 
                   variable=self.respond_to_replies,
                   command=self.save_group_settings).pack(anchor=W, pady=5)
        
        Checkbutton(settings_frame, text="Ignore messages starting with / (bot commands)", 
                   variable=self.ignore_bot_commands,
                   command=self.save_group_settings).pack(anchor=W, pady=5)
        
        # Group-specific overrides
        Label(group_frame, text="Group-Specific Overrides (Chat ID: Mode)", 
              font=("Arial", 10, "bold")).pack(anchor=W, pady=(20,5))
        
        override_frame = Frame(group_frame)
        override_frame.pack(fill=BOTH, expand=True)
        
        # Overrides list
        self.group_overrides_list = Listbox(override_frame, height=8)
        self.group_overrides_list.pack(side=LEFT, fill=BOTH, expand=True, pady=5)
        
        scrollbar = Scrollbar(override_frame)
        scrollbar.pack(side=RIGHT, fill=Y)
        self.group_overrides_list.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.group_overrides_list.yview)
        
        # Add override controls
        add_frame = Frame(group_frame)
        add_frame.pack(fill=X, pady=10)
        
        Label(add_frame, text="Chat ID:").pack(side=LEFT)
        self.override_chat_id = Entry(add_frame, width=15)
        self.override_chat_id.pack(side=LEFT, padx=5)
        
        Label(add_frame, text="Mode:").pack(side=LEFT)
        self.override_mode = ttk.Combobox(add_frame, values=["default", "always_respond", "never_respond"], width=15)
        self.override_mode.pack(side=LEFT, padx=5)
        self.override_mode.set("default")
        
        Button(add_frame, text="Add/Update", command=self.add_group_override).pack(side=LEFT, padx=5)
        Button(add_frame, text="Delete", command=self.delete_group_override).pack(side=LEFT, padx=5)
        
        # Info text
        info_text = """
        Group Response Logic:
        • In groups, the bot will only respond when:
          1. It is explicitly tagged with @username, OR
          2. The message is a reply to one of the bot's messages (if enabled)
        • This prevents the bot from responding to every message in a group
        • Use group-specific overrides to customize behavior for certain groups
        """
        
        info_label = Label(group_frame, text=info_text, justify=LEFT, fg="gray", wraplength=500)
        info_label.pack(pady=20)
        
        # Load group overrides
        self.load_group_overrides()
    
    def setup_responder_tab(self):
        # Mode selection
        mode_frame = LabelFrame(self.responder_frame, text="Response Mode", padx=10, pady=10)
        mode_frame.pack(fill=X, padx=10, pady=10)
        
        self.mode_var = StringVar(value=self.response_mode)
        
        Radiobutton(mode_frame, text="Normal Mode (Manual responses only)", 
                   variable=self.mode_var, value="normal",
                   command=self.change_mode).pack(anchor=W, pady=2)
        Radiobutton(mode_frame, text="Away Mode (Auto-respond to all messages)", 
                   variable=self.mode_var, value="away",
                   command=self.change_mode).pack(anchor=W, pady=2)
        Radiobutton(mode_frame, text="Custom Mode (Selective auto-responses)", 
                   variable=self.mode_var, value="custom",
                   command=self.change_mode).pack(anchor=W, pady=2)
        
        # Status indicator
        self.mode_status = Label(mode_frame, text="", font=("Arial", 10, "bold"))
        self.mode_status.pack(pady=5)
        
        # Away message
        away_frame = LabelFrame(self.responder_frame, text="Away Message", padx=10, pady=10)
        away_frame.pack(fill=X, padx=10, pady=10)
        
        self.away_message_text = Text(away_frame, height=4, width=60)
        self.away_message_text.pack(fill=X, pady=5)
        self.away_message_text.insert(1.0, self.responses.get("away_message", ""))
        
        Button(away_frame, text="Save Away Message", 
               command=self.save_away_message).pack(pady=5)
        
        # Custom responses
        custom_frame = LabelFrame(self.responder_frame, text="Custom Responses (Keyword-based)", padx=10, pady=10)
        custom_frame.pack(fill=BOTH, expand=True, padx=10, pady=10)
        
        # Custom responses list
        self.custom_responses_list = Listbox(custom_frame, height=6)
        self.custom_responses_list.pack(fill=BOTH, expand=True, pady=5)
        self.custom_responses_list.bind('<<ListboxSelect>>', self.on_custom_response_select)
        
        # Custom response entry
        entry_frame = Frame(custom_frame)
        entry_frame.pack(fill=X, pady=5)
        
        Label(entry_frame, text="Keyword:").pack(side=LEFT)
        self.keyword_entry = Entry(entry_frame, width=20)
        self.keyword_entry.pack(side=LEFT, padx=5)
        
        Label(entry_frame, text="Response:").pack(side=LEFT)
        self.custom_response_entry = Entry(entry_frame, width=40)
        self.custom_response_entry.pack(side=LEFT, padx=5)
        
        Button(entry_frame, text="Add/Update", command=self.add_custom_response).pack(side=LEFT, padx=5)
        Button(entry_frame, text="Delete", command=self.delete_custom_response).pack(side=LEFT, padx=5)
        
        # Load custom responses
        self.load_custom_responses()
        
        # Message queue display
        queue_frame = LabelFrame(self.responder_frame, text="Message Queue (Messages received while away)", padx=10, pady=10)
        queue_frame.pack(fill=BOTH, expand=True, padx=10, pady=10)
        
        self.queue_display = scrolledtext.ScrolledText(queue_frame, height=8, width=70, state=DISABLED)
        self.queue_display.pack(fill=BOTH, expand=True)
        
        Button(queue_frame, text="Clear Queue", command=self.clear_queue).pack(pady=5)
    
    def setup_broadcast_tab(self):
        # Broadcast message
        broadcast_frame = LabelFrame(self.broadcast_frame, text="Broadcast Message", padx=10, pady=10)
        broadcast_frame.pack(fill=BOTH, expand=True, padx=10, pady=10)
        
        Label(broadcast_frame, text="Message to send:").pack(anchor=W)
        self.broadcast_message = Text(broadcast_frame, height=6, width=70)
        self.broadcast_message.pack(fill=X, pady=5)
        
        Label(broadcast_frame, text="Recipients (one per line - username, phone number, or user ID):").pack(anchor=W, pady=(10,0))
        self.recipients_list = Text(broadcast_frame, height=8, width=70)
        self.recipients_list.pack(fill=X, pady=5)
        
        # Buttons
        btn_frame = Frame(broadcast_frame)
        btn_frame.pack(pady=10)
        
        Button(btn_frame, text="Load from File", command=self.load_recipients_file).pack(side=LEFT, padx=5)
        Button(btn_frame, text="Send Broadcast", command=self.send_broadcast, 
               bg="blue", fg="white").pack(side=LEFT, padx=5)
        
        # Progress
        self.broadcast_progress = ttk.Progressbar(broadcast_frame, mode='indeterminate')
        self.broadcast_progress.pack(fill=X, pady=5)
        
        self.broadcast_status = Label(broadcast_frame, text="")
        self.broadcast_status.pack()
    
    def setup_connection_tab(self):
        # API Credentials
        cred_frame = LabelFrame(self.connection_frame, text="API Credentials", padx=10, pady=10)
        cred_frame.pack(fill=X, padx=10, pady=10)
        
        # Load from .env if available
        env_api_id = os.getenv('TELEGRAM_API_ID', '')
        env_api_hash = os.getenv('TELEGRAM_API_HASH', '')
        env_phone = os.getenv('TELEGRAM_PHONE', '')
        
        Label(cred_frame, text="API ID:").grid(row=0, column=0, sticky=W, pady=5)
        self.api_id_entry = Entry(cred_frame, width=40)
        self.api_id_entry.grid(row=0, column=1, pady=5, padx=5)
        self.api_id_entry.insert(0, self.config.get("api_id", env_api_id))
        
        Label(cred_frame, text="API Hash:").grid(row=1, column=0, sticky=W, pady=5)
        self.api_hash_entry = Entry(cred_frame, width=40, show="*")
        self.api_hash_entry.grid(row=1, column=1, pady=5, padx=5)
        self.api_hash_entry.insert(0, self.config.get("api_hash", env_api_hash))
        
        Label(cred_frame, text="Phone Number:").grid(row=2, column=0, sticky=W, pady=5)
        self.phone_entry = Entry(cred_frame, width=40)
        self.phone_entry.grid(row=2, column=1, pady=5, padx=5)
        self.phone_entry.insert(0, self.config.get("phone", env_phone))
        
        # Verification code frame
        self.verification_frame = Frame(cred_frame)
        self.verification_frame.grid(row=3, column=0, columnspan=2, pady=10, sticky=EW)
        
        Label(self.verification_frame, text="Verification Code:").pack(side=LEFT, padx=5)
        self.verification_code = Entry(self.verification_frame, width=20)
        self.verification_code.pack(side=LEFT, padx=5)
        self.verification_code.pack_forget()
        
        self.submit_code_btn = Button(self.verification_frame, text="Submit Code", 
                                       command=self.submit_verification_code, bg="blue", fg="white")
        self.submit_code_btn.pack(side=LEFT, padx=5)
        self.submit_code_btn.pack_forget()
        
        self.resend_code_btn = Button(self.verification_frame, text="Resend Code", 
                                       command=self.resend_verification_code)
        self.resend_code_btn.pack(side=LEFT, padx=5)
        self.resend_code_btn.pack_forget()
        
        # Connection buttons
        btn_frame = Frame(cred_frame)
        btn_frame.grid(row=4, column=0, columnspan=2, pady=10)
        
        self.connect_btn = Button(btn_frame, text="Connect", command=self.connect_bot, 
                                 bg="green", fg="white", width=15)
        self.connect_btn.pack(side=LEFT, padx=5)
        
        self.disconnect_btn = Button(btn_frame, text="Disconnect", command=self.disconnect_bot, 
                                     bg="red", fg="white", state=DISABLED, width=15)
        self.disconnect_btn.pack(side=LEFT, padx=5)
        
        Button(btn_frame, text="Save to .env", command=self.save_to_env, width=12).pack(side=LEFT, padx=5)
        
        # Status display
        status_frame = LabelFrame(self.connection_frame, text="Connection Status", padx=10, pady=10)
        status_frame.pack(fill=BOTH, expand=True, padx=10, pady=10)
        
        self.connection_status = Text(status_frame, height=8, width=70, state=DISABLED)
        self.connection_status.pack(fill=BOTH, expand=True)
    
    def setup_logs_tab(self):
        # Log display
        log_frame = Frame(self.logs_frame)
        log_frame.pack(fill=BOTH, expand=True, padx=10, pady=10)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=20, width=80)
        self.log_text.pack(fill=BOTH, expand=True)
        
        # Buttons
        btn_frame = Frame(self.logs_frame)
        btn_frame.pack(pady=5)
        
        Button(btn_frame, text="Clear Logs", command=self.clear_logs).pack(side=LEFT, padx=5)
        Button(btn_frame, text="Export Logs", command=self.export_logs).pack(side=LEFT, padx=5)
    
    def log_message(self, message, msg_type="system"):
        """Add message to log and message display"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}\n"
        
        # Add to GUI log
        self.log_text.insert(END, log_entry)
        self.log_text.see(END)
        
        # Add to message display if it's a chat message
        if msg_type in ["received", "sent", "group_mention"]:
            self.display_chat_message(message, msg_type)
        
        # Also print to console
        print(log_entry.strip())
    
    def display_chat_message(self, message, msg_type):
        """Display message in the message display area"""
        self.message_display.config(state=NORMAL)
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        if msg_type == "received":
            self.message_display.insert(END, f"[{timestamp}] Received: {message}\n", "received")
        elif msg_type == "sent":
            self.message_display.insert(END, f"[{timestamp}] Sent: {message}\n", "sent")
        elif msg_type == "group_mention":
            self.message_display.insert(END, f"[{timestamp}] Group Mention: {message}\n", "group_mention")
        
        self.message_display.see(END)
        self.message_display.config(state=DISABLED)
    
    def insert_quick_response(self, response):
        """Insert quick response into message input"""
        self.message_input.insert(END, response)
        self.message_input.focus()
    
    def load_custom_responses(self):
        """Load custom responses into listbox"""
        self.custom_responses_list.delete(0, END)
        custom = self.responses.get("custom_responses", {})
        for keyword, response in custom.items():
            self.custom_responses_list.insert(END, f"{keyword}: {response[:50]}...")
    
    def load_group_overrides(self):
        """Load group overrides into listbox"""
        self.group_overrides_list.delete(0, END)
        overrides = self.responses.get("group_settings", {}).get("overrides", {})
        for chat_id, mode in overrides.items():
            self.group_overrides_list.insert(END, f"{chat_id}: {mode}")
    
    def add_group_override(self):
        """Add or update group override"""
        chat_id = self.override_chat_id.get().strip()
        mode = self.override_mode.get()
        
        if not chat_id:
            messagebox.showerror("Error", "Please enter a chat ID!")
            return
        
        if "group_settings" not in self.responses:
            self.responses["group_settings"] = {}
        if "overrides" not in self.responses["group_settings"]:
            self.responses["group_settings"]["overrides"] = {}
        
        self.responses["group_settings"]["overrides"][chat_id] = mode
        self.save_responses()
        self.load_group_overrides()
        
        self.override_chat_id.delete(0, END)
        self.log_message(f"Added group override for {chat_id}: {mode}")
    
    def delete_group_override(self):
        """Delete selected group override"""
        selection = self.group_overrides_list.curselection()
        if not selection:
            return
        
        item = self.group_overrides_list.get(selection[0])
        chat_id = item.split(":")[0].strip()
        
        if "group_settings" in self.responses and "overrides" in self.responses["group_settings"]:
            if chat_id in self.responses["group_settings"]["overrides"]:
                del self.responses["group_settings"]["overrides"][chat_id]
                self.save_responses()
                self.load_group_overrides()
                self.log_message(f"Deleted group override for {chat_id}")
    
    def save_group_settings(self):
        """Save group settings"""
        if "group_settings" not in self.responses:
            self.responses["group_settings"] = {}
        
        self.responses["group_settings"]["respond_when_tagged"] = self.respond_when_tagged.get()
        self.responses["group_settings"]["respond_to_replies"] = self.respond_to_replies.get()
        self.responses["group_settings"]["ignore_bot_commands"] = self.ignore_bot_commands.get()
        self.save_responses()
        self.log_message("Group settings saved")
    
    def on_custom_response_select(self, event):
        """Handle custom response selection"""
        selection = self.custom_responses_list.curselection()
        if selection:
            item = self.custom_responses_list.get(selection[0])
            keyword = item.split(":")[0]
            response = self.responses.get("custom_responses", {}).get(keyword, "")
            self.keyword_entry.delete(0, END)
            self.keyword_entry.insert(0, keyword)
            self.custom_response_entry.delete(0, END)
            self.custom_response_entry.insert(0, response)
    
    def add_custom_response(self):
        """Add or update custom response"""
        keyword = self.keyword_entry.get().strip().lower()
        response = self.custom_response_entry.get().strip()
        
        if not keyword or not response:
            messagebox.showerror("Error", "Please enter both keyword and response!")
            return
        
        if "custom_responses" not in self.responses:
            self.responses["custom_responses"] = {}
        
        self.responses["custom_responses"][keyword] = response
        self.save_responses()
        self.load_custom_responses()
        
        self.keyword_entry.delete(0, END)
        self.custom_response_entry.delete(0, END)
        self.log_message(f"Added custom response for keyword: {keyword}")
    
    def delete_custom_response(self):
        """Delete selected custom response"""
        selection = self.custom_responses_list.curselection()
        if not selection:
            return
        
        item = self.custom_responses_list.get(selection[0])
        keyword = item.split(":")[0]
        
        if keyword in self.responses.get("custom_responses", {}):
            del self.responses["custom_responses"][keyword]
            self.save_responses()
            self.load_custom_responses()
            self.keyword_entry.delete(0, END)
            self.custom_response_entry.delete(0, END)
            self.log_message(f"Deleted custom response for keyword: {keyword}")
    
    def save_away_message(self):
        """Save away message"""
        away_msg = self.away_message_text.get(1.0, END).strip()
        self.responses["away_message"] = away_msg
        self.save_responses()
        self.log_message("Away message saved")
        messagebox.showinfo("Success", "Away message saved!")
    
    def change_mode(self):
        """Change response mode"""
        self.response_mode = self.mode_var.get()
        
        if self.response_mode == "normal":
            self.mode_status.config(text="Normal Mode: Manual responses only", fg="green")
            self.log_message("Switched to Normal mode - no auto-responses")
        elif self.response_mode == "away":
            self.mode_status.config(text="Away Mode: Auto-responding to all messages", fg="orange")
            self.log_message("Switched to Away mode - auto-responding to all messages")
        else:
            self.mode_status.config(text="Custom Mode: Keyword-based auto-responses", fg="blue")
            self.log_message("Switched to Custom mode - keyword-based responses")
    
    def clear_queue(self):
        """Clear message queue"""
        self.message_queue = []
        self.queue_display.config(state=NORMAL)
        self.queue_display.delete(1.0, END)
        self.queue_display.insert(1.0, "Queue cleared\n")
        self.queue_display.config(state=DISABLED)
        self.log_message("Message queue cleared")
    
    def add_to_queue(self, sender, message):
        """Add message to queue"""
        queue_entry = f"[{datetime.now().strftime('%H:%M:%S')}] {sender}: {message}\n"
        self.message_queue.append(queue_entry)
        
        # Update queue display
        self.queue_display.config(state=NORMAL)
        self.queue_display.insert(END, queue_entry)
        self.queue_display.see(END)
        self.queue_display.config(state=DISABLED)
    
    def get_custom_response(self, message):
        """Get custom response based on keywords"""
        message_lower = message.lower()
        custom = self.responses.get("custom_responses", {})
        
        for keyword, response in custom.items():
            if keyword.lower() in message_lower:
                return response
        return None
    
    def should_respond_in_group(self, event, message_text):
        """Determine if bot should respond to a group message"""
        group_settings = self.responses.get("group_settings", {})
        
        # Check for group-specific override
        overrides = group_settings.get("overrides", {})
        chat_id_str = str(event.chat_id)
        
        if chat_id_str in overrides:
            override_mode = overrides[chat_id_str]
            if override_mode == "never_respond":
                return False, None
            elif override_mode == "always_respond":
                return True, None
        
        # Check if it's a reply to the bot
        if group_settings.get("respond_to_replies", True) and event.message.is_reply:
            # Check if the reply is to the bot's message
            reply_to = event.message.reply_to_msg_id
            async def check_reply():
                try:
                    original_msg = await event.get_reply_message()
                    me = await self.client.get_me()
                    if original_msg and original_msg.sender_id == me.id:
                        return True
                except:
                    pass
                return False
            
            # This is async, but we need to handle it differently
            # We'll return a special flag to indicate we need to check asynchronously
            return "check_reply", None
        
        # Check if tagged
        if group_settings.get("respond_when_tagged", True) and self.bot_username:
            if f"@{self.bot_username}" in message_text:
                return True, None
        
        # Check if it's a bot command (starts with /)
        if group_settings.get("ignore_bot_commands", True) and message_text.startswith("/"):
            return False, None
        
        return False, None
    
    def setup_message_handler(self):
        """Set up the message handler with group mention detection"""
        @self.client.on(events.NewMessage(incoming=True))
        async def handle_new_message(event):
            try:
                # Get sender info
                sender = await event.get_sender()
                sender_name = sender.first_name or str(sender.id)
                
                # Check if message is from self
                me = await self.client.get_me()
                if sender.id == me.id:
                    return
                
                # Get message text
                message_text = event.message.text or "[Media/Sticker]"
                
                # Get bot username if not already set
                if not self.bot_username:
                    self.bot_username = me.username
                
                # Determine if it's a group or private chat
                is_group = event.is_group or event.is_channel
                
                # Check if we should process this message
                should_respond = False
                response = None
                is_mention = False
                
                if is_group:
                    # Handle group messages
                    group_decision = await self.should_respond_in_group_async(event, message_text)
                    
                    if group_decision == "check_reply":
                        # We need to check if it's a reply to the bot
                        original_msg = await event.get_reply_message()
                        if original_msg and original_msg.sender_id == me.id:
                            should_respond = True
                            is_mention = True
                            self.log_message(f"Reply to bot in group from {sender_name}: {message_text}", "group_mention")
                        else:
                            self.log_message(f"Ignored group message from {sender_name}: {message_text}", "system")
                            return
                    elif group_decision is True:
                        should_respond = True
                        is_mention = True
                        self.log_message(f"Mention in group from {sender_name}: {message_text}", "group_mention")
                    else:
                        # Message ignored
                        if message_text:
                            self.log_message(f"Ignored group message from {sender_name}: {message_text}", "system")
                        return
                else:
                    # Private chat - always process
                    should_respond = True
                    is_mention = False
                    self.log_message(f"{sender_name}: {message_text}", "received")
                
                # Check if we should auto-respond based on mode
                if should_respond and self.response_mode != "normal":
                    if self.response_mode == "away":
                        response = self.responses.get("away_message", "I'm currently away.")
                    elif self.response_mode == "custom":
                        response = self.get_custom_response(message_text)
                    
                    if response:
                        # Add to queue
                        self.root.after(0, lambda n=sender_name, m=message_text: 
                                      self.add_to_queue(n, m))
                        
                        # Send auto-response
                        await event.reply(response)
                        self.root.after(0, lambda n=sender_name: 
                                      self.log_message(f"Auto-response sent to {n}", "sent"))
                
                # Update chat list with this message
                self.root.after(0, lambda sid=sender.id, n=sender_name, m=message_text: 
                              self.update_chat_list(sid, n, m))
                
            except Exception as e:
                error_msg = str(e)
                self.root.after(0, lambda err=error_msg: self.log_message(f"Error handling message: {err}"))
        
        self.log_message("✅ Message handler registered with group mention detection")
    
    async def should_respond_in_group_async(self, event, message_text):
        """Async version of should_respond_in_group"""
        group_settings = self.responses.get("group_settings", {})
        
        # Check for group-specific override
        overrides = group_settings.get("overrides", {})
        chat_id_str = str(event.chat_id)
        
        if chat_id_str in overrides:
            override_mode = overrides[chat_id_str]
            if override_mode == "never_respond":
                return False
            elif override_mode == "always_respond":
                return True
        
        # Check if it's a reply to the bot
        if group_settings.get("respond_to_replies", True) and event.message.is_reply:
            try:
                original_msg = await event.get_reply_message()
                me = await self.client.get_me()
                if original_msg and original_msg.sender_id == me.id:
                    return True
            except:
                pass
        
        # Check if tagged
        if group_settings.get("respond_when_tagged", True) and self.bot_username:
            if f"@{self.bot_username}" in message_text:
                return True
        
        # Check if it's a bot command (starts with /)
        if group_settings.get("ignore_bot_commands", True) and message_text.startswith("/"):
            return False
        
        return False
    
    def update_chat_list(self, chat_id, chat_name, last_message):
        """Update chat list with recent messages"""
        # Check if chat already exists
        found = False
        for i in range(self.chat_listbox.size()):
            item = self.chat_listbox.get(i)
            if str(chat_id) in item:
                # Update existing chat
                self.chat_listbox.delete(i)
                self.chat_listbox.insert(0, f"{chat_name} ({chat_id}) - {last_message[:30]}")
                found = True
                break
        
        if not found:
            # Add new chat
            self.chat_listbox.insert(0, f"{chat_name} ({chat_id}) - {last_message[:30]}")
        
        # Store chat info
        self.chats[chat_id] = {"name": chat_name, "last_message": last_message}
    
    def on_chat_select(self, event):
        """Handle chat selection"""
        selection = self.chat_listbox.curselection()
        if selection:
            item = self.chat_listbox.get(selection[0])
            # Extract chat ID from item
            import re
            match = re.search(r'\((\d+)\)', item)
            if match:
                chat_id = int(match.group(1))
                self.selected_chat = chat_id
                chat_info = self.chats.get(chat_id, {})
                self.chat_info.config(text=f"Selected: {chat_info.get('name', 'Unknown')}")
                self.log_message(f"Selected chat: {chat_info.get('name', 'Unknown')}")
    
    def load_chats(self):
        """Load recent chats"""
        if not self.client or not self.is_running:
            messagebox.showerror("Error", "Please connect first!")
            return
        
        def on_chats_loaded(dialogs):
            """Callback when chats are loaded"""
            self.chat_listbox.delete(0, END)
            for dialog in dialogs:
                name = dialog.name or str(dialog.id)
                last_msg = dialog.message.text[:30] if dialog.message and dialog.message.text else "No messages"
                self.chat_listbox.insert(END, f"{name} ({dialog.id}) - {last_msg}")
                self.chats[dialog.id] = {"name": name, "last_message": last_msg}
            self.log_message(f"Loaded {len(dialogs)} chats")
        
        async def get_dialogs():
            dialogs = []
            async for dialog in self.client.iter_dialogs():
                dialogs.append(dialog)
            return dialogs
        
        self.run_async(get_dialogs(), on_chats_loaded)
        self.log_message("Loading chats...")
    
    def send_message(self):
        """Send message to selected chat"""
        if not self.client or not self.is_running:
            messagebox.showerror("Error", "Please connect first!")
            return
        
        if not self.selected_chat:
            messagebox.showerror("Error", "Please select a chat first!")
            return
        
        message = self.message_input.get(1.0, END).strip()
        if not message:
            return
        
        async def send():
            try:
                entity = await self.client.get_entity(self.selected_chat)
                await self.client.send_message(entity, message)
                self.log_message(f"Sent: {message}", "sent")
                self.message_input.delete(1.0, END)
            except Exception as e:
                self.log_message(f"Error sending message: {e}")
        
        self.run_async(send())
        self.log_message(f"Sending message...")
    
    def connect_bot(self):
        """Connect to Telegram"""
        api_id = self.api_id_entry.get().strip()
        api_hash = self.api_hash_entry.get().strip()
        phone = self.phone_entry.get().strip()
        
        if not api_id or not api_hash or not phone:
            messagebox.showerror("Error", "Please fill all API credentials!")
            return
        
        self.current_phone = phone
        self.current_api_id = int(api_id)
        self.current_api_hash = api_hash
        self.current_session_name = f"session_{phone.replace('+', '').replace(' ', '')}"
        
        async def connect_and_check():
            try:
                self.client = TelegramClient(self.current_session_name, self.current_api_id, self.current_api_hash)
                await self.client.connect()
                
                if not await self.client.is_user_authorized():
                    self.root.after(0, self.show_verification_input)
                    self.log_message("Sending verification code...")
                    result = await self.client.send_code_request(self.current_phone)
                    self.phone_code_hash = result.phone_code_hash
                    self.log_message(f"✅ Verification code sent to {self.current_phone}")
                    return False
                else:
                    return True
            except Exception as e:
                self.root.after(0, lambda: self.on_connect_failure(str(e)))
                return False
        
        def on_connected(success):
            if success:
                self.setup_message_handler()
                self.root.after(0, self.on_connect_success)
        
        self.run_async(connect_and_check(), on_connected)
        self.log_message("Connecting to Telegram...")
    
    def show_verification_input(self):
        """Show verification code input"""
        self.verification_code.pack(side=LEFT, padx=5)
        self.submit_code_btn.pack(side=LEFT, padx=5)
        self.resend_code_btn.pack(side=LEFT, padx=5)
        self.verification_code.focus()
        self.update_connection_status("✓ Verification code sent! Please enter the code.")
    
    def submit_verification_code(self):
        """Submit verification code"""
        code = self.verification_code.get().strip()
        if not code:
            messagebox.showerror("Error", "Please enter the verification code!")
            return
        
        async def verify():
            try:
                await self.client.sign_in(self.current_phone, code, phone_code_hash=self.phone_code_hash)
                return True
            except Exception as e:
                self.log_message(f"Verification failed: {e}")
                return False
        
        def on_verified(success):
            if success:
                self.setup_message_handler()
                self.root.after(0, self.on_connect_success)
            else:
                self.root.after(0, lambda: self.on_connect_failure("Invalid verification code"))
        
        self.run_async(verify(), on_verified)
    
    def resend_verification_code(self):
        """Resend verification code"""
        async def resend():
            if self.client and self.client.is_connected():
                result = await self.client.send_code_request(self.current_phone)
                self.phone_code_hash = result.phone_code_hash
                self.log_message("✅ Verification code resent!")
                return True
            return False
        
        def on_resend(success):
            if success:
                self.update_connection_status("✓ Code resent! Please enter the code.")
        
        self.run_async(resend(), on_resend)
    
    def update_connection_status(self, message):
        """Update connection status display"""
        self.connection_status.config(state=NORMAL)
        self.connection_status.insert(END, f"{message}\n")
        self.connection_status.see(END)
        self.connection_status.config(state=DISABLED)
    
    def on_connect_success(self):
        """Handle successful connection"""
        self.is_running = True
        self.connect_btn.config(state=DISABLED)
        self.disconnect_btn.config(state=NORMAL)
        self.status_bar.config(text="Connected to Telegram")
        self.log_message("✅ Successfully connected to Telegram!")
        self.update_connection_status("✓ Connected successfully!")
        
        # Hide verification inputs
        self.verification_code.pack_forget()
        self.submit_code_btn.pack_forget()
        self.resend_code_btn.pack_forget()
        
        # Load chats
        self.load_chats()
        
        # Set default mode
        self.change_mode()
    
    def on_connect_failure(self, error=None):
        """Handle connection failure"""
        self.is_running = False
        self.log_message(f"Connection failed: {error}")
        self.status_bar.config(text="Connection failed")
        self.update_connection_status(f"✗ Connection failed: {error}")
        
        self.verification_code.pack_forget()
        self.submit_code_btn.pack_forget()
        self.resend_code_btn.pack_forget()
        
        if self.client:
            async def cleanup():
                await self.client.disconnect()
            self.run_async(cleanup())
            self.client = None
        
        messagebox.showerror("Connection Error", f"Failed to connect: {error}")
    
    def disconnect_bot(self):
        """Disconnect from Telegram"""
        if self.client:
            async def disconnect():
                await self.client.disconnect()
            self.run_async(disconnect())
        
        self.is_running = False
        self.client = None
        self.connect_btn.config(state=NORMAL)
        self.disconnect_btn.config(state=DISABLED)
        self.status_bar.config(text="Disconnected")
        self.log_message("Disconnected from Telegram")
    
    def save_to_env(self):
        """Save credentials to .env"""
        api_id = self.api_id_entry.get()
        api_hash = self.api_hash_entry.get()
        phone = self.phone_entry.get()
        
        if not api_id or not api_hash or not phone:
            messagebox.showerror("Error", "Please fill all fields!")
            return
        
        try:
            with open('.env', 'w') as f:
                f.write(f"TELEGRAM_API_ID={api_id}\n")
                f.write(f"TELEGRAM_API_HASH={api_hash}\n")
                f.write(f"TELEGRAM_PHONE={phone}\n")
            
            self.log_message("Credentials saved to .env")
            messagebox.showinfo("Success", "Credentials saved to .env!")
            load_dotenv(override=True)
        except Exception as e:
            error_msg = str(e)
            self.log_message(f"Error saving to .env: {error_msg}")
            messagebox.showerror("Error", f"Failed to save: {error_msg}")
    
    def send_broadcast(self):
        """Send broadcast message"""
        if not self.client or not self.is_running:
            messagebox.showerror("Error", "Please connect first!")
            return
        
        message = self.broadcast_message.get(1.0, END).strip()
        recipients_text = self.recipients_list.get(1.0, END).strip()
        
        if not message or not recipients_text:
            messagebox.showerror("Error", "Please enter message and recipients!")
            return
        
        recipients = [r.strip() for r in recipients_text.split('\n') if r.strip()]
        
        async def send_messages():
            success = 0
            fail = 0
            
            self.root.after(0, lambda: self.broadcast_progress.start())
            
            for i, recipient in enumerate(recipients):
                try:
                    entity = await self.client.get_entity(recipient)
                    await self.client.send_message(entity, message)
                    success += 1
                    self.root.after(0, lambda r=recipient: self.update_broadcast_status(f"✓ Sent to {r}"))
                except Exception as e:
                    fail += 1
                    error_msg = str(e)
                    self.log_message(f"Failed to send to {recipient}: {error_msg}")
                
                progress = (i + 1) / len(recipients) * 100
                self.root.after(0, lambda p=progress: self.update_broadcast_progress(p))
            
            self.root.after(0, lambda s=success, f=fail: self.broadcast_complete(s, f))
        
        self.run_async(send_messages())
        self.log_message(f"Starting broadcast to {len(recipients)} recipients...")
    
    def update_broadcast_progress(self, value):
        """Update broadcast progress"""
        self.broadcast_progress.stop()
        self.broadcast_progress['value'] = value
        self.broadcast_progress['mode'] = 'determinate'
    
    def update_broadcast_status(self, status):
        """Update broadcast status"""
        self.broadcast_status.config(text=status)
        self.broadcast_status.update()
    
    def broadcast_complete(self, success, fail):
        """Handle broadcast completion"""
        self.broadcast_progress.stop()
        self.broadcast_status.config(text=f"Complete! Success: {success}, Failed: {fail}")
        messagebox.showinfo("Complete", f"Sent to {success} recipients\nFailed: {fail}")
        self.broadcast_progress['mode'] = 'indeterminate'
    
    def load_recipients_file(self):
        """Load recipients from file"""
        filename = filedialog.askopenfilename(filetypes=[("Text files", "*.txt")])
        if filename:
            try:
                with open(filename, 'r') as f:
                    content = f.read()
                self.recipients_list.delete(1.0, END)
                self.recipients_list.insert(1.0, content)
                self.log_message(f"Loaded recipients from {filename}")
            except Exception as e:
                error_msg = str(e)
                messagebox.showerror("Error", f"Failed to load: {error_msg}")
    
    def load_config(self):
        """Load configuration"""
        self.config = {}
        if os.path.exists(self.config_file):
            try:
                config = configparser.ConfigParser()
                config.read(self.config_file)
                if 'credentials' in config:
                    self.config = dict(config['credentials'])
            except:
                pass
    
    def load_responses(self):
        """Load responses"""
        if os.path.exists(self.responses_file):
            try:
                with open(self.responses_file, 'r') as f:
                    self.responses = json.load(f)
            except:
                self.responses = {}
        else:
            self.responses = {}
    
    def save_responses(self):
        """Save responses"""
        try:
            with open(self.responses_file, 'w') as f:
                json.dump(self.responses, f, indent=4)
        except Exception as e:
            error_msg = str(e)
            self.log_message(f"Error saving responses: {error_msg}")
    
    def clear_logs(self):
        """Clear logs"""
        self.log_text.delete(1.0, END)
        self.log_message("Logs cleared")
    
    def export_logs(self):
        """Export logs"""
        filename = filedialog.asksaveasfilename(defaultextension=".txt")
        if filename:
            try:
                with open(filename, 'w') as f:
                    f.write(self.log_text.get(1.0, END))
                messagebox.showinfo("Success", f"Logs exported to {filename}")
            except Exception as e:
                error_msg = str(e)
                messagebox.showerror("Error", f"Failed to export: {error_msg}")

def main():
    root = Tk()
    app = TelegramBotGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
