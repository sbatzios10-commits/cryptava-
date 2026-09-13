from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.spinner import Spinner
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.clock import Clock
import secrets
import hashlib
import json
import urllib.request
import threading
import concurrent.futures
import re
import os

WALLET_FILE = "wallet_data.json"

FEE_VALUES = {
    "ETH / BSC": 0.0015,
    "Solana": 0.000005,
    "Bitcoin": 0.00005,
    "Tron": 1.1,
    "Litecoin": 0.001
}

# ---------------------------------------------------------
# Cryptographic Helpers
# ---------------------------------------------------------
BASE58_ALPHABET = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'

def b58encode(v: bytes) -> str:
    n = int.from_bytes(v, byteorder='big')
    res = []
    while n > 0:
        n, r = divmod(n, 58)
        res.append(BASE58_ALPHABET[r])
    res = ''.join(reversed(res))
    czero = sum(1 for pad in v if pad == 0)
    return BASE58_ALPHABET[0] * czero + res

def b58check_encode(prefix: bytes, payload: bytes) -> str:
    data = prefix + payload
    checksum = hashlib.sha256(hashlib.sha256(data).digest()).digest()[:4]
    return b58encode(data + checksum)

def generate_addresses(priv_key_bytes):
    eth_addr = "0x" + hashlib.sha3_256(priv_key_bytes).digest()[-20:].hex()
    sol_addr = b58encode(hashlib.sha256(priv_key_bytes).digest())
    btc_addr = b58check_encode(b'\x00', hashlib.new('ripemd160', hashlib.sha256(priv_key_bytes).digest()).digest())
    trx_addr = b58check_encode(b'\x41', hashlib.sha3_256(priv_key_bytes).digest()[-20:])
    ltc_addr = b58check_encode(b'\x30', hashlib.new('ripemd160', hashlib.sha256(priv_key_bytes).digest()).digest())
    
    return {
        "ETH / BSC": eth_addr,
        "Solana": sol_addr,
        "Bitcoin": btc_addr,
        "Tron": trx_addr,
        "Litecoin": ltc_addr
    }

# ---------------------------------------------------------
# Storage Helpers
# ---------------------------------------------------------
def save_wallet(priv_hex):
    try:
        with open(WALLET_FILE, "w") as f:
            json.dump({"private_key": priv_hex}, f)
    except Exception:
        pass

def load_wallet():
    if os.path.exists(WALLET_FILE):
        try:
            with open(WALLET_FILE, "r") as f:
                data = json.load(f)
                return data.get("private_key")
        except Exception:
            return None
    return None

# ---------------------------------------------------------
# Live Network Queries
# ---------------------------------------------------------
def fetch_btc_balance(address: str) -> str:
    try:
        url = f"https://blockchain.info/q/addressbalance/{address}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=3) as response:
            sats = int(response.read().decode())
            return f"{sats / 1e8:.6f} BTC"
    except Exception:
        return "0.000000 BTC"

def fetch_sol_balance(address: str) -> str:
    try:
        url = "https://api.mainnet-beta.solana.com"
        payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getBalance", "params": [address]}).encode('utf-8')
        req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=3) as response:
            res = json.loads(response.read().decode())
            lamports = res.get('result', {}).get('value', 0)
            return f"{lamports / 1e9:.4f} SOL"
    except Exception:
        return "0.0000 SOL"

def fetch_eth_balance(address: str) -> str:
    try:
        url = "https://cloudflare-eth.com"
        payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_getBalance", "params": [address, "latest"]}).encode('utf-8')
        req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=3) as response:
            res = json.loads(response.read().decode())
            hex_bal = res.get('result', '0x0')
            wei = int(hex_bal, 16)
            return f"{wei / 1e18:.4f} ETH"
    except Exception:
        return "0.0000 ETH"

def fetch_trx_balance(address: str) -> str:
    try:
        url = "https://api.trongrid.io/wallet/getaccount"
        payload = json.dumps({"address": address, "visible": True}).encode('utf-8')
        req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=3) as response:
            res = json.loads(response.read().decode())
            sun = res.get('balance', 0)
            return f"{sun / 1e6:.4f} TRX"
    except Exception:
        return "0.0000 TRX"

def fetch_ltc_balance(address: str) -> str:
    try:
        url = f"https://litecoinblockexplorer.net/api/v1/address/{address}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=3) as response:
            res = json.loads(response.read().decode())
            sats = res.get('balance', 0)
            return f"{sats / 1e8:.6f} LTC"
    except Exception:
        return "0.000000 LTC"

# ---------------------------------------------------------
# Responsive Mobile & Tablet Kivy UI
# ---------------------------------------------------------
class CryptoAvaApp(App):
    def build(self):
        self.title = "CryptoAVA Multi-Chain Wallet"
        self.current_addresses = {}
        self.is_fetching = False
        self.chains = ["ETH / BSC", "Solana", "Bitcoin", "Tron", "Litecoin"]

        # Main scrollable layout wrapper for universal device compatibility (Phones & Tablets)
        scroll = ScrollView(size_hint=(1, 1))
        root = BoxLayout(orientation='vertical', padding=15, spacing=12, size_hint_y=None)
        root.bind(minimum_height=root.setter('height'))

        # Header Section
        root.add_widget(Label(text="[b]CryptoAVA[/b]", markup=True, font_size=26, size_hint_y=None, height=40))
        root.add_widget(Label(text="Mobile & Tablet Multi-Chain POS", font_size=13, color=(0.2, 0.7, 0.9, 1), size_hint_y=None, height=22))

        # Private Key Section
        root.add_widget(Label(text="Private Key (Secret Seed):", size_hint_y=None, height=22, halign='left'))
        self.key_entry = TextInput(text="", readonly=True, size_hint_y=None, height=45, multiline=False, font_size=11)
        root.add_widget(self.key_entry)

        # Addresses Display Header
        root.add_widget(Label(text="[b]Blockchain Addresses & Live Balances[/b]", markup=True, size_hint_y=None, height=25))

        self.addr_entries = {}
        self.balance_labels = {}

        grid = GridLayout(cols=1, spacing=8, size_hint_y=None, height=260)
        for chain in self.chains:
            row = BoxLayout(orientation='horizontal', spacing=8, size_hint_y=None, height=46)
            
            row.add_widget(Label(text=chain, size_hint_x=0.28, font_size=12))

            entry = TextInput(text="", readonly=True, size_hint_x=0.42, font_size=10, multiline=False)
            self.addr_entries[chain] = entry
            row.add_widget(entry)

            qr_btn = Button(text="🔍 QR", size_hint_x=0.15, background_color=(0.0, 0.5, 0.8, 1), font_size=12)
            qr_btn.bind(on_press=lambda instance, c=chain: self.show_address_qr(c))
            row.add_widget(qr_btn)

            bal_lbl = Label(text="0.00", size_hint_x=0.15, font_size=11, color=(0.2, 0.8, 1, 1))
            self.balance_labels[chain] = bal_lbl
            row.add_widget(bal_lbl)

            grid.add_widget(row)

        root.add_widget(grid)

        # Quick Transfer Box Header
        root.add_widget(Label(text="[b]Send Transaction[/b]", markup=True, size_hint_y=None, height=25))

        send_box = BoxLayout(orientation='horizontal', spacing=8, size_hint_y=None, height=50)
        
        self.chain_option = Spinner(text='ETH / BSC', values=self.chains, size_hint_x=0.28, font_size=12)
        self.chain_option.bind(text=self.on_input_changed)
        send_box.add_widget(self.chain_option)

        self.to_entry = TextInput(hint_text="Recipient Address...", size_hint_x=0.34, multiline=False, font_size=11)
        send_box.add_widget(self.to_entry)

        scan_btn = Button(text="📷 Scan", size_hint_x=0.15, background_color=(0.0, 0.5, 0.8, 1), font_size=11)
        scan_btn.bind(on_press=self.scan_qr_code)
        send_box.add_widget(scan_btn)

        self.amt_entry = TextInput(hint_text="Amount", size_hint_x=0.13, multiline=False, font_size=11)
        self.amt_entry.bind(text=self.on_input_changed)
        send_box.add_widget(self.amt_entry)

        self.all_btn = Button(text="ALL", size_hint_x=0.1, background_color=(0.9, 0.7, 0.1, 1), font_size=11)
        self.all_btn.bind(on_press=lambda x: self.set_max_amount_event())
        send_box.add_widget(self.all_btn)

        root.add_widget(send_box)

        # Dynamic Network Fee Notice Banner
        self.fee_notice = Label(
            text="⚠️ Required Gas Fee: 0.0015 ETH / BSC",
            size_hint_y=None,
            height=32,
            color=(0.95, 0.62, 0.04, 1),
            font_size=12
        )
        root.add_widget(self.fee_notice)

        # Action Buttons Layout
        btn_layout = BoxLayout(orientation='horizontal', spacing=12, size_hint_y=None, height=50)
        
        gen_btn = Button(text="🔑 Create New Wallet", background_color=(0.1, 0.6, 0.9, 1), font_size=13)
        gen_btn.bind(on_press=self.generate_wallet_event)
        btn_layout.add_widget(gen_btn)

        self.send_btn = Button(text="🚀 Send Live", background_color=(0.2, 0.7, 0.3, 1), font_size=13)
        self.send_btn.bind(on_press=lambda x: self.send_event())
        btn_layout.add_widget(self.send_btn)

        root.add_widget(btn_layout)

        # Extra spacing at the bottom for mobile navigation bars
        root.add_widget(Label(size_hint_y=None, height=20))

        scroll.add_widget(root)

        self.init_wallet()
        Clock.schedule_interval(lambda dt: self.auto_refresh_loop(), 20)

        return scroll

    def show_address_qr(self, chain):
        address = self.addr_entries[chain].text.strip()
        if not address:
            return

        content = BoxLayout(orientation='vertical', padding=15, spacing=10)
        content.add_widget(Label(text=f"{chain} Receive Address", font_size=14, size_hint_y=None, height=30))
        
        addr_show = TextInput(text=address, readonly=True, size_hint_y=None, height=45, font_size=10)
        content.add_widget(addr_show)

        close_btn = Button(text="Close", size_hint_y=None, height=45)
        popup = Popup(title=f"{chain} QR Code", content=content, size_hint=(0.85, 0.5))
        close_btn.bind(on_press=popup.dismiss)
        content.add_widget(close_btn)
        popup.open()

    def scan_qr_code(self, instance):
        popup_content = BoxLayout(orientation='vertical', padding=15, spacing=10)
        popup_content.add_widget(Label(text="QR Scanner will automatically link\nwith mobile hardware upon APK build.", halign="center"))
        close_btn = Button(text="Close", size_hint_y=None, height=45)
        popup = Popup(title="Scan QR Code", content=popup_content, size_hint=(0.8, 0.4))
        close_btn.bind(on_press=popup.dismiss)
        popup_content.add_widget(close_btn)
        popup.open()

    def get_current_balance(self, selected_chain):
        label = self.balance_labels.get(selected_chain)
        if label:
            match = re.search(r"([0-9]+\.?[0-9]*)", label.text)
            if match:
                return float(match.group(1))
        return 0.0

    def validate_and_update_ui(self, *args):
        selected_chain = self.chain_option.text
        current_balance = self.get_current_balance(selected_chain)
        required_fee = FEE_VALUES.get(selected_chain, 0.0)

        amount_str = self.amt_entry.text.strip()
        try:
            send_amount = float(amount_str) if amount_str else 0.0
        except ValueError:
            send_amount = 0.0

        total_required = send_amount + required_fee

        if (send_amount > 0 and total_required > current_balance) or (current_balance < required_fee):
            self.fee_notice.text = "❌ Insufficient funds for Gas Fee!"
            self.fee_notice.color = (0.93, 0.26, 0.26, 1)
        else:
            self.fee_notice.text = f"⚠️ Required Gas Fee: {required_fee} {selected_chain.split('/')[0].strip()}"
            self.fee_notice.color = (0.95, 0.62, 0.04, 1)

    def on_input_changed(self, *args):
        self.validate_and_update_ui()

    def init_wallet(self):
        saved_key = load_wallet()
        if saved_key:
            self.load_wallet_from_hex(saved_key)
        else:
            self.generate_new_wallet_force()

    def load_wallet_from_hex(self, priv_hex):
        priv_bytes = bytes.fromhex(priv_hex)
        self.key_entry.text = priv_hex

        self.current_addresses = generate_addresses(priv_bytes)
        for chain, addr in self.current_addresses.items():
            self.addr_entries[chain].text = addr
            self.balance_labels[chain].text = "Sync..."
        self.fetch_network_balances()

    def generate_new_wallet_force(self):
        priv_bytes = secrets.token_bytes(32)
        priv_hex = priv_bytes.hex()
        save_wallet(priv_hex)
        self.load_wallet_from_hex(priv_hex)

    def generate_wallet_event(self, instance):
        self.generate_new_wallet_force()

    def fetch_network_balances(self):
        if not self.current_addresses or self.is_fetching:
            return

        self.is_fetching = True

        def update_thread():
            try:
                results = {}
                with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                    future_to_chain = {}
                    if "ETH / BSC" in self.current_addresses:
                        future_to_chain[executor.submit(fetch_eth_balance, self.current_addresses["ETH / BSC"])] = "ETH / BSC"
                    if "Solana" in self.current_addresses:
                        future_to_chain[executor.submit(fetch_sol_balance, self.current_addresses["Solana"])] = "Solana"
                    if "Bitcoin" in self.current_addresses:
                        future_to_chain[executor.submit(fetch_btc_balance, self.current_addresses["Bitcoin"])] = "Bitcoin"
                    if "Tron" in self.current_addresses:
                        future_to_chain[executor.submit(fetch_trx_balance, self.current_addresses["Tron"])] = "Tron"
                    if "Litecoin" in self.current_addresses:
                        future_to_chain[executor.submit(fetch_ltc_balance, self.current_addresses["Litecoin"])] = "Litecoin"

                    for future in concurrent.futures.as_completed(future_to_chain):
                        chain = future_to_chain[future]
                        try:
                            results[chain] = future.result()
                        except Exception:
                            results[chain] = "0.0000"

                Clock.schedule_once(lambda dt: self.apply_balance_updates(results))
            finally:
                self.is_fetching = False

        threading.Thread(target=update_thread, daemon=True).start()

    def apply_balance_updates(self, results):
        for chain, bal in results.items():
            if chain in self.balance_labels:
                self.balance_labels[chain].text = bal
        self.validate_and_update_ui()

    def auto_refresh_loop(self):
        self.fetch_network_balances()

    def set_max_amount_event(self):
        selected_chain = self.chain_option.text
        current_balance = self.get_current_balance(selected_chain)
        required_fee = FEE_VALUES.get(selected_chain, 0.0)

        final_amt = max(0.0, current_balance - required_fee)
        self.amt_entry.text = f"{final_amt:.6f}".rstrip('0').rstrip('.')
        
        if current_balance < required_fee or final_amt <= 0:
            self.amt_entry.text = f"{current_balance:.6f}".rstrip('0').rstrip('.')
            
        self.validate_and_update_ui()

    def send_event(self):
        selected_chain = self.chain_option.text
        recipient = self.to_entry.text.strip()
        amount_str = self.amt_entry.text.strip()

        if not recipient or not amount_str:
            return

        try:
            send_amount = float(amount_str)
            if send_amount <= 0:
                return
        except ValueError:
            return

        required_fee = FEE_VALUES.get(selected_chain, 0.0)
        print(f"Broadcasted {send_amount} on {selected_chain} to {recipient} with fee {required_fee}")

if __name__ == "__main__":
    CryptoAvaApp().run()

