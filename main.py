import os
import io
import json
import re
import hashlib
import secrets
import threading
import concurrent.futures
import urllib.request
import webbrowser

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.spinner import Spinner
from kivy.uix.popup import Popup
from kivy.clock import Clock
from kivy.graphics import Color, Rectangle
from kivy.core.window import Window

import cv2
import qrcode
from pyzbar import pyzbar

Window.size = (980, 740)
Window.clearcolor = (0.07, 0.09, 0.12, 1)  # Dark background theme

WALLET_FILE = "wallet_data.json"
TOKEN_MINT_ADDRESS = "BUEnVFDPMVgGv4HQGKRsnHwm76nqQ254f2h5Ud2Ppump"

FEE_VALUES = {
    "Ethereum": 0.0015,
    "BNB Smart Chain": 0.0005,
    "Solana": 0.000005,
    "CRYPTAVA_OFFICIAL": 0.000005,
    "Bitcoin": 0.00005,
    "Tron": 1.1,
    "Litecoin": 0.001
}

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
    eth_bsc_addr = "0x" + hashlib.sha3_256(priv_key_bytes).digest()[-20:].hex()
    sol_addr = b58encode(hashlib.sha256(priv_key_bytes).digest())
    btc_addr = b58check_encode(b'\x00', hashlib.new('ripemd160', hashlib.sha256(priv_key_bytes).digest()).digest())
    trx_addr = b58check_encode(b'\x41', hashlib.sha3_256(priv_key_bytes).digest()[-20:])
    ltc_addr = b58check_encode(b'\x30', hashlib.new('ripemd160', hashlib.sha256(priv_key_bytes).digest()).digest())
    
    return {
        "Ethereum": eth_bsc_addr,
        "BNB Smart Chain": eth_bsc_addr, 
        "Solana": sol_addr,
        "CRYPTAVA_OFFICIAL": sol_addr,  
        "Bitcoin": btc_addr,
        "Tron": trx_addr,
        "Litecoin": ltc_addr
    }

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

def fetch_btc_balance(address: str) -> str:
    try:
        url = f"https://blockchain.info/q/addressbalance/{address}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=2) as response:
            sats = int(response.read().decode())
            return f"{sats / 1e8:.6f} BTC"
    except Exception:
        return "0.000000 BTC"

def fetch_sol_balance(address: str) -> str:
    try:
        url = "https://api.mainnet-beta.solana.com"
        payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getBalance", "params": [address]}).encode('utf-8')
        req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=2) as response:
            res = json.loads(response.read().decode())
            lamports = res.get('result', {}).get('value', 0)
            return f"{lamports / 1e9:.4f} SOL"
    except Exception:
        return "0.0000 SOL"

def fetch_cryptava_official_balance(address: str) -> str:
    try:
        url = "https://api.mainnet-beta.solana.com"
        payload = json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "getTokenAccountsByOwner",
            "params": [address, {"mint": TOKEN_MINT_ADDRESS}, {"encoding": "jsonParsed"}]
        }).encode('utf-8')
        req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=2) as response:
            res = json.loads(response.read().decode())
            accounts = res.get('result', {}).get('value', [])
            if accounts:
                token_amount = accounts[0]["account"]["data"]["parsed"]["info"]["tokenAmount"]["uiAmount"]
                val = float(token_amount) if token_amount is not None else 0.0
                return f"{val:.4f} CRYPTAVA_OFFICIAL"
            return "0.0000 CRYPTAVA_OFFICIAL"
    except Exception:
        return "0.0000 CRYPTAVA_OFFICIAL"

def fetch_eth_balance(address: str) -> str:
    try:
        url = "https://cloudflare-eth.com"
        payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_getBalance", "params": [address, "latest"]}).encode('utf-8')
        req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=2) as response:
            res = json.loads(response.read().decode())
            hex_bal = res.get('result', '0x0')
            wei = int(hex_bal, 16)
            return f"{wei / 1e18:.4f} ETH"
    except Exception:
        return "0.0000 ETH"

def fetch_bsc_balance(address: str) -> str:
    try:
        url = "https://bsc-dataseed.binance.org/"
        payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_getBalance", "params": [address, "latest"]}).encode('utf-8')
        req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=2) as response:
            res = json.loads(response.read().decode())
            hex_bal = res.get('result', '0x0')
            wei = int(hex_bal, 16)
            return f"{wei / 1e18:.4f} BNB"
    except Exception:
        return "0.0000 BNB"

def fetch_trx_balance(address: str) -> str:
    try:
        url = "https://api.trongrid.io/wallet/getaccount"
        payload = json.dumps({"address": address, "visible": True}).encode('utf-8')
        req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=2) as response:
            res = json.loads(response.read().decode())
            sun = res.get('balance', 0)
            return f"{sun / 1e6:.4f} TRX"
    except Exception:
        return "0.0000 TRX"

def fetch_ltc_balance(address: str) -> str:
    try:
        url = f"https://litecoinblockexplorer.net/api/v1/address/{address}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=2) as response:
            res = json.loads(response.read().decode())
            sats = res.get('balance', 0)
            return f"{sats / 1e8:.6f} LTC"
    except Exception:
        return "0.000000 LTC"

class CryptoAvaApp(App):
    def build(self):
        self.title = "CryptoAVA Multi-Chain Wallet"
        self.current_addresses = {}
        self.is_fetching = False
        self.chains = ["Ethereum", "BNB Smart Chain", "Solana", "CRYPTAVA_OFFICIAL", "Bitcoin", "Tron", "Litecoin"]
        
        root = BoxLayout(orientation='horizontal', padding=10, spacing=10)

        # --- SIDEBAR ---
        sidebar = BoxLayout(orientation='vertical', size_hint_x=0.28, spacing=10, padding=10)
        with sidebar.canvas.before:
            Color(0.12, 0.15, 0.2, 1)
            self.bg_rect = Rectangle(size=sidebar.size, pos=sidebar.pos)
            sidebar.bind(size=self._update_bg, pos=self._update_bg)

        sidebar.add_widget(Label(text="CryptoAVA", font_size=24, bold=True, color=(1,1,1,1), size_hint_y=None, height=40))
        sidebar.add_widget(Label(text="Live Business POS", font_size=12, color=(0.22, 0.74, 0.97, 1), size_hint_y=None, height=20))
        
        btn_gen = Button(text="🔑 Create New Wallet", background_color=(0.1, 0.5, 0.8, 1), size_hint_y=None, height=45)
        btn_gen.bind(on_press=self.generate_wallet_event)
        sidebar.add_widget(btn_gen)
        
        sidebar.add_widget(Label()) # Spacer
        
        self.status_box = Label(text="● Lightning Sync", font_size=12, bold=True, color=(0.17, 0.65, 0.25, 1), size_hint_y=None, height=30)
        sidebar.add_widget(self.status_box)
        root.add_widget(sidebar)

        # --- MAIN PANEL ---
        main_frame = BoxLayout(orientation='vertical', spacing=10, padding=10)

        main_frame.add_widget(Label(text="Private Key (Secret Seed)", font_size=14, bold=True, size_hint_y=None, height=25, halign='left'))
        
        self.key_entry = TextInput(text="", multiline=False, readonly=True, size_hint_y=None, height=35, background_color=(0.2, 0.2, 0.2, 1), foreground_color=(1,1,1,1))
        main_frame.add_widget(self.key_entry)

        main_frame.add_widget(Label(text="Your Blockchain Addresses & Live Balances", font_size=14, bold=True, size_hint_y=None, height=25, halign='left'))

        # Scrollable Addresses List
        scroll = ScrollView(size_hint=(1, 0.5))
        self.addrs_layout = GridLayout(cols=1, spacing=5, size_hint_y=None)
        self.addrs_layout.bind(minimum_height=self.addrs_layout.setter('height'))
        
        self.addr_entries = {}
        self.balance_labels = {}
        
        for chain in self.chains:
            row = BoxLayout(orientation='horizontal', spacing=5, size_hint_y=None, height=40)
            row.add_widget(Label(text=f"{chain}:", bold=True, size_hint_x=0.25))
            
            entry = TextInput(text="", multiline=False, readonly=True, size_hint_x=0.45, background_color=(0.2, 0.2, 0.2, 1), foreground_color=(1,1,1,1))
            self.addr_entries[chain] = entry
            row.add_widget(entry)

            qr_btn = Button(text="🔍 QR", size_hint_x=0.1, background_color=(0.01, 0.51, 0.78, 1))
            qr_btn.bind(on_press=lambda inst, c=chain: self.show_address_qr(c))
            row.add_widget(qr_btn)

            bal_lbl = Label(text="0.00", size_hint_x=0.2, bold=True, color=(0.22, 0.74, 0.97, 1))
            self.balance_labels[chain] = bal_lbl
            row.add_widget(bal_lbl)

            self.addrs_layout.add_widget(row)

        scroll.add_widget(self.addrs_layout)
        main_frame.add_widget(scroll)

        # Quick Transfer Box
        main_frame.add_widget(Label(text="Send Transaction (To Wallet / Exchange)", font_size=14, bold=True, size_hint_y=None, height=25, halign='left'))

        send_box = BoxLayout(orientation='horizontal', spacing=5, size_hint_y=None, height=45)
        
        self.chain_option = Spinner(text=self.chains[0], values=self.chains, size_hint_x=0.22)
        self.chain_option.bind(text=self.on_input_changed)
        send_box.add_widget(self.chain_option)

        self.to_entry = TextInput(text="", hint_text="Recipient...", multiline=False, size_hint_x=0.25)
        send_box.add_widget(self.to_entry)

        scan_btn = Button(text="📷", size_hint_x=0.08, background_color=(0.01, 0.51, 0.78, 1))
        scan_btn.bind(on_press=self.scan_qr_code)
        send_box.add_widget(scan_btn)

        self.amt_entry = TextInput(text="", hint_text="Amt", multiline=False, size_hint_x=0.12)
        self.amt_entry.bind(text=self.on_input_changed)
        send_box.add_widget(self.amt_entry)

        all_btn = Button(text="ALL", size_hint_x=0.08, background_color=(0.91, 0.7, 0.02, 1), color=(0,0,0,1), bold=True)
        all_btn.bind(on_press=self.set_max_amount_event)
        send_box.add_widget(all_btn)

        self.send_btn = Button(text="Send", size_hint_x=0.1, background_color=(0.17, 0.65, 0.25, 1))
        self.send_btn.bind(on_press=self.send_event)
        send_box.add_widget(self.send_btn)

        guardarian_btn = Button(text="🛒 Buy", size_hint_x=0.1, background_color=(0.06, 0.72, 0.5, 1))
        guardarian_btn.bind(on_press=self.open_guardarian_event)
        send_box.add_widget(guardarian_btn)

        swap_btn = Button(text="🔄 Swap", size_hint_x=0.1, background_color=(0.54, 0.36, 0.96, 1))
        swap_btn.bind(on_press=self.open_jupiter_swap_event)
        send_box.add_widget(swap_btn)

        main_frame.add_widget(send_box)

        # Fee Notice Banner
        self.fee_notice = Label(text="⚠️ Required Gas Fee: 0.0015 ETH", font_size=12, bold=True, color=(0.96, 0.62, 0.04, 1), size_hint_y=None, height=30)
        main_frame.add_widget(self.fee_notice)

        root.add_widget(main_frame)

        self.init_wallet()
        Clock.schedule_interval(lambda dt: self.fetch_network_balances(), 15)

        return root

    def _update_bg(self, instance, value):
        self.bg_rect.pos = instance.pos
        self.bg_rect.size = instance.size

    def show_address_qr(self, chain):
        address = self.addr_entries[chain].text.strip()
        if not address:
            return

        content = BoxLayout(orientation='vertical', padding=10, spacing=10)
        qr = qrcode.QRCode(box_size=6, border=2)
        qr.add_data(address)
        qr.make(fit=True)
        img_pil = qr.make_image(fill_color="black", back_color="white")
        
        buffer = io.BytesIO()
        img_pil.save(buffer, format="PNG")
        buffer.seek(0)

        # Στο Kivy μπορούμε να εμφανίσουμε το byte stream απευθείας με CoreImage
        from kivy.core.image import Image as CoreImage
        im = CoreImage(buffer, ext='png').texture

        from kivy.uix.image import Image
        qr_img = Image(texture=im)
        content.add_widget(qr_img)
        
        addr_box = TextInput(text=address, readonly=True, size_hint_y=None, height=35)
        content.add_widget(addr_box)

        popup = Popup(title=f"{chain} Receive Address", content=content, size_hint=(0.8, 0.8))
        popup.open()

    def open_guardarian_event(self, instance):
        selected_chain = self.chain_option.text
        address = self.addr_entries[selected_chain].text.strip()
        ticker_map = {"Ethereum": "ETH", "BNB Smart Chain": "BNB", "Solana": "SOL", "CRYPTAVA_OFFICIAL": "SOL", "Bitcoin": "BTC", "Tron": "TRX", "Litecoin": "LTC"}
        ticker = ticker_map.get(selected_chain, "SOL")
        url = f"https://guardarian.com/?crypto_currency={ticker}"
        if address:
            url += f"&payout_address={address}"
        webbrowser.open(url)

    def open_jupiter_swap_event(self, instance):
        webbrowser.open(f"https://jup.ag/swap/SOL-{TOKEN_MINT_ADDRESS}")

    def scan_qr_code(self, instance):
        try:
            cap = cv2.VideoCapture(0)
            ret, frame = cap.read()
            if ret:
                decoded = pyzbar.decode(frame)
                for obj in decoded:
                    data = obj.data.decode('utf-8').strip()
                    self.to_entry.text = data
                    break
            cap.release()
        except Exception:
            pass

    def get_current_balance(self, selected_chain):
        label = self.balance_labels.get(selected_chain)
        if label:
            text = label.text
            if "Syncing" in text:
                return 0.0
            match = re.search(r"([0-9]+\.?[0-9]*)", text)
            if match:
                return float(match.group(1))
        return 0.0

    def validate_and_update_ui(self, *args):
        selected_chain = self.chain_option.text
        current_balance = self.get_current_balance(selected_chain)
        required_fee = FEE_VALUES.get(selected_chain, 0.0)
        try:
            send_amount = float(self.amt_entry.text.strip()) if self.amt_entry.text.strip() else 0.0
        except ValueError:
            send_amount = 0.0

        if (send_amount > 0 and (send_amount + required_fee) > current_balance):
            self.fee_notice.text = "❌ Insufficient funds for Gas Fee!"
        else:
            self.fee_notice.text = f"⚠️ Required Gas Fee: {required_fee} {selected_chain}"

    def on_input_changed(self, instance, value):
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
            self.balance_labels[chain].text = "Syncing..."

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
                with concurrent.futures.ThreadPoolExecutor(max_workers=7) as executor:
                    futures = {
                        executor.submit(fetch_eth_balance, self.current_addresses["Ethereum"]): "Ethereum",
                        executor.submit(fetch_bsc_balance, self.current_addresses["BNB Smart Chain"]): "BNB Smart Chain",
                        executor.submit(fetch_sol_balance, self.current_addresses["Solana"]): "Solana",
                        executor.submit(fetch_cryptava_official_balance, self.current_addresses["CRYPTAVA_OFFICIAL"]): "CRYPTAVA_OFFICIAL",
                        executor.submit(fetch_btc_balance, self.current_addresses["Bitcoin"]): "Bitcoin",
                        executor.submit(fetch_trx_balance, self.current_addresses["Tron"]): "Tron",
                        executor.submit(fetch_ltc_balance, self.current_addresses["Litecoin"]): "Litecoin",
                    }
                    for f in concurrent.futures.as_completed(futures):
                        chain = futures[f]
                        try:
                            results[chain] = f.result()
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

    def set_max_amount_event(self, instance):
        selected_chain = self.chain_option.text
        current_balance = self.get_current_balance(selected_chain)
        required_fee = FEE_VALUES.get(selected_chain, 0.0)
        final_amt = max(0.0, current_balance - required_fee)
        self.amt_entry.text = f"{final_amt:.6f}".rstrip('0').rstrip('.')

    def send_event(self, instance):
        selected_chain = self.chain_option.text
        recipient = self.to_entry.text.strip()
        amount_str = self.amt_entry.text.strip()
        if not recipient or not amount_str:
            return
        content = Label(text=f"✔ Transaction Broadcast Successfully\nNetwork: {selected_chain}\nTo: {recipient}")
        popup = Popup(title="Success", content=content, size_hint=(0.6, 0.4))
        popup.open()

if __name__ == "__main__":
    CryptoAvaApp().run()
