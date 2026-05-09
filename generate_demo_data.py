"""
Generate realistic demo_alerts.xlsx matching real APT alert data patterns.

Key realism improvements over the old generator:
- C2 beacon patterns: same device→same target→same port appears across multiple days
- Lateral movement: same source IP hits many different targets
- Multi-device targeting: popular C2 domains hit by many devices
- Realistic device IDs (hostnames, not random MD5)
- Proper alert_count distribution (scanning=high, APT=low/medium)
- Cross-day persistence for true APT indicators
"""
import pandas as pd
import random
import os
from datetime import datetime, timedelta

random.seed(42)

# ── Column Headers (matching user's real data format) ──
HEADERS = [
    "设备ID", "首次告警时间", "最近告警时间", "源IP", "外联目标", "外联端口",
    "威胁类型", "威胁等级", "标准APT组织", "APT组织", "APT组织分类",
    "告警次数", "厂商", "协议", "情报标签", "目标类型", "情报位置",
    "处置动作", "DNS解析IP", "下行流量", "上行流量", "资产类型",
    "研判状态", "重点关注",
]

TOTAL_ROWS = 100_000
print(f"Generating {TOTAL_ROWS:,} rows with realistic patterns...")

# ═══════════════════════════════════════════════════════════
# DATA POOLS
# ═══════════════════════════════════════════════════════════

# ── Realistic internal IP ranges ──
INTERNAL_RANGES = [
    ("10.100.", 10, 50), ("10.200.", 1, 30), ("10.50.", 1, 20),
    ("192.168.1.", 1, 254), ("192.168.10.", 1, 100), ("192.168.20.", 1, 80),
    ("172.16.10.", 1, 50), ("172.16.20.", 1, 40),
]

# ── Realistic device hostnames ──
DEVICE_PREFIXES = [
    "DESKTOP-", "LAPTOP-", "SRV-", "PC-", "WIN-", "NB-", "WS-",
]
DEVICE_USERS = ["admin", "zhangsan", "lisi", "wangwu", "zhaoliu", "liuqi",
    "chenba", "yangjiu", "huanglei", "zhoujie", "wuxian", "suner",
    "malin", "huangshan", "hefei", "wuhan", "nanjing", "hangzhou"]

# ── C2 target domains (APT-related, realistic bad domains) ──
C2_DOMAINS = [
    "update.microsoft-secure.cc", "cdn.jsdelivr-cache.top", "api.cloudflare-dns.xyz",
    "news.bbc-update.net", "mail.exchange-online.vip", "portal.office365-login.cc",
    "dns.google-resolver.top", "ntp.time-sync.xyz", "ws.tencent-game.cc",
    "api.wechat-pay.xyz", "login.alipay-secure.top", "m.alibaba-trade.vip",
    "static.jd-cdn.cc", "img.tmall-shop.xyz", "video.douyin-cdn.top",
    "update.kingsoft-secure.cc", "download.wps-office.xyz", "cloud.baidu-disk.top",
    "api.huawei-cloud.vip", "console.qcloud-secure.cc", "cdn.netease-game.xyz",
    "auth.steam-community.top", "store.epic-games.cc", "login.taobao-secure.xyz",
    "pay.unionpay-secure.top", "ebank.icbc-online.cc", "sms.10086-update.xyz",
    "adobe-update.cc", "oracle-java.net", "cdn.bootcss.top",
    "logger.mysql-sync.cc", "replica.postgres-db.xyz", "sync.redis-cache.top",
    "monitor.zabbix-alert.cc", "backup.nas-storage.xyz", "vpn.corporate-access.top",
    "owa.mail-exchange.cc", "lync.skype-business.xyz", "teams.microsoft-meeting.top",
    "zoom.us-join.cc", "webex.cisco-meeting.xyz", "slack.enterprise-im.top",
    "gitlab.internal-code.cc", "jenkins.ci-build.xyz", "docker.registry-hub.top",
    "k8s.container-cloud.cc", "api.gateway-micro.xyz", "nacos.config-center.top",
    "erp.sap-business.cc", "crm.salesforce-cn.xyz", "oa.office-automation.top",
    "c2.evil-apt.xyz", "panel.botnet-ctrl.cc", "gate.phishing-login.top",
]

# ── C2 IP-like targets ──
C2_IPS = [
    "45.142.120.91", "103.96.74.123", "185.220.101.34", "91.121.87.10",
    "5.188.87.66", "185.244.25.179", "94.102.61.78", "45.155.205.99",
    "103.224.182.253", "198.144.121.88", "185.56.80.205", "91.234.254.147",
    "45.76.155.102", "149.28.158.67", "104.238.180.119", "45.63.97.44",
    "66.42.66.201", "139.180.143.82", "208.87.243.131", "23.254.211.228",
]

# ── Clean/benign targets (for noise/false positives) ──
CLEAN_DOMAINS = [
    "www.baidu.com", "www.google.com", "api.github.com", "www.microsoft.com",
    "cdn.jsdelivr.net", "www.google-analytics.com", "realtime.tencent.com",
    "api.weixin.qq.com", "www.aliyun.com", "log.aliyuncs.com",
    "download.windowsupdate.com", "ctldl.windowsupdate.com",
    "ocsp.digicert.com", "crl.globalsign.com",
]

CLEAN_IPS = [
    "8.8.8.8", "8.8.4.4", "114.114.114.114", "1.1.1.1",
    "223.5.5.5", "119.29.29.29", "180.76.76.76",
]

# ── Scan targets (random IPs being scanned) ──
def random_scan_ip():
    return f"{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}"

# ── Port pools ──
C2_PORTS = [443, 8443, 80, 8080, 4444, 5555, 6666, 7777, 8888, 9999, 5178, 8000]
SCAN_PORTS = [22, 23, 25, 53, 80, 135, 139, 443, 445, 1433, 1521, 3306, 3389, 5432, 6379, 8080, 8443, 27017]
COMMON_PORTS = [80, 443, 53, 8080, 8443]

# ── Threat types ──
THREAT_TYPES_APT = [
    "APT,远控木马", "APT,远控木马,恶意软件", "APT", "远控木马",
    "APT,僵尸网络,远控木马", "恶意软件,APT,远控木马",
]
THREAT_TYPES_SCAN = [
    "扫描探测", "扫描探测,流量异常", "扫描探测,暴力破解",
]
THREAT_TYPES_OTHER = [
    "恶意软件", "僵尸网络", "DDoS,僵尸网络", "流量异常",
    "钓鱼攻击", "横向移动", "恶意软件,僵尸网络",
]
THREAT_TYPES_NOISE = [
    "流量异常", "扫描探测,流量异常", "扫描探测",
]

THREAT_LEVELS = ["高", "中", "低"]

# ── APT orgs ──
STD_APT_ORGS = [
    "oceanlotus", "turla", "lazarus", "apt28", "dukes", "darkhotel",
    "方程式", "白象", "响尾蛇", "蔓灵花", "毒云藤",
]

APT_ORG_NAMES = [
    "海莲花", "Turla", "Lazarus", "APT28", "DarkHotel",
    "白象组织", "蔓灵花", "响尾蛇组织", "方程式组织", "毒云藤",
]

APT_TIERS = ["一级", "二级", "三级"]

# ── Vendors ──
VENDORS_POOL = [
    "腾讯,安恒信息,知道创宇",
    "腾讯,安恒信息,360",
    "腾讯,知道创宇,安恒信息,360",
    "安恒信息,360,腾讯",
    "360,腾讯",
    "腾讯,安恒信息",
    "知道创宇,360,华为",
    "腾讯",
    "360",
]

# ── Protocols ──
PROTOCOLS = ["tcp", "udp", "http", "https", "dns"]

# ── Misc ──
TARGET_TYPES = ["IP", "域名"]
ASSET_TYPES = ["终端", "服务器", ""]
ANALYSIS_STATUSES = ["未研判"] * 60 + ["研判中"] * 20 + ["已研判"] * 15 + ["忽略"] * 5
IS_FOCUSED = ["否"] * 85 + ["是"] * 15

# ═══════════════════════════════════════════════════════════
# GENERATION STRATEGY
# ═══════════════════════════════════════════════════════════

# We'll generate patterns in layers:
# 1. C2 beacons (25% = 25k rows): repeating device→target→port across days
# 2. Lateral movement (15% = 15k rows): same source IP to many targets
# 3. Multi-device C2 (20% = 20k rows): popular C2 hit by many devices
# 4. Scanning noise (30% = 30k rows): high-count scan alerts
# 5. Random mix (10% = 10k rows): fill remaining

NOW = datetime(2026, 4, 29, 9, 0, 0)
TOTAL_DEVICES = 5000

# Generate device pool
devices = []
for i in range(TOTAL_DEVICES):
    prefix = random.choice(DEVICE_PREFIXES)
    if random.random() < 0.6:
        # Hostname-style: DESKTOP-zhangsan, PC-admin-01
        user = random.choice(DEVICE_USERS)
        suffix = f"{random.randint(1, 99):02d}" if random.random() < 0.5 else ""
        dev_id = f"{prefix}{user}{suffix}"
    else:
        # Asset-number style: SRV-BJ-001, WIN-GZ-123
        city = random.choice(["BJ", "SH", "GZ", "SZ", "CD", "WH", "NJ", "HZ"])
        num = f"{random.randint(1, 999):03d}"
        dev_id = f"{prefix}{city}-{num}"
    devices.append(dev_id)

# Generate source IPs mapped to devices
device_source_ips = {}
for dev in devices:
    rng = random.choice(INTERNAL_RANGES)
    ip = f"{rng[0]}{random.randint(rng[1], rng[2])}"
    device_source_ips[dev] = ip

# Pool of source IPs for lateral movement (pick 100 IPs)
lateral_source_ips = random.sample(list(device_source_ips.values()), min(100, len(device_source_ips)))

rows = []

def make_row(device_id, first_time, last_time, source_ip, target, target_type, port,
             threat_type, threat_level, std_apt_org, apt_org, apt_tier,
             alert_count, vendors, protocol, intel_tags,
             dns_ip, down_traffic, up_traffic, asset_type,
             analysis_status, is_focused):
    return {
        "设备ID": device_id,
        "首次告警时间": first_time.strftime("%Y-%m-%d %H:%M:%S"),
        "最近告警时间": last_time.strftime("%Y-%m-%d %H:%M:%S"),
        "源IP": source_ip,
        "外联目标": target,
        "外联端口": port,
        "威胁类型": threat_type,
        "威胁等级": threat_level,
        "标准APT组织": std_apt_org,
        "APT组织": apt_org,
        "APT组织分类": apt_tier,
        "告警次数": alert_count,
        "厂商": vendors,
        "协议": protocol,
        "情报标签": intel_tags,
        "目标类型": target_type,
        "情报位置": "设备侧",
        "处置动作": "远程",
        "DNS解析IP": dns_ip,
        "下行流量": down_traffic,
        "上行流量": up_traffic,
        "资产类型": asset_type,
        "研判状态": analysis_status,
        "重点关注": is_focused,
    }

# ═══════════════════════════════════════════════════════════
# LAYER 1: C2 Beacons (25k rows)
# Same device→target→port appearing across multiple days
# ═══════════════════════════════════════════════════════════
print("Layer 1: Generating C2 beacon patterns...")
BEACON_DEVICES = 500
BEACON_C2_ALL = C2_DOMAINS + C2_IPS
BEACON_C2_TARGETS = min(len(BEACON_C2_ALL), 60)
BEACON_DAYS = 14

# Pick beacon devices and targets
beacon_devices = random.sample(devices, BEACON_DEVICES)
beacon_c2 = random.sample(BEACON_C2_ALL, BEACON_C2_TARGETS)

for c2_target in beacon_c2:
    is_ip = c2_target.replace(".", "").isdigit()
    target_type = "IP" if is_ip else "域名"
    dns_ip = "" if is_ip else f"{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}"
    port = random.choice(C2_PORTS)
    # Each C2 is hit by 5-20 devices
    num_devices = random.randint(5, 20)
    for _ in range(num_devices):
        dev = random.choice(beacon_devices)
        source_ip = device_source_ips[dev]
        # Each device beacons every 1-3 days across 14 days
        for day_offset in range(0, BEACON_DAYS, random.randint(1, 3)):
            day = NOW - timedelta(days=day_offset)
            first_time = day.replace(hour=random.randint(6, 22), minute=random.randint(0, 59))
            last_time = first_time + timedelta(hours=random.randint(1, 8))
            if last_time > day.replace(hour=23, minute=59):
                last_time = day.replace(hour=23, minute=59)

            threat_type = random.choice(THREAT_TYPES_APT)
            std_apt_org = random.choice(STD_APT_ORGS)
            apt_org = random.choice(APT_ORG_NAMES)
            apt_tier = random.choice(APT_TIERS)
            intel_tags = random.choice(["apt,c2", "apt,远控", "c2,远控木马", "apt,c2,远控", ""])

            rows.append(make_row(
                dev, first_time, last_time, source_ip, c2_target, target_type, port,
                threat_type, "高", std_apt_org, apt_org, apt_tier,
                random.randint(3, 500), random.choice(VENDORS_POOL),
                random.choice(PROTOCOLS), intel_tags,
                dns_ip, random.randint(0, 50000), random.randint(0, 100000),
                random.choice(ASSET_TYPES), random.choice(ANALYSIS_STATUSES),
                random.choice(IS_FOCUSED),
            ))

print(f"  C2 beacon rows: {len(rows)}")

# ═══════════════════════════════════════════════════════════
# LAYER 2: Lateral Movement (15k rows)
# Same source IP hitting many different targets
# ═══════════════════════════════════════════════════════════
print("Layer 2: Generating lateral movement patterns...")
LATERAL_TARGET_COUNT = 3000

target_count_before = len(rows)
lateral_count = 0
for src_ip in lateral_source_ips:
    # Each lateral source hits 50-200 targets
    num_targets = random.randint(50, 200)
    if lateral_count + num_targets > 15000:
        num_targets = 15000 - lateral_count
    if num_targets <= 0:
        break
    # Find device for this IP
    dev = None
    for d, ip in device_source_ips.items():
        if ip == src_ip:
            dev = d
            break
    if not dev:
        continue

    for _ in range(num_targets):
        day = NOW - timedelta(days=random.randint(0, 13))
        first_time = day.replace(hour=random.randint(0, 23), minute=random.randint(0, 59))
        last_time = first_time + timedelta(minutes=random.randint(0, 120))

        target = random_scan_ip()
        port = random.choice([445, 135, 139, 3389, 22, 5985, 5986])
        threat_type = "横向移动"
        rows.append(make_row(
            dev, first_time, last_time, src_ip, target, "IP", port,
            threat_type, "中", "", "", "",
            random.randint(1, 50), "360,腾讯", "tcp", "",
            "", random.randint(0, 1000), random.randint(0, 2000),
            "服务器", random.choice(ANALYSIS_STATUSES), "否",
        ))
        lateral_count += 1

print(f"  Lateral rows: {len(rows) - target_count_before}")

# ═══════════════════════════════════════════════════════════
# LAYER 3: Multi-device C2 (20k rows)
# Many different devices hitting the same popular C2
# ═══════════════════════════════════════════════════════════
print("Layer 3: Generating multi-device C2 patterns...")
target_count_before = len(rows)
MULTI_C2 = random.sample(C2_DOMAINS, 40) + random.sample(C2_IPS, 10)

for c2_target in MULTI_C2:
    is_ip = c2_target.replace(".", "").isdigit()
    target_type = "IP" if is_ip else "域名"
    dns_ip = "" if is_ip else f"{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}"
    port = random.choice(C2_PORTS)
    # Each C2 hit by 100-500 devices
    num_devices = random.randint(100, 500)
    used_devices = random.sample(devices, min(num_devices, len(devices)))
    for dev in used_devices:
        day = NOW - timedelta(days=random.randint(0, 13))
        first_time = day.replace(hour=random.randint(0, 23), minute=random.randint(0, 59))
        last_time = first_time + timedelta(hours=random.randint(0, 12))
        source_ip = device_source_ips[dev]

        threat_type = random.choice(THREAT_TYPES_APT)
        std_apt_org = random.choice(STD_APT_ORGS)
        apt_org = random.choice(APT_ORG_NAMES)
        apt_tier = random.choice(APT_TIERS)
        intel_tags = random.choice(["apt", "c2", "apt,c2", ""])

        rows.append(make_row(
            dev, first_time, last_time, source_ip, c2_target, target_type, port,
            threat_type, random.choice(["高", "中"]), std_apt_org, apt_org, apt_tier,
            random.randint(1, 200), random.choice(VENDORS_POOL),
            random.choice(PROTOCOLS), intel_tags,
            dns_ip, random.randint(0, 20000), random.randint(0, 50000),
            random.choice(ASSET_TYPES), random.choice(ANALYSIS_STATUSES),
            random.choice(IS_FOCUSED),
        ))

print(f"  Multi-C2 rows: {len(rows) - target_count_before}")

# ═══════════════════════════════════════════════════════════
# LAYER 4: Scanning Noise (30k rows)
# High alert_count, many targets, benign-looking
# ═══════════════════════════════════════════════════════════
print("Layer 4: Generating scanning noise...")
target_count_before = len(rows)
SCAN_DEVICES = random.sample(devices, 2000)

for dev in SCAN_DEVICES:
    source_ip = device_source_ips[dev]
    # Each scanner generates 5-25 rows
    for _ in range(random.randint(5, 25)):
        day = NOW - timedelta(days=random.randint(0, 13))
        first_time = day.replace(hour=random.randint(0, 23), minute=random.randint(0, 59))
        last_time = first_time + timedelta(minutes=random.randint(0, 180))

        is_ip = random.random() < 0.7
        target = random_scan_ip() if is_ip else random.choice(CLEAN_DOMAINS)
        target_type = "IP" if is_ip else "域名"
        port = random.choice(SCAN_PORTS)
        threat_type = random.choice(THREAT_TYPES_SCAN)
        alert_count = random.choices([100, 200, 500, 1000, 2000, 5000, 8000],
                                     weights=[25, 20, 15, 15, 10, 10, 5])[0]

        rows.append(make_row(
            dev, first_time, last_time, source_ip, target, target_type, port,
            threat_type, "低", "", "", "",
            alert_count, random.choice(["腾讯", "360", "腾讯,360"]),
            random.choice(PROTOCOLS), "",
            "", 0, 0, random.choice(ASSET_TYPES),
            "未研判", "否",
        ))

# Trim to ~30k
while len(rows) - target_count_before > 30000:
    rows.pop(random.randint(target_count_before, len(rows) - 1))

print(f"  Scan noise rows: {len(rows) - target_count_before}")

# ═══════════════════════════════════════════════════════════
# LAYER 5: Random mix (fill to 100k)
# ═══════════════════════════════════════════════════════════
print("Layer 5: Filling remaining rows...")
target_count = max(0, TOTAL_ROWS - len(rows))
for i in range(target_count):
    dev = random.choice(devices)
    source_ip = device_source_ips[dev]
    day = NOW - timedelta(days=random.randint(0, 13))
    first_time = day.replace(hour=random.randint(0, 23), minute=random.randint(0, 59))
    last_time = first_time + timedelta(minutes=random.randint(0, 240))

    is_ip = random.random() < 0.5
    target = random_scan_ip() if is_ip else random.choice(C2_DOMAINS + CLEAN_DOMAINS)
    target_type = "IP" if is_ip else "域名"
    port = random.choice(COMMON_PORTS + C2_PORTS + SCAN_PORTS)

    # Bias toward mixed/interesting threats for remaining rows
    roll = random.random()
    if roll < 0.3:
        threat_type = random.choice(THREAT_TYPES_APT)
        threat_level = random.choice(["高", "中"])
        std_apt_org = random.choice(STD_APT_ORGS)
        apt_org = random.choice(APT_ORG_NAMES)
        apt_tier = random.choice(APT_TIERS)
    elif roll < 0.6:
        threat_type = random.choice(THREAT_TYPES_OTHER)
        threat_level = random.choice(["中", "低"])
        std_apt_org = ""
        apt_org = ""
        apt_tier = ""
    else:
        threat_type = random.choice(THREAT_TYPES_NOISE)
        threat_level = "低"
        std_apt_org = ""
        apt_org = ""
        apt_tier = ""

    intel_tags = random.choice(["apt,c2", "c2", "远控", ""]) if "APT" in threat_type else ""

    rows.append(make_row(
        dev, first_time, last_time, source_ip, target, target_type, port,
        threat_type, threat_level, std_apt_org, apt_org, apt_tier,
        random.randint(1, 300), random.choice(VENDORS_POOL),
        random.choice(PROTOCOLS), intel_tags,
        "", random.randint(0, 30000), random.randint(0, 60000),
        random.choice(ASSET_TYPES), random.choice(ANALYSIS_STATUSES),
        random.choice(IS_FOCUSED),
    ))

# ── Final shuffle (data naturally has time clustering, keep it) ──
print(f"Total rows: {len(rows):,}")

# ── Save ──
df = pd.DataFrame(rows, columns=HEADERS)
output_dir = 'uploads'
os.makedirs(output_dir, exist_ok=True)
output_path = os.path.join(output_dir, 'demo_alerts.xlsx')
df.to_excel(output_path, index=False, engine='openpyxl')
print(f"\nSaved {len(df):,} rows to {output_path}")
print(f"File size: {os.path.getsize(output_path) / (1024*1024):.1f} MB")

# ── Quick stats ──
apt_rows = sum(1 for r in rows if "APT" in str(r["威胁类型"]) or "远控" in str(r["威胁类型"]))
print(f"APT/C2-related rows: {apt_rows:,}")
print(f"Unique devices: {len(set(r['设备ID'] for r in rows)):,}")
print(f"Unique targets: {len(set(r['外联目标'] for r in rows)):,}")
