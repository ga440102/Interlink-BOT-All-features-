from aiohttp import (
    ClientResponseError,
    ClientSession,
    ClientTimeout,
    BasicAuth
)
from aiohttp_socks import ProxyConnector
from datetime import datetime
from colorama import *
import asyncio, json, sys, re, os

class Interlink:
    def __init__(self) -> None:
        self.HEADERS = {
            "Accept-Encoding": "*/*",
            "User-Agent": "okhttp/4.12.0",
            "Accept-Encoding": "gzip"
        }
        self.BASE_API = "https://prod.interlinklabs.ai/api/v1"
        self.proxies = []
        self.proxy_index = 0
        self.account_proxies = {}

    def clear_terminal(self):
        os.system('cls' if os.name == 'nt' else 'clear')

    def log(self, message):
        print(
            f"{Fore.CYAN + Style.BRIGHT}[ {datetime.now().strftime('%x %X')} ]{Style.RESET_ALL}"
            f"{Fore.WHITE + Style.BRIGHT} | {Style.RESET_ALL}{message}",
            flush=True
        )

    def log_status(self, action, status, message="", error=None):
        if status == "success":
            self.log(
                f"{Fore.CYAN+Style.BRIGHT}Action :{Style.RESET_ALL}"
                f"{Fore.WHITE+Style.BRIGHT} {action} {Style.RESET_ALL}"
                f"{Fore.CYAN+Style.BRIGHT}Status :{Style.RESET_ALL}"
                f"{Fore.GREEN+Style.BRIGHT} Success {Style.RESET_ALL}"
                f"{(Fore.MAGENTA+Style.BRIGHT + '- ' + Style.RESET_ALL + Fore.WHITE+Style.BRIGHT + message + Style.RESET_ALL) if message else ''}"
            )
        elif status == "failed":
            self.log(
                f"{Fore.CYAN+Style.BRIGHT}Action :{Style.RESET_ALL}"
                f"{Fore.WHITE+Style.BRIGHT} {action} {Style.RESET_ALL}"
                f"{Fore.CYAN+Style.BRIGHT}Status :{Style.RESET_ALL}"
                f"{Fore.RED+Style.BRIGHT} Failed {Style.RESET_ALL}"
                f"{Fore.MAGENTA+Style.BRIGHT}-{Style.RESET_ALL}"
                f"{Fore.YELLOW+Style.BRIGHT} {str(error)} {Style.RESET_ALL}"
            )
        elif status == "retry":
            self.log(
                f"{Fore.CYAN+Style.BRIGHT}Action :{Style.RESET_ALL}"
                f"{Fore.WHITE+Style.BRIGHT} {action} {Style.RESET_ALL}"
                f"{Fore.CYAN+Style.BRIGHT}Status :{Style.RESET_ALL}"
                f"{Fore.YELLOW+Style.BRIGHT} Retrying {Style.RESET_ALL}"
                f"{Fore.MAGENTA+Style.BRIGHT}-{Style.RESET_ALL}"
                f"{Fore.WHITE+Style.BRIGHT} {message} {Style.RESET_ALL}"
            )

    def welcome(self):
        print(
            f"""
        {Fore.GREEN + Style.BRIGHT}Interlink {Fore.BLUE + Style.BRIGHT}Auto BOT
            """
            f"""
        {Fore.GREEN + Style.BRIGHT}Rey? {Fore.YELLOW + Style.BRIGHT}<INI WATERMARK>
            """
        )

    def format_seconds(self, seconds):
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{int(hours):02}:{int(minutes):02}:{int(seconds):02}"
    
    def load_accounts(self):
        filename = "accounts.json"
        try:
            if not os.path.exists(filename):
                self.log(f"{Fore.RED}File {filename} Not Found.{Style.RESET_ALL}")
                return

            with open(filename, 'r') as file:
                data = json.load(file)
                if isinstance(data, list):
                    return data
                return []
        except json.JSONDecodeError:
            return []
        
    def save_accounts(self, new_accounts):
        filename = "accounts.json"
        try:
            if os.path.exists(filename) and os.path.getsize(filename) > 0:
                with open(filename, 'r') as file:
                    existing_accounts = json.load(file)
            else:
                existing_accounts = []

            account_dict = {acc["email"]: acc for acc in existing_accounts}

            for new_acc in new_accounts:
                email = new_acc["email"]
                if email in account_dict:
                    account_dict[email]["tokens"] = new_acc["tokens"]
                else:
                    account_dict[email] = new_acc

            updated_accounts = list(account_dict.values())

            with open(filename, 'w') as file:
                json.dump(updated_accounts, file, indent=4)

            self.log_status("Save Accounts", "success", "Accounts saved to file")

        except Exception as e:
            self.log_status("Save Accounts", "failed", error=e)
            return []
        
    async def load_proxies(self):
        filename = "proxy.txt"
        try:
            if not os.path.exists(filename):
                self.log(f"{Fore.RED + Style.BRIGHT}File {filename} Not Found.{Style.RESET_ALL}")
                return
            with open(filename, 'r') as f:
                self.proxies = [line.strip() for line in f.read().splitlines() if line.strip()]
            
            if not self.proxies:
                self.log(f"{Fore.RED + Style.BRIGHT}No Proxies Found.{Style.RESET_ALL}")
                return

            self.log(
                f"{Fore.GREEN + Style.BRIGHT}Proxies Total  : {Style.RESET_ALL}"
                f"{Fore.WHITE + Style.BRIGHT}{len(self.proxies)}{Style.RESET_ALL}"
            )
        
        except Exception as e:
            self.log(f"{Fore.RED + Style.BRIGHT}Failed To Load Proxies: {e}{Style.RESET_ALL}")
            self.proxies = []

    def check_proxy_schemes(self, proxies):
        schemes = ["http://", "https://", "socks4://", "socks5://"]
        if any(proxies.startswith(scheme) for scheme in schemes):
            return proxies
        return f"http://{proxies}"

    def get_next_proxy_for_account(self, account):
        if account not in self.account_proxies:
            if not self.proxies:
                return None
            proxy = self.check_proxy_schemes(self.proxies[self.proxy_index])
            self.account_proxies[account] = proxy
            self.proxy_index = (self.proxy_index + 1) % len(self.proxies)
        return self.account_proxies[account]

    def rotate_proxy_for_account(self, account):
        if not self.proxies:
            return None
        proxy = self.check_proxy_schemes(self.proxies[self.proxy_index])
        self.account_proxies[account] = proxy
        self.proxy_index = (self.proxy_index + 1) % len(self.proxies)
        return proxy
    
    def build_proxy_config(self, proxy=None):
        if not proxy:
            return None, None, None

        if proxy.startswith("socks"):
            connector = ProxyConnector.from_url(proxy)
            return connector, None, None

        elif proxy.startswith("http"):
            match = re.match(r"http://(.*?):(.*?)@(.*)", proxy)
            if match:
                username, password, host_port = match.groups()
                clean_url = f"http://{host_port}"
                auth = BasicAuth(username, password)
                return None, clean_url, auth
            else:
                return None, proxy, None

        raise Exception("Unsupported Proxy Type.")
    
    def mask_account(self, account):
        if "@" in account:
            local, domain = account.split('@', 1)
            mask_account = local[:3] + '*' * 3 + local[-3:]
            return f"{mask_account}@{domain}"

    def print_question(self):
        while True:
            try:
                print(f"{Fore.WHITE + Style.BRIGHT}1. Run With Proxy{Style.RESET_ALL}")
                print(f"{Fore.WHITE + Style.BRIGHT}2. Run Without Proxy{Style.RESET_ALL}")
                proxy_choice = int(input(f"{Fore.BLUE + Style.BRIGHT}Choose [1/2] -> {Style.RESET_ALL}").strip())

                if proxy_choice in [1, 2]:
                    proxy_type = (
                        "With" if proxy_choice == 1 else 
                        "Without"
                    )
                    print(f"{Fore.GREEN + Style.BRIGHT}Run {proxy_type} Proxy Selected.{Style.RESET_ALL}")
                    break
                else:
                    print(f"{Fore.RED + Style.BRIGHT}Please enter either 1  or 2.{Style.RESET_ALL}")
            except ValueError:
                print(f"{Fore.RED + Style.BRIGHT}Invalid input. Enter a number (1  or 2).{Style.RESET_ALL}")

        rotate_proxy = False
        if proxy_choice == 1:
            while True:
                rotate_proxy = input(f"{Fore.BLUE + Style.BRIGHT}Rotate Invalid Proxy? [y/n] -> {Style.RESET_ALL}").strip()
                if rotate_proxy in ["y", "n"]:
                    rotate_proxy = rotate_proxy == "y"
                    break
                else:
                    print(f"{Fore.RED + Style.BRIGHT}Invalid input. Enter 'y' or 'n'.{Style.RESET_ALL}")

        return proxy_choice, rotate_proxy
    
    async def check_connection(self, proxy_url=None):
        connector, proxy, proxy_auth = self.build_proxy_config(proxy_url)
        try:
            async with ClientSession(connector=connector, timeout=ClientTimeout(total=10)) as session:
                async with session.get(url="https://api.ipify.org?format=json", proxy=proxy, proxy_auth=proxy_auth) as response:
                    response.raise_for_status()
                    self.log_status("Check Connection", "success", "Connection OK")
                    return True
        except (Exception, ClientResponseError) as e:
            self.log_status("Check Connection", "failed", error=e)
            return None
        
    async def request_otp(self, email: str, passcode: str, interlink_id: str, proxy_url=None, retries=5):
        url = f"{self.BASE_API}/auth/send-otp-email-verify-login"
        data = json.dumps({"loginId":int(interlink_id), "passcode":int(passcode), "email":email})
        headers = {
            **self.HEADERS,
            "Content-Length": str(len(data)),
            "Content-Type": "application/json"
        }
        for attempt in range(retries):
            connector, proxy, proxy_auth = self.build_proxy_config(proxy_url)
            try:
                async with ClientSession(connector=connector, timeout=ClientTimeout(total=60)) as session:
                    async with session.post(url=url, headers=headers, data=data, proxy=proxy, proxy_auth=proxy_auth, ssl=False) as response:
                        response.raise_for_status()
                        result = await response.json()
                        self.log_status("Request OTP", "success", "OTP request sent")
                        return result
            except (Exception, ClientResponseError) as e:
                if attempt < retries - 1:
                    self.log_status("Request OTP", "retry", f"Attempt {attempt + 1}/{retries}")
                    await asyncio.sleep(5)
                    continue
                else:
                    self.log_status("Request OTP", "failed", error=e)
                    return None
        
    async def verify_otp(self, interlink_id: str, otp_code: str, proxy_url=None, retries=5):
        url = f"{self.BASE_API}/auth/check-otp-email-verify-login"
        data = json.dumps({"loginId":int(interlink_id), "otp":int(otp_code)})
        headers = {
            **self.HEADERS,
            "Content-Length": str(len(data)),
            "Content-Type": "application/json"
        }
        for attempt in range(retries):
            connector, proxy, proxy_auth = self.build_proxy_config(proxy_url)
            try:
                async with ClientSession(connector=connector, timeout=ClientTimeout(total=60)) as session:
                    async with session.post(url=url, headers=headers, data=data, proxy=proxy, proxy_auth=proxy_auth) as response:
                        response.raise_for_status()
                        result = await response.json()
                        self.log_status("Verify OTP", "success", "OTP verified successfully")
                        return result
            except (Exception, ClientResponseError) as e:
                if attempt < retries - 1:
                    self.log_status("Verify OTP", "retry", f"Attempt {attempt + 1}/{retries}")
                    await asyncio.sleep(5)
                    continue
                else:
                    self.log_status("Verify OTP", "failed", error=e)
                    return None
        
    async def process_check_connection(self, email: str, use_proxy: bool, rotate_proxy: bool):
        while True:
            proxy = self.get_next_proxy_for_account(email) if use_proxy else None
            self.log(
                f"{Fore.CYAN+Style.BRIGHT}Proxy  :{Style.RESET_ALL}"
                f"{Fore.WHITE+Style.BRIGHT} {proxy if proxy else 'No Proxy'} {Style.RESET_ALL}"
            )

            is_valid = await self.check_connection(proxy)
            if is_valid: return True
            
            if rotate_proxy:
                proxy = self.rotate_proxy_for_account(email)
                await asyncio.sleep(1)
                continue

            return False

    async def process_accounts(self, email: str, passcode: str, interlink_id: str, use_proxy: bool, rotate_proxy: bool):
        is_valid = await self.process_check_connection(email, use_proxy, rotate_proxy)
        if not is_valid:
            self.log_status("Process Account", "failed", error="Connection check failed")
            return

        proxy = self.get_next_proxy_for_account(email) if use_proxy else None

        request = await self.request_otp(email, passcode, interlink_id, proxy)
        if not request: return

        timestamp = (
            f"{Fore.CYAN + Style.BRIGHT}[ {datetime.now().strftime('%x %X')} ]{Style.RESET_ALL}"
            f"{Fore.WHITE + Style.BRIGHT} | {Style.RESET_ALL}"
            f"{Fore.CYAN + Style.BRIGHT}Action :{Style.RESET_ALL}"
        )
        otp_code = input(f"{timestamp}{Fore.BLUE + Style.BRIGHT} Enter OTP Code -> {Style.RESET_ALL}")

        verify = await self.verify_otp(interlink_id, otp_code, proxy)
        if not verify: return

        access_token = verify.get("data", {}).get("accessToken")
        refresh_token = verify.get("data", {}).get("refreshToken")

        if not access_token or not refresh_token:
            self.log_status("Process Account", "failed", error="No token received from authentication")
            return

        account_data = [{
            "email": email,
            "passcode": passcode,
            "interlinkId": interlink_id,
            "tokens": {
                "accessToken": access_token,
                "refreshToken": refresh_token
            }
        }]
        self.save_accounts(account_data)
        self.log_status("Process Account", "success", f"Account {self.mask_account(email)} processed successfully")
    
    async def main(self):
        try:
            accounts = self.load_accounts()
            if not accounts:
                print(f"{Fore.YELLOW + Style.BRIGHT}No Accounts Loaded{Style.RESET_ALL}")
                return
            
            proxy_choice, rotate_proxy = self.print_question()

            self.clear_terminal()
            self.welcome()

            use_proxy = True if proxy_choice == 1 else False
            if use_proxy:
                await self.load_proxies()

            separator = "=" * 27
            for idx, account in enumerate(accounts, start=1):
                email = account.get("email")
                passcode = account.get("passcode")
                interlink_id = account.get("interlinkId")

                if not "@" in email or not passcode or not interlink_id:
                    self.log_status("Account Validation", "failed", error="Invalid account format")
                    continue

                self.log(
                    f"{Fore.CYAN + Style.BRIGHT}{separator}[{Style.RESET_ALL}"
                    f"{Fore.WHITE + Style.BRIGHT} {idx} {Style.RESET_ALL}"
                    f"{Fore.CYAN + Style.BRIGHT}Of{Style.RESET_ALL}"
                    f"{Fore.WHITE + Style.BRIGHT} {len(accounts)} {Style.RESET_ALL}"
                    f"{Fore.CYAN + Style.BRIGHT}]{separator}{Style.RESET_ALL}"
                )

                self.log(
                    f"{Fore.CYAN+Style.BRIGHT}Email  :{Style.RESET_ALL}"
                    f"{Fore.WHITE+Style.BRIGHT} {self.mask_account(email)} {Style.RESET_ALL}"
                )

                await self.process_accounts(email, passcode, interlink_id, use_proxy, rotate_proxy)
                await asyncio.sleep(3)

        except Exception as e:
            self.log_status("Main Process", "failed", error=e)
            raise e

if __name__ == "__main__":
    try:
        bot = Interlink()
        asyncio.run(bot.main())
    except KeyboardInterrupt:
        print(
            f"{Fore.CYAN + Style.BRIGHT}[ {datetime.now().strftime('%x %X')} ]{Style.RESET_ALL}"
            f"{Fore.WHITE + Style.BRIGHT} | {Style.RESET_ALL}"
            f"{Fore.RED + Style.BRIGHT}[ EXIT ] Interlink - BOT{Style.RESET_ALL}                                      ",                                       
        )
        sys.exit(1)