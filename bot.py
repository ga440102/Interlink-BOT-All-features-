from aiohttp import (
    ClientResponseError,
    ClientSession,
    ClientTimeout,
    BasicAuth
)
from aiohttp_socks import ProxyConnector
from base64 import urlsafe_b64decode
from datetime import datetime, timezone, timedelta
from colorama import *
import asyncio, random, time, json, sys, re, os

class Interlink:
    def __init__(self) -> None:
        self.BASE_API = "https://prod.interlinklabs.ai"
        self.VERSION = "5.0.0"

        self.USE_PROXY = False
        self.ROTATE_PROXY = False

        self.proxies = []
        self.proxy_index = 0
        self.account_proxies = {}
        self.accounts = {}

        # ===== 功能开关 =====
        self.ENABLE_GROUP_MINING  = True   # 安全组挖矿签到开关
        self.ENABLE_RECOVERY      = True   # ITLG恢复开关

        # ===== 安全组挖矿配置 =====
        # 已通过APK反编译+API探测确认的端点
        self.GROUP_MINING_LIST      = "/api/v1/group-mining/get-list-group-mining"     # 获取账号所在群组列表
        self.GROUP_MINING_DETAIL    = "/api/v1/group-mining/get-detail-group-mining"   # 获取群组详情
        self.GROUP_MINING_CLAIM     = "/api/v1/group-mining/claim-group-mining"        # 领取挖矿奖励
        self.GROUP_MINING_CREATE    = "/api/v1/group-mining/create-group"              # 创建群组
        self.GROUP_MINING_LEAVE     = "/api/v1/group-mining/leave-group"              # 离开群组
        self.GROUP_MINING_INVITE    = "/api/v1/group-mining/invite-group"             # 邀请加入群组
        self.GROUP_MINING_ACCEPT    = "/api/v1/group-mining/accept-invite-group"      # 接受邀请

        # 缓存：每个账号的groupId，避免每次都查
        self.account_groups = {}  # {email: groupId}

        # ===== ITLG恢复配置 =====
        self.RECOVERY_STATUS = "/api/v1/token/get-token"        # 恢复状态：直接用token信息接口，查 itlgRecoverable 字段
        self.BURN_HISTORY    = "/api/v1/burn-histories/my"      # Burn历史：获取可恢复的transactionId列表
        self.RECOVERY_CLAIM  = "/api/v1/recovery/claim"         # 领取恢复接口

    def clear_terminal(self):
        os.system('cls' if os.name == 'nt' else 'clear')

    def log(self, message):
        print(
            f"{Fore.CYAN + Style.BRIGHT}[ {datetime.now().strftime('%x %X')} ]{Style.RESET_ALL}"
            f"{Fore.WHITE + Style.BRIGHT} | {Style.RESET_ALL}{message}",
            flush=True
        )

    def welcome(self):
        print(
            f"""
        {Fore.GREEN + Style.BRIGHT}Interlink Labs {Fore.BLUE + Style.BRIGHT}Auto BOT
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
                    account_dict[email].update(new_acc)
                else:
                    account_dict[email] = new_acc

            updated_accounts = list(account_dict.values())

            with open(filename, 'w') as file:
                json.dump(updated_accounts, file, indent=4)

        except Exception as e:
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
    
    def display_proxy(self, proxy_url=None):
        if not proxy_url: return "No Proxy"

        proxy_url = re.sub(r"^(http|https|socks4|socks5)://", "", proxy_url)

        if "@" in proxy_url:
            proxy_url = proxy_url.split("@", 1)[1]

        return proxy_url
    
    def decode_token(self, email: str):
        try:
            access_token = self.accounts[email]["accessToken"]
            header, payload, signature = access_token.split(".")
            decoded_payload = urlsafe_b64decode(payload + "==").decode("utf-8")
            parsed_payload = json.loads(decoded_payload)
            exp_time = parsed_payload["exp"]
            
            return exp_time
        except Exception as e:
            return None
    
    def mask_account(self, account):
        if "@" in account:
            local, domain = account.split('@', 1)
            mask_account = local[:3] + '*' * 3 + local[-3:]
            return f"{mask_account}@{domain}"
        
    def generate_device_id(self):
        return str(os.urandom(8).hex())
    
    def generate_timestamp(self):
        return str(int(time.time()) * 1000)
        
    def initialize_headers(self, email: str):
        headers = {
            "Host": "prod.interlinklabs.ai",
            "Accept": "*/*",
            "Version": self.VERSION,
            "X-Platform": "android",
            "X-Date": self.generate_timestamp(),
            "X-Unique-Id": self.accounts[email]["deviceId"],
            "X-Model": "25053PC47G",
            "X-Brand": "POCO",
            "X-System-Name": "Android",
            "X-Device-Id": self.accounts[email]["deviceId"],
            "X-Bundle-Id": "org.ai.interlinklabs.interlinkId",
            "Accept-Encoding": "gzip, deflate",
            "User-Agent": "okhttp/4.12.0"
        }

        return headers.copy()

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
                    self.USE_PROXY = True if proxy_choice == 1 else False
                    break
                else:
                    print(f"{Fore.RED + Style.BRIGHT}Please enter either 1  or 2.{Style.RESET_ALL}")
            except ValueError:
                print(f"{Fore.RED + Style.BRIGHT}Invalid input. Enter a number (1  or 2).{Style.RESET_ALL}")

        if self.USE_PROXY:
            while True:
                rotate_proxy = input(f"{Fore.BLUE + Style.BRIGHT}Rotate Invalid Proxy? [y/n] -> {Style.RESET_ALL}").strip()
                if rotate_proxy in ["y", "n"]:
                    self.ROTATE_PROXY = True if rotate_proxy == "y" else False
                    break
                else:
                    print(f"{Fore.RED + Style.BRIGHT}Invalid input. Enter 'y' or 'n'.{Style.RESET_ALL}")

    async def ensure_ok(self, response):
        if response.status >= 400:
            raise Exception(f"HTTP: {response.status}:{await response.text()}")

    async def check_connection(self, email: str, proxy_url=None):
        url = "https://api.ipify.org?format=json"
        
        connector, proxy, proxy_auth = self.build_proxy_config(proxy_url)
        try:
            async with ClientSession(connector=connector, timeout=ClientTimeout(total=15)) as session:
                async with session.get(url=url, proxy=proxy, proxy_auth=proxy_auth) as response:
                    await self.ensure_ok(response)
                    return True
        except (Exception, ClientResponseError) as e:
            self.log(
                f"{Fore.CYAN+Style.BRIGHT}Status :{Style.RESET_ALL}"
                f"{Fore.RED+Style.BRIGHT} Connection Not 200 OK {Style.RESET_ALL}"
                f"{Fore.MAGENTA+Style.BRIGHT}-{Style.RESET_ALL}"
                f"{Fore.YELLOW+Style.BRIGHT} {str(e)} {Style.RESET_ALL}"
            )
            return None
    
    async def refresh_token(self, email: str, proxy_url=None, retries=5):
        url = f"{self.BASE_API}/api/v1/auth/token"
        
        for attempt in range(retries):
            connector, proxy, proxy_auth = self.build_proxy_config(proxy_url)
            try:
                headers = self.initialize_headers(email)
                headers["Authorization"] = f"Bearer {self.accounts[email]['accessToken']}"
                headers["Content-Type"] = "application/json"
                payload = {
                    "refreshToken": self.accounts[email]["refreshToken"]
                }

                async with ClientSession(connector=connector, timeout=ClientTimeout(total=60)) as session:
                    async with session.post(url=url, headers=headers, json=payload, proxy=proxy, proxy_auth=proxy_auth) as response:
                        await self.ensure_ok(response)
                        return await response.json()
            except (Exception, ClientResponseError) as e:
                if attempt < retries - 1:
                    await asyncio.sleep(5)
                    continue
                self.log(
                    f"{Fore.CYAN+Style.BRIGHT}Status :{Style.RESET_ALL}"
                    f"{Fore.RED+Style.BRIGHT} Failed to Refreshing Tokens {Style.RESET_ALL}"
                    f"{Fore.MAGENTA+Style.BRIGHT}-{Style.RESET_ALL}"
                    f"{Fore.YELLOW+Style.BRIGHT} {str(e)} {Style.RESET_ALL}"
                )

        return None
    
    async def token_balance(self, email: str, proxy_url=None, retries=5):
        url = f"{self.BASE_API}/api/v1/token/get-token"
        
        for attempt in range(retries):
            connector, proxy, proxy_auth = self.build_proxy_config(proxy_url)
            try:
                headers = self.initialize_headers(email)
                headers["Authorization"] = f"Bearer {self.accounts[email]['accessToken']}"

                async with ClientSession(connector=connector, timeout=ClientTimeout(total=60)) as session:
                    async with session.get(url=url, headers=headers, proxy=proxy, proxy_auth=proxy_auth) as response:
                        await self.ensure_ok(response)
                        return await response.json()
            except (Exception, ClientResponseError) as e:
                if attempt < retries - 1:
                    await asyncio.sleep(5)
                    continue
                self.log(
                    f"{Fore.CYAN+Style.BRIGHT}Balance:{Style.RESET_ALL}"
                    f"{Fore.RED+Style.BRIGHT} Failed to Fetch Token Earned {Style.RESET_ALL}"
                    f"{Fore.MAGENTA+Style.BRIGHT}-{Style.RESET_ALL}"
                    f"{Fore.YELLOW+Style.BRIGHT} {str(e)} {Style.RESET_ALL}"
                )

        return None
            
    async def claimable_check(self, email: str, proxy_url=None, retries=5):
        url = f"{self.BASE_API}/api/v1/token/check-is-claimable"
        
        for attempt in range(retries):
            connector, proxy, proxy_auth = self.build_proxy_config(proxy_url)
            try:
                headers = self.initialize_headers(email)
                headers["Authorization"] = f"Bearer {self.accounts[email]['accessToken']}"

                async with ClientSession(connector=connector, timeout=ClientTimeout(total=60)) as session:
                    async with session.get(url=url, headers=headers, proxy=proxy, proxy_auth=proxy_auth) as response:
                        await self.ensure_ok(response)
                        return await response.json()
            except (Exception, ClientResponseError) as e:
                if attempt < retries - 1:
                    await asyncio.sleep(5)
                    continue
                self.log(
                    f"{Fore.CYAN+Style.BRIGHT}Mining :{Style.RESET_ALL}"
                    f"{Fore.RED+Style.BRIGHT} Failed to Fetch Status {Style.RESET_ALL}"
                    f"{Fore.MAGENTA+Style.BRIGHT}-{Style.RESET_ALL}"
                    f"{Fore.YELLOW+Style.BRIGHT} {str(e)} {Style.RESET_ALL}"
                )

        return None
            
    async def claim_airdrop(self, email: str, proxy_url=None, retries=1):
        url = f"{self.BASE_API}/api/v1/token/claim-airdrop"

        for attempt in range(retries):
            connector, proxy, proxy_auth = self.build_proxy_config(proxy_url)
            try:
                headers = self.initialize_headers(email)
                headers["Authorization"] = f"Bearer {self.accounts[email]['accessToken']}"
                headers["Content-Type"] = "application/json"

                async with ClientSession(connector=connector, timeout=ClientTimeout(total=60)) as session:
                    async with session.post(url=url, headers=headers, json={}, proxy=proxy, proxy_auth=proxy_auth) as response:
                        await self.ensure_ok(response)
                        return await response.json()
            except (Exception, ClientResponseError) as e:
                if attempt < retries - 1:
                    await asyncio.sleep(5)
                    continue
                self.log(
                    f"{Fore.CYAN+Style.BRIGHT}Mining :{Style.RESET_ALL}"
                    f"{Fore.RED+Style.BRIGHT} Not Claimed {Style.RESET_ALL}"
                    f"{Fore.MAGENTA+Style.BRIGHT}-{Style.RESET_ALL}"
                    f"{Fore.YELLOW+Style.BRIGHT} {str(e)} {Style.RESET_ALL}"
                )

        return None

    # ========== 安全组挖矿（Security Group / Group Mining） ==========
    
    async def group_mining_get_list(self, email: str, proxy_url=None, retries=3):
        """获取账号所在的安全组列表（自动获取groupId）"""
        url = f"{self.BASE_API}{self.GROUP_MINING_LIST}"

        for attempt in range(retries):
            connector, proxy, proxy_auth = self.build_proxy_config(proxy_url)
            try:
                headers = self.initialize_headers(email)
                headers["Authorization"] = f"Bearer {self.accounts[email]['accessToken']}"
                headers["Content-Type"] = "application/json"

                async with ClientSession(connector=connector, timeout=ClientTimeout(total=60)) as session:
                    async with session.post(url=url, headers=headers, json={}, proxy=proxy, proxy_auth=proxy_auth) as response:
                        status = response.status
                        data = await response.json()
                        if status == 200:
                            return data
                        # 非200也返回，让调用者处理
                        return data
            except (Exception, ClientResponseError) as e:
                if attempt < retries - 1:
                    await asyncio.sleep(3)
                    continue
                self.log(
                    f"{Fore.CYAN+Style.BRIGHT}GrpMine:{Style.RESET_ALL}"
                    f"{Fore.RED+Style.BRIGHT} Failed to Get Group List {Style.RESET_ALL}"
                    f"{Fore.MAGENTA+Style.BRIGHT}-{Style.RESET_ALL}"
                    f"{Fore.YELLOW+Style.BRIGHT} {str(e)} {Style.RESET_ALL}"
                )

        return None

    async def group_mining_claim(self, email: str, group_id: str, proxy_url=None, retries=3):
        """领取安全组挖矿奖励"""
        url = f"{self.BASE_API}{self.GROUP_MINING_CLAIM}"

        for attempt in range(retries):
            connector, proxy, proxy_auth = self.build_proxy_config(proxy_url)
            try:
                headers = self.initialize_headers(email)
                headers["Authorization"] = f"Bearer {self.accounts[email]['accessToken']}"
                headers["Content-Type"] = "application/json"

                async with ClientSession(connector=connector, timeout=ClientTimeout(total=60)) as session:
                    async with session.post(
                        url=url,
                        headers=headers,
                        json={"groupId": group_id},
                        proxy=proxy,
                        proxy_auth=proxy_auth
                    ) as response:
                        status = response.status
                        data = await response.json()
                        
                        if status == 200:
                            return data
                        
                        # 400 可能是已领取
                        if status == 400:
                            msg = data.get("message", {})
                            if isinstance(msg, dict):
                                msg = msg.get("message", "")
                            if "ALREADY_CLAIMED" in str(msg).upper():
                                return {"statusCode": 200, "already_claimed": True, "data": {}}
                        
                        if attempt < retries - 1:
                            await asyncio.sleep(3)
                            continue
                        return data
            except (Exception, ClientResponseError) as e:
                if attempt < retries - 1:
                    await asyncio.sleep(3)
                    continue
                self.log(
                    f"{Fore.CYAN+Style.BRIGHT}GrpMine:{Style.RESET_ALL}"
                    f"{Fore.RED+Style.BRIGHT} Claim Failed {Style.RESET_ALL}"
                    f"{Fore.MAGENTA+Style.BRIGHT}-{Style.RESET_ALL}"
                    f"{Fore.YELLOW+Style.BRIGHT} {str(e)} {Style.RESET_ALL}"
                )

        return None

    async def process_group_mining(self, email: str, proxy_url=None):
        """安全组挖矿完整流程：获取群组 → 只领取可领取的群奖励
        
        一个账号可能在多个群里，但只能领取 isClaimGroupMining=true 的群的奖励。
        API 通过 isClaimGroupMining 字段标记哪个群是"挖矿群"（可领取的）。
        跟随主循环，每次都查API判断状态（不管几点启动都能正确处理）。
        """
        self.log(
            f"{Fore.CYAN+Style.BRIGHT}GrpMine:{Style.RESET_ALL}"
            f"{Fore.WHITE+Style.BRIGHT} Fetching Group Mining Info... {Style.RESET_ALL}"
        )

        # Step 1: 获取群组列表
        result = await self.group_mining_get_list(email, proxy_url)
        if not result:
            self.log(
                f"{Fore.CYAN+Style.BRIGHT}GrpMine:{Style.RESET_ALL}"
                f"{Fore.RED+Style.BRIGHT} API returned no result {Style.RESET_ALL}"
            )
            return

        # 调试：打印API返回的关键字段
        status_code = result.get("statusCode", result.get("status", "?"))
        self.log(
            f"{Fore.CYAN+Style.BRIGHT}GrpMine:{Style.RESET_ALL}"
            f"{Fore.WHITE+Style.BRIGHT} API statusCode: {status_code} {Style.RESET_ALL}"
        )

        data = result.get("data", {})
        groups = data.get("groups", [])
        is_claimable = data.get("isClaimable", False)
        has_claimed_today = data.get("requesterHasClaimedToday", False)

        if not groups:
            self.log(
                f"{Fore.CYAN+Style.BRIGHT}GrpMine:{Style.RESET_ALL}"
                f"{Fore.YELLOW+Style.BRIGHT} Not in any Security Group yet {Style.RESET_ALL}"
            )
            return

        # 显示所有群组信息，标注哪个是可领取的挖矿群
        claim_group = None  # 可领取奖励的群
        for group in groups:
            group_id = group.get("groupId", "?")
            status = group.get("statusLabel", "?")
            can_claim = group.get("canClaim", False)
            is_secure = group.get("secure", False)
            is_mining = group.get("isClaimGroupMining", False)  # 是否是挖矿群（可领取奖励的群）
            total_reward = group.get("totalReward", 0)
            counts = group.get("counts", {})
            total_members = counts.get("totalMembers", 0)
            claimed_yesterday = counts.get("claimedYesterday", 0)

            mining_tag = f"{Fore.GREEN+Style.BRIGHT}[Mining]{Style.RESET_ALL}" if is_mining else f"{Fore.YELLOW+Style.BRIGHT}[View]{Style.RESET_ALL}"

            self.log(
                f"{Fore.CYAN+Style.BRIGHT}GrpMine:{Style.RESET_ALL}"
                f" {mining_tag}"
                f"{Fore.BLUE+Style.BRIGHT} Group: {Style.RESET_ALL}"
                f"{Fore.WHITE+Style.BRIGHT}{group_id} {Style.RESET_ALL}"
                f"{Fore.MAGENTA+Style.BRIGHT}-{Style.RESET_ALL}"
                f"{Fore.BLUE+Style.BRIGHT} Members: {Style.RESET_ALL}"
                f"{Fore.WHITE+Style.BRIGHT}{total_members} {Style.RESET_ALL}"
                f"{Fore.MAGENTA+Style.BRIGHT}-{Style.RESET_ALL}"
                f"{Fore.BLUE+Style.BRIGHT} Secure: {Style.RESET_ALL}"
                f"{Fore.GREEN+Style.BRIGHT}{'Yes' if is_secure else 'No'}{Style.RESET_ALL}"
                f"{Fore.MAGENTA+Style.BRIGHT}-{Style.RESET_ALL}"
                f"{Fore.BLUE+Style.BRIGHT} Reward: {Style.RESET_ALL}"
                f"{Fore.WHITE+Style.BRIGHT}{total_reward} ITLG{Style.RESET_ALL}"
            )

            # 记录可领取的挖矿群（isClaimGroupMining=true 的群）
            if is_mining and claim_group is None:
                claim_group = group

        # 如果没有标记 isClaimGroupMining 的群，fallback 到第一个群
        if claim_group is None and groups:
            claim_group = groups[0]
            self.log(
                f"{Fore.CYAN+Style.BRIGHT}GrpMine:{Style.RESET_ALL}"
                f"{Fore.YELLOW+Style.BRIGHT} No isClaimGroupMining group found, using first group {Style.RESET_ALL}"
            )

        # 缓存groupId
        if claim_group:
            self.account_groups[email] = claim_group.get("groupId", "?")

        # Step 2: 领取奖励（只领挖矿群的）
        if has_claimed_today:
            self.log(
                f"{Fore.CYAN+Style.BRIGHT}GrpMine:{Style.RESET_ALL}"
                f"{Fore.YELLOW+Style.BRIGHT} Already Claimed Today {Style.RESET_ALL}"
            )
            # 显示下次可领取时间
            next_ts = data.get("nextTimeClaim", 0)
            if next_ts:
                next_time = datetime.fromtimestamp(next_ts / 1000).strftime('%x %X')
                self.log(
                    f"{Fore.CYAN+Style.BRIGHT}GrpMine:{Style.RESET_ALL}"
                    f"{Fore.WHITE+Style.BRIGHT} Next Claim at: {next_time} {Style.RESET_ALL}"
                )
            return

        if not is_claimable:
            self.log(
                f"{Fore.CYAN+Style.BRIGHT}GrpMine:{Style.RESET_ALL}"
                f"{Fore.YELLOW+Style.BRIGHT} Not Claimable Yet {Style.RESET_ALL}"
            )
            return

        if not claim_group:
            return

        # 只领取挖矿群的奖励
        group_id = claim_group.get("groupId")
        can_claim = claim_group.get("canClaim", False)

        if not can_claim and not is_claimable:
            self.log(
                f"{Fore.CYAN+Style.BRIGHT}GrpMine:{Style.RESET_ALL}"
                f"{Fore.YELLOW+Style.BRIGHT} Group {group_id} not claimable yet {Style.RESET_ALL}"
            )
            return

        self.log(
            f"{Fore.CYAN+Style.BRIGHT}GrpMine:{Style.RESET_ALL}"
            f"{Fore.WHITE+Style.BRIGHT} Claiming Group {group_id}... {Style.RESET_ALL}"
        )

        claim = await self.group_mining_claim(email, group_id, proxy_url)
        if claim:
            if claim.get("already_claimed"):
                self.log(
                    f"{Fore.CYAN+Style.BRIGHT}GrpMine:{Style.RESET_ALL}"
                    f"{Fore.YELLOW+Style.BRIGHT} Already Claimed Today {Style.RESET_ALL}"
                )
            else:
                claim_data = claim.get("data", {})
                reward = claim_data.get("totalReward", "N/A")
                next_ts = claim_data.get("nextTimeClaim", 0)

                self.log(
                    f"{Fore.CYAN+Style.BRIGHT}GrpMine:{Style.RESET_ALL}"
                    f"{Fore.GREEN+Style.BRIGHT} Claimed Successfully! {Style.RESET_ALL}"
                    f"{Fore.MAGENTA+Style.BRIGHT}-{Style.RESET_ALL}"
                    f"{Fore.CYAN+Style.BRIGHT} Reward: {Style.RESET_ALL}"
                    f"{Fore.WHITE+Style.BRIGHT}{reward} ITLG{Style.RESET_ALL}"
                )

                if next_ts:
                    next_time = datetime.fromtimestamp(next_ts / 1000).strftime('%x %X')
                    self.log(
                        f"{Fore.CYAN+Style.BRIGHT}GrpMine:{Style.RESET_ALL}"
                        f"{Fore.WHITE+Style.BRIGHT} Next Claim at: {next_time} {Style.RESET_ALL}"
                    )
        else:
            self.log(
                f"{Fore.CYAN+Style.BRIGHT}GrpMine:{Style.RESET_ALL}"
                f"{Fore.RED+Style.BRIGHT} Claim Failed, Will Retry Next Loop {Style.RESET_ALL}"
            )

    # ========== ITLG 恢复 ==========

    async def recovery_status(self, email: str, proxy_url=None, retries=5):
        """查询ITLG恢复状态 - 获取token信息和burn历史中的可恢复记录"""
        token_url = f"{self.BASE_API}{self.RECOVERY_STATUS}"
        burn_url  = f"{self.BASE_API}{self.BURN_HISTORY}"

        for attempt in range(retries):
            connector, proxy, proxy_auth = self.build_proxy_config(proxy_url)
            try:
                headers = self.initialize_headers(email)
                headers["Authorization"] = f"Bearer {self.accounts[email]['accessToken']}"

                async with ClientSession(connector=connector, timeout=ClientTimeout(total=60)) as session:
                    # 同时请求 token信息和burn历史
                    t_resp, b_resp = await asyncio.gather(
                        session.get(url=token_url, headers=headers, proxy=proxy, proxy_auth=proxy_auth),
                        session.get(url=burn_url,  headers=headers, proxy=proxy, proxy_auth=proxy_auth),
                    )

                    await self.ensure_ok(t_resp)
                    token_data = await t_resp.json()

                    b_status = b_resp.status
                    burn_data = await b_resp.json() if b_status == 200 else {"data": []}

                # 合并数据
                t_data = token_data.get("data", token_data)
                burn_records = burn_data.get("data", {}).get("data", burn_data.get("data", []))

                # 找可恢复且未恢复的记录
                recoverable_records = [
                    r for r in burn_records
                    if r.get("isRecoverable") and not r.get("isRecovered")
                ]

                return {
                    "data": {
                        **t_data,
                        "recoverable_records": recoverable_records,
                    }
                }

            except (Exception, ClientResponseError) as e:
                if attempt < retries - 1:
                    await asyncio.sleep(5)
                    continue
                self.log(
                    f"{Fore.CYAN+Style.BRIGHT}Recover:{Style.RESET_ALL}"
                    f"{Fore.RED+Style.BRIGHT} Failed to Fetch Recovery Status {Style.RESET_ALL}"
                    f"{Fore.MAGENTA+Style.BRIGHT}-{Style.RESET_ALL}"
                    f"{Fore.YELLOW+Style.BRIGHT} {str(e)} {Style.RESET_ALL}"
                )

        return None

    async def claim_recovery(self, email: str, transaction_id: str, proxy_url=None, retries=3):
        """执行ITLG恢复领取 - 用正确的transactionId参数"""
        url = f"{self.BASE_API}{self.RECOVERY_CLAIM}"

        for attempt in range(retries):
            connector, proxy, proxy_auth = self.build_proxy_config(proxy_url)
            try:
                headers = self.initialize_headers(email)
                headers["Authorization"] = f"Bearer {self.accounts[email]['accessToken']}"
                headers["Content-Type"] = "application/json"

                async with ClientSession(connector=connector, timeout=ClientTimeout(total=60)) as session:
                    async with session.post(
                        url=url,
                        headers=headers,
                        json={"transactionId": transaction_id},
                        proxy=proxy,
                        proxy_auth=proxy_auth
                    ) as response:
                        status = response.status
                        data = await response.json()

                        # 201 = 已排队处理（成功），200 = 已领取过了
                        if status in (200, 201):
                            return data

                        # 其他错误码 → 重试
                        msg = data.get("message", "")
                        if attempt < retries - 1:
                            await asyncio.sleep(3)
                            continue
                        self.log(
                            f"{Fore.CYAN+Style.BRIGHT}Recover:{Style.RESET_ALL}"
                            f"{Fore.RED+Style.BRIGHT} Recovery Failed [{status}] {Style.RESET_ALL}"
                            f"{Fore.YELLOW+Style.BRIGHT} {msg} {Style.RESET_ALL}"
                        )
                        return data

            except (Exception, ClientResponseError) as e:
                if attempt < retries - 1:
                    await asyncio.sleep(5)
                    continue
                self.log(
                    f"{Fore.CYAN+Style.BRIGHT}Recover:{Style.RESET_ALL}"
                    f"{Fore.RED+Style.BRIGHT} Recovery Claim Failed {Style.RESET_ALL}"
                    f"{Fore.MAGENTA+Style.BRIGHT}-{Style.RESET_ALL}"
                    f"{Fore.YELLOW+Style.BRIGHT} {str(e)} {Style.RESET_ALL}"
                )

        return None

    async def process_recovery(self, email: str, proxy_url=None):
        """ITLG恢复完整流程"""
        self.log(
            f"{Fore.CYAN+Style.BRIGHT}Recover:{Style.RESET_ALL}"
            f"{Fore.WHITE+Style.BRIGHT} Checking Recovery Status... {Style.RESET_ALL}"
        )

        status = await self.recovery_status(email, proxy_url)
        if not status:
            return

        data = status.get("data", {})

        recoverable = data.get("itlgRecoverable", 0)
        burned_cycles = data.get("burnedCycles", "N/A")
        burning_streak = data.get("burningStreak", "N/A")
        recoverable_records = data.get("recoverable_records", [])

        self.log(
            f"{Fore.CYAN+Style.BRIGHT}Recover:{Style.RESET_ALL}"
            f"{Fore.BLUE+Style.BRIGHT} Burned: {Style.RESET_ALL}"
            f"{Fore.WHITE+Style.BRIGHT}{burned_cycles} cycles {Style.RESET_ALL}"
            f"{Fore.MAGENTA+Style.BRIGHT}-{Style.RESET_ALL}"
            f"{Fore.BLUE+Style.BRIGHT} Streak: {Style.RESET_ALL}"
            f"{Fore.WHITE+Style.BRIGHT}{burning_streak} {Style.RESET_ALL}"
            f"{Fore.MAGENTA+Style.BRIGHT}-{Style.RESET_ALL}"
            f"{Fore.BLUE+Style.BRIGHT} Recoverable: {Style.RESET_ALL}"
            f"{Fore.WHITE+Style.BRIGHT}{recoverable} ITLG{Style.RESET_ALL}"
        )

        if not recoverable_records:
            self.log(
                f"{Fore.CYAN+Style.BRIGHT}Recover:{Style.RESET_ALL}"
                f"{Fore.YELLOW+Style.BRIGHT} No Recoverable Records Found {Style.RESET_ALL}"
            )
            return

        # 遍历所有可恢复记录，逐个领取
        for record in recoverable_records:
            tx_id = record.get("transactionId")
            amt   = record.get("amount", 0)

            self.log(
                f"{Fore.CYAN+Style.BRIGHT}Recover:{Style.RESET_ALL}"
                f"{Fore.WHITE+Style.BRIGHT} Claiming {amt} ITLG "
                f"({tx_id})... {Style.RESET_ALL}"
            )

            claim = await self.claim_recovery(email, tx_id, proxy_url)
            if claim:
                claimed_amt = claim.get("data", {}).get("amount", amt)
                job_id = claim.get("data", {}).get("jobId", "N/A")
                self.log(
                    f"{Fore.CYAN+Style.BRIGHT}Recover:{Style.RESET_ALL}"
                    f"{Fore.GREEN+Style.BRIGHT} Recovery Queued Successfully! {Style.RESET_ALL}"
                    f"{Fore.MAGENTA+Style.BRIGHT}-{Style.RESET_ALL}"
                    f"{Fore.CYAN+Style.BRIGHT} Amount: {Style.RESET_ALL}"
                    f"{Fore.WHITE+Style.BRIGHT}{claimed_amt} ITLG {Style.RESET_ALL}"
                    f"{Fore.MAGENTA+Style.BRIGHT}-{Style.RESET_ALL}"
                    f"{Fore.CYAN+Style.BRIGHT} JobID: {Style.RESET_ALL}"
                    f"{Fore.WHITE+Style.BRIGHT}{job_id} {Style.RESET_ALL}"
                )
            else:
                self.log(
                    f"{Fore.CYAN+Style.BRIGHT}Recover:{Style.RESET_ALL}"
                    f"{Fore.RED+Style.BRIGHT} Recovery Failed for {tx_id} {Style.RESET_ALL}"
                )

    # ========== 主流程 ==========

    async def process_check_connection(self, email: str, proxy_url=None):
        while True:
            if self.USE_PROXY:
                proxy_url = self.get_next_proxy_for_account(email)

            is_valid = await self.check_connection(proxy_url)
            if is_valid: return True
            
            if self.ROTATE_PROXY:
                proxy_url = self.rotate_proxy_for_account(email)
                await asyncio.sleep(1)
                continue

            return False
            
    async def process_check_tokens(self, email: str, proxy_url=None):
        exp_time = self.decode_token(email)
        if not exp_time:
            self.log(
                f"{Fore.CYAN+Style.BRIGHT}Status :{Style.RESET_ALL}"
                f"{Fore.RED+Style.BRIGHT} Invalid Token {Style.RESET_ALL}"
            )
            return False

        if int(time.time()) > exp_time:
            refresh = await self.refresh_token(email, proxy_url)
            if not refresh: return False

            self.accounts[email]["accessToken"] = refresh.get("data", {}).get("accessToken")
            self.accounts[email]["refreshToken"] = refresh.get("data", {}).get("refreshToken")

            account_data = [{
                "email": email,
                "interlinkId": self.accounts[email]["interlinkId"],
                "passcode": self.accounts[email]["passcode"],
                "deviceId": self.accounts[email]["deviceId"],
                "tokens": {
                    "accessToken": self.accounts[email]["accessToken"],
                    "refreshToken": self.accounts[email]["refreshToken"]
                }
            }]
            self.save_accounts(account_data)

            self.log(
                f"{Fore.CYAN+Style.BRIGHT}Status :{Style.RESET_ALL}"
                f"{Fore.GREEN+Style.BRIGHT} Tokens Refreshed {Style.RESET_ALL}"
            )

        return True

    async def process_accounts(self, email: str, proxy_url=None):
        is_ok = await self.process_check_connection(email, proxy_url)
        if not is_ok: return False

        if self.USE_PROXY:
            proxy_url = self.get_next_proxy_for_account(email)

        is_valid = await self.process_check_tokens(email, proxy_url)
        if not is_valid: return False

        balance = await self.token_balance(email, proxy_url)
        if balance:
            token_balance = balance.get("data", {}).get("interlinkTokenAmount", 0)
            silver_balance = balance.get("data", {}).get("interlinkSilverTokenAmount", 0)
            gold_balance = balance.get("data", {}).get("interlinkGoldTokenAmount", 0)
            diamond_balance = balance.get("data", {}).get("interlinkDiamondTokenAmount", 0)

            self.log(f"{Fore.CYAN+Style.BRIGHT}Balance:{Style.RESET_ALL}")
            self.log(
                f"{Fore.MAGENTA+Style.BRIGHT}  ● {Style.RESET_ALL}"
                f"{Fore.BLUE+Style.BRIGHT}Interlink:{Style.RESET_ALL}"
                f"{Fore.WHITE+Style.BRIGHT} {token_balance} {Style.RESET_ALL}"
            )
            self.log(
                f"{Fore.MAGENTA+Style.BRIGHT}  ● {Style.RESET_ALL}"
                f"{Fore.BLUE+Style.BRIGHT}Silver   :{Style.RESET_ALL}"
                f"{Fore.WHITE+Style.BRIGHT} {silver_balance} {Style.RESET_ALL}"
            )
            self.log(
                f"{Fore.MAGENTA+Style.BRIGHT}  ● {Style.RESET_ALL}"
                f"{Fore.BLUE+Style.BRIGHT}Gold     :{Style.RESET_ALL}"
                f"{Fore.WHITE+Style.BRIGHT} {gold_balance} {Style.RESET_ALL}"
            )
            self.log(
                f"{Fore.MAGENTA+Style.BRIGHT}  ● {Style.RESET_ALL}"
                f"{Fore.BLUE+Style.BRIGHT}Diamond  :{Style.RESET_ALL}"
                f"{Fore.WHITE+Style.BRIGHT} {diamond_balance} {Style.RESET_ALL}"
            )

        claimable = await self.claimable_check(email, proxy_url)
        if claimable:
            is_claimable = claimable.get("data", {}).get("isClaimable", False)

            if is_claimable:
                claim = await self.claim_airdrop(email, proxy_url)
                if claim:
                    reward = claim.get("data") or "N/A"

                    self.log(
                        f"{Fore.CYAN+Style.BRIGHT}Mining :{Style.RESET_ALL}"
                        f"{Fore.GREEN+Style.BRIGHT} Claimed Successfully {Style.RESET_ALL}"
                        f"{Fore.MAGENTA+Style.BRIGHT}-{Style.RESET_ALL}"
                        f"{Fore.CYAN+Style.BRIGHT} Reward: {Style.RESET_ALL}"
                        f"{Fore.WHITE+Style.BRIGHT}{reward}{Style.RESET_ALL}"
                    )

            else:
                next_frame_ts = claimable.get("data", {}).get("nextFrame", 0) / 1000
                next_frame_wib = datetime.fromtimestamp(next_frame_ts).strftime('%x %X')

                self.log(
                    f"{Fore.CYAN+Style.BRIGHT}Mining :{Style.RESET_ALL}"
                    f"{Fore.YELLOW+Style.BRIGHT} Already Claimed {Style.RESET_ALL}"
                    f"{Fore.MAGENTA+Style.BRIGHT}-{Style.RESET_ALL}"
                    f"{Fore.CYAN+Style.BRIGHT} Next Claim at: {Style.RESET_ALL}"
                    f"{Fore.WHITE+Style.BRIGHT}{next_frame_wib}{Style.RESET_ALL}"
                )

        if self.ENABLE_GROUP_MINING:
            try:
                await self.process_group_mining(email, proxy_url)
            except Exception as e:
                self.log(
                    f"{Fore.CYAN+Style.BRIGHT}GrpMine:{Style.RESET_ALL}"
                    f"{Fore.RED+Style.BRIGHT} Error: {e} {Style.RESET_ALL}"
                )

        if self.ENABLE_RECOVERY:
            try:
                await self.process_recovery(email, proxy_url)
            except Exception as e:
                self.log(
                    f"{Fore.CYAN+Style.BRIGHT}Recover:{Style.RESET_ALL}"
                    f"{Fore.RED+Style.BRIGHT} Error: {e} {Style.RESET_ALL}"
                )

    async def main(self):
        try:
            accounts = self.load_accounts()
            if not accounts:
                self.log(f"{Fore.RED}No Accounts Loaded.{Style.RESET_ALL}")
                return

            self.print_question()

            while True:
                self.clear_terminal()
                self.welcome()
                self.log(
                    f"{Fore.GREEN + Style.BRIGHT}Account's Total: {Style.RESET_ALL}"
                    f"{Fore.WHITE + Style.BRIGHT}{len(accounts)}{Style.RESET_ALL}"
                )

                if self.USE_PROXY: self.load_proxies()
        
                separator = "=" * 27
                for idx, account in enumerate(accounts, start=1):
                    email = account.get("email")
                    interlink_id = account.get("interlinkId")
                    passcode = account.get("passcode")
                    device_id = account.get("deviceId")
                    tokens = account.get("tokens", {})
                    access_token = tokens.get("accessToken")
                    refresh_token = tokens.get("refreshToken")

                    if device_id is None:
                        device_id = self.generate_device_id()

                    account_data = [{
                        "email": email,
                        "interlinkId": interlink_id,
                        "passcode": passcode,
                        "deviceId": device_id,
                        "tokens": {
                            "accessToken": access_token,
                            "refreshToken": refresh_token
                        }
                    }]
                    self.save_accounts(account_data)

                    self.log(
                        f"{Fore.CYAN + Style.BRIGHT}{separator}[{Style.RESET_ALL}"
                        f"{Fore.WHITE + Style.BRIGHT} {idx} {Style.RESET_ALL}"
                        f"{Fore.CYAN + Style.BRIGHT}Of{Style.RESET_ALL}"
                        f"{Fore.WHITE + Style.BRIGHT} {len(accounts)} {Style.RESET_ALL}"
                        f"{Fore.CYAN + Style.BRIGHT}]{separator}{Style.RESET_ALL}"
                    )

                    if "@" not in email or not interlink_id or not passcode or not device_id or not access_token or not refresh_token:
                        self.log(
                            f"{Fore.CYAN+Style.BRIGHT}Status :{Style.RESET_ALL}"
                            f"{Fore.RED+Style.BRIGHT} Invalid Account Data {Style.RESET_ALL}"
                        )
                        continue

                    self.log(
                        f"{Fore.CYAN+Style.BRIGHT}Account:{Style.RESET_ALL}"
                        f"{Fore.WHITE+Style.BRIGHT} {self.mask_account(email)} {Style.RESET_ALL}"
                    )

                    self.accounts[email] = {
                        "interlinkId": interlink_id,
                        "passcode": passcode,
                        "deviceId": device_id,
                        "accessToken": access_token,
                        "refreshToken": refresh_token
                    }
                    
                    await self.process_accounts(email)
                    await asyncio.sleep(random.uniform(2.0, 3.0))

                self.log(f"{Fore.CYAN + Style.BRIGHT}={Style.RESET_ALL}"*65)

                # 智能等待：计算到下一个早上9点的秒数
                # 安全组挖矿每天9点刷新，普通挖矿4小时一轮
                now = datetime.now()
                next_9am = now.replace(hour=9, minute=0, second=0, microsecond=0)
                if now >= next_9am:
                    next_9am = next_9am + timedelta(days=1)
                seconds_to_9am = int((next_9am - now).total_seconds())

                # 如果距9点不到1小时，等到9点；否则等4小时（普通挖矿周期）
                if seconds_to_9am <= 3600:
                    seconds = seconds_to_9am + 30  # 9点后多等30秒，确保服务端已刷新
                    self.log(
                        f"{Fore.CYAN+Style.BRIGHT}GrpMine:{Style.RESET_ALL}"
                        f"{Fore.WHITE+Style.BRIGHT} Waiting until 09:00 for Group Mining reset... {Style.RESET_ALL}"
                    )
                else:
                    seconds = 4 * 60 * 60
                    self.log(
                        f"{Fore.CYAN+Style.BRIGHT}GrpMine:{Style.RESET_ALL}"
                        f"{Fore.WHITE+Style.BRIGHT} Next Group Mining reset at: {next_9am.strftime('%x %X')} {Style.RESET_ALL}"
                    )

                while seconds > 0:
                    formatted_time = self.format_seconds(seconds)
                    print(
                        f"{Fore.CYAN+Style.BRIGHT}[ Wait for{Style.RESET_ALL}"
                        f"{Fore.WHITE+Style.BRIGHT} {formatted_time} {Style.RESET_ALL}"
                        f"{Fore.CYAN+Style.BRIGHT}... ]{Style.RESET_ALL}"
                        f"{Fore.WHITE+Style.BRIGHT} | {Style.RESET_ALL}"
                        f"{Fore.BLUE+Style.BRIGHT}All Accounts Have Been Processed...{Style.RESET_ALL}",
                        end="\r"
                    )
                    await asyncio.sleep(1)
                    seconds -= 1

        except Exception as e:
            self.log(f"{Fore.RED+Style.BRIGHT}Error: {e}{Style.RESET_ALL}")
            raise e

if __name__ == "__main__":
    try:
        bot = Interlink()
        asyncio.run(bot.main())
    except KeyboardInterrupt:
        print(
            f"{Fore.CYAN + Style.BRIGHT}[ {datetime.now().strftime('%x %X')} ]{Style.RESET_ALL}"
            f"{Fore.WHITE + Style.BRIGHT} | {Style.RESET_ALL}"
            f"{Fore.RED + Style.BRIGHT}[ EXIT ] Interlink - BOT{Style.RESET_ALL}                                       "                              
        )
        sys.exit(1)
