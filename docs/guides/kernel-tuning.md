# Kernel Tuning for BNG

A Linux-based BNG (Broadband Network Gateway) running accel-ppp behaves as a high-throughput router with thousands of point-to-point interfaces. The default kernel settings are designed for general-purpose servers and desktops, not for a device that terminates thousands of PPPoE sessions, performs NAT on every packet, and maintains tens of thousands of concurrent connections.

This guide documents every kernel parameter that should be tuned on a production BNG node, explains **why** each one matters, and provides ready-to-use configuration files.

!!! warning "Production impact"
    These settings are applied live with `sysctl -p`. They do **not** require a reboot or restart of accel-ppp. Existing PPPoE sessions are unaffected. However, incorrect values (especially `rp_filter=0`) can open security holes. Always review before applying.

---

## Quick Apply

If you used the installer script (`install.sh`), these files are **not** created automatically -- the installer only sets up dawos-agent, not kernel tuning. Apply them manually:

```bash
# Create all four config files
sudo tee /etc/sysctl.d/99-accel-ppp.conf > /dev/null << 'EOF'
# === BNG / BRAS kernel tuning for accel-ppp ===
# See: https://cepat-kilat-teknologi.github.io/dawos-agent/guides/kernel-tuning/

# -- Packet forwarding (required for PPPoE routing) --
net.ipv4.ip_forward=1
net.ipv6.conf.all.forwarding=1

# -- Reverse path filtering (loose mode for asymmetric routing) --
net.ipv4.conf.all.rp_filter=2
net.ipv4.conf.default.rp_filter=2

# -- Socket buffers (16 MB each, up from 208 KB default) --
net.core.rmem_max=16777216
net.core.wmem_max=16777216

# -- Network device backlog (250k, up from 1000 default) --
net.core.netdev_max_backlog=250000

# -- Socket listen backlog --
net.core.somaxconn=4096

# -- File descriptor limit (1M, up from ~100k default) --
fs.file-max=1000000

# -- ARP table sizing (for thousands of directly-connected PPPoE hosts) --
net.ipv4.neigh.default.gc_thresh1=8192
net.ipv4.neigh.default.gc_thresh2=32768
net.ipv4.neigh.default.gc_thresh3=65536

# -- Connection tracking (1M entries, optimized timeouts) --
net.netfilter.nf_conntrack_max=1048576
net.netfilter.nf_conntrack_buckets=262144
net.netfilter.nf_conntrack_tcp_timeout_established=43200
net.netfilter.nf_conntrack_tcp_timeout_fin_wait=30
net.netfilter.nf_conntrack_udp_timeout=10
net.netfilter.nf_conntrack_udp_timeout_stream=60
net.netfilter.nf_conntrack_icmp_timeout=10

# -- TCP performance (NAT-aware, BNG-optimized) --
net.ipv4.tcp_fin_timeout=30
net.ipv4.tcp_tw_reuse=1
net.ipv4.tcp_no_metrics_save=1
net.ipv4.tcp_congestion_control=bbr

# -- Memory pressure reserve (128 MB minimum free) --
vm.min_free_kbytes=131072
EOF

sudo tee /etc/sysctl.d/10-network-security.conf > /dev/null << 'EOF'
# === BNG edge security hardening ===

# Reverse path filtering (loose mode)
net.ipv4.conf.default.rp_filter=2
net.ipv4.conf.all.rp_filter=2

# Do not send ICMP redirects (BNG is the only gateway)
net.ipv4.conf.all.send_redirects=0
net.ipv4.conf.default.send_redirects=0

# Do not accept ICMP redirects (prevent routing table manipulation)
net.ipv4.conf.all.accept_redirects=0
net.ipv4.conf.default.accept_redirects=0
net.ipv4.conf.all.secure_redirects=0
net.ipv4.conf.default.secure_redirects=0
net.ipv6.conf.all.accept_redirects=0
net.ipv6.conf.default.accept_redirects=0

# Reject source-routed packets (prevent firewall bypass)
net.ipv4.conf.all.accept_source_route=0
net.ipv4.conf.default.accept_source_route=0
net.ipv6.conf.all.accept_source_route=0
net.ipv6.conf.default.accept_source_route=0

# Log packets with impossible source addresses (spoofing detection)
net.ipv4.conf.all.log_martians=1
net.ipv4.conf.default.log_martians=1

# SYN flood protection
net.ipv4.tcp_syncookies=1

# ICMP hardening (anti-Smurf, ignore bogus errors)
net.ipv4.icmp_echo_ignore_broadcasts=1
net.ipv4.icmp_ignore_bogus_error_responses=1
EOF

sudo tee /etc/sysctl.d/10-bufferbloat.conf > /dev/null << 'EOF'
# === Anti-bufferbloat: Fair Queue CoDel as default qdisc ===
net.core.default_qdisc = fq_codel
EOF

# Apply all at once
sudo sysctl --system

# Verify key values
sysctl net.ipv4.ip_forward net.netfilter.nf_conntrack_max \
       net.ipv4.tcp_syncookies net.ipv4.tcp_congestion_control \
       net.core.default_qdisc
```

### Process File Descriptor Limits

The `fs.file-max` sysctl sets the **system-wide** limit, but each process also has its own per-process limit (default: 1024). Both must be raised.

```bash
# Per-process limits for the dawos user
sudo tee /etc/security/limits.d/dawos.conf > /dev/null << 'EOF'
dawos    soft    nofile    65536
dawos    hard    nofile    65536
EOF

# Also set in the systemd unit (overrides limits.conf for services)
sudo mkdir -p /etc/systemd/system/dawos-agent.service.d
sudo tee /etc/systemd/system/dawos-agent.service.d/limits.conf > /dev/null << 'EOF'
[Service]
LimitNOFILE=65536
EOF

sudo mkdir -p /etc/systemd/system/accel-ppp.service.d
sudo tee /etc/systemd/system/accel-ppp.service.d/limits.conf > /dev/null << 'EOF'
[Service]
LimitNOFILE=65536
EOF

sudo systemctl daemon-reload
sudo systemctl restart dawos-agent
sudo systemctl restart accel-ppp
```

---

## Parameter Reference

### Packet Forwarding

These are the most fundamental settings. Without IP forwarding, the BNG cannot route packets between subscriber PPP interfaces and the uplink -- it would act as an endpoint, not a router.

#### `net.ipv4.ip_forward`

| | |
|---|---|
| **What it does** | Enables the kernel to forward IPv4 packets between network interfaces. |
| **Default** | `0` (disabled) |
| **Recommended** | `1` (enabled) |
| **Why it matters** | A BNG is a router. Packets arrive on `ppp0`..`pppN` interfaces from subscribers and must be forwarded to the uplink (`ens18`, `ens19`, etc.) and vice versa. Without this, subscribers cannot reach the internet. |
| **What happens without it** | Subscribers connect (PPPoE session establishes) but cannot send or receive any traffic. Ping, web, everything fails. |
| **Config file** | `/etc/sysctl.d/99-accel-ppp.conf` |

#### `net.ipv6.conf.all.forwarding`

| | |
|---|---|
| **What it does** | Enables IPv6 packet forwarding across all interfaces. |
| **Default** | `0` (disabled) |
| **Recommended** | `1` (enabled) |
| **Why it matters** | Required if you assign IPv6 prefixes to subscribers (dual-stack PPPoE). Even if you only use IPv4 today, enabling it now avoids a service disruption when you add IPv6 later. |
| **What happens without it** | IPv6 traffic from subscribers is silently dropped at the BNG. IPv4 continues to work. |
| **Config file** | `/etc/sysctl.d/99-accel-ppp.conf` |

---

### Reverse Path Filtering

#### `net.ipv4.conf.all.rp_filter` / `net.ipv4.conf.default.rp_filter`

| | |
|---|---|
| **What it does** | Controls how the kernel validates the source address of incoming packets. Three modes: `0` = disabled (no check), `1` = strict (packet must arrive on the interface the kernel would use to reach that source), `2` = loose (any route to the source address must exist in the routing table). |
| **Default** | `2` (loose) on Ubuntu 22.04+ |
| **Recommended** | `2` (loose) |
| **Why it matters** | **Strict mode (`1`) breaks PPPoE.** A subscriber's source IP (e.g. `10.90.16.31`) arrives on `ppp1`, but the kernel's route for that IP might point to a different `ppp` interface during brief routing transitions, or the route might be a blackhole aggregate (`blackhole 10.90.16.0/24`). Strict RPF drops these packets. Loose mode only checks that *some* route exists -- safe for a BNG with dynamic PPP interfaces. |
| **What happens if set to 1 (strict)** | Intermittent packet drops for subscribers, especially during session reconnects. Some subscribers work, others randomly lose connectivity. Very difficult to diagnose. |
| **What happens if set to 0 (disabled)** | No source address validation at all. A compromised subscriber device could spoof any source IP and the BNG would forward it. **Never use 0 on a BNG facing untrusted users.** |
| **Config file** | `/etc/sysctl.d/99-accel-ppp.conf` and `/etc/sysctl.d/10-network-security.conf` |

!!! danger "Never use `rp_filter=0` on a BNG"
    Disabling reverse path filtering on subscriber-facing interfaces allows IP spoofing. A single compromised CPE could impersonate any IP address on the internet. Loose mode (`2`) provides the right balance: it validates routes exist without breaking PPPoE's dynamic interface model.

---

### Socket Buffers

These control the maximum size of kernel send/receive buffers for network sockets. They affect every network application on the system, including accel-ppp's RADIUS client, the PPPoE kernel module, and dawos-agent's HTTP server.

#### `net.core.rmem_max`

| | |
|---|---|
| **What it does** | Maximum receive socket buffer size (in bytes) that any application can request with `setsockopt(SO_RCVBUF)`. |
| **Default** | `212992` (208 KB) |
| **Recommended** | `16777216` (16 MB) |
| **Why it matters** | A BNG handles traffic from hundreds or thousands of subscribers simultaneously. Each RADIUS accounting packet, each PPPoE control message, and each management API request uses a socket buffer. With the 208 KB default, high-traffic bursts cause buffer overflows, leading to dropped packets and retransmissions. 16 MB provides headroom for burst absorption. |
| **What happens without it** | Under load, RADIUS accounting packets are dropped (the `acct lost` counter in `accel-cmd show stat` increases). Subscribers may fail to authenticate during traffic spikes. |
| **Config file** | `/etc/sysctl.d/99-accel-ppp.conf` |

#### `net.core.wmem_max`

| | |
|---|---|
| **What it does** | Maximum send socket buffer size (in bytes). |
| **Default** | `212992` (208 KB) |
| **Recommended** | `16777216` (16 MB) |
| **Why it matters** | Same reasoning as `rmem_max` but for outgoing data. Affects RADIUS request throughput and bulk API responses. |
| **Config file** | `/etc/sysctl.d/99-accel-ppp.conf` |

!!! note "Memory impact"
    Setting `rmem_max` and `wmem_max` to 16 MB does **not** allocate 16 MB per socket. It sets the *maximum* a socket can request. Most sockets use much smaller buffers (typically 16-256 KB). The actual memory consumption depends on how many sockets are active and what buffer sizes they request. On a typical BNG with 500 sessions, expect ~10-50 MB total socket buffer usage.

---

### Network Device Backlog

#### `net.core.netdev_max_backlog`

| | |
|---|---|
| **What it does** | Maximum number of packets that can be queued at the network device driver level, waiting for the kernel to process them. When packets arrive faster than the kernel can process them, they queue here. |
| **Default** | `1000` |
| **Recommended** | `250000` |
| **Why it matters** | A BNG with hundreds of subscribers generates far more packets per second than a typical server. The default backlog of 1000 packets is exhausted in milliseconds under load. When the backlog overflows, packets are silently dropped at the driver level -- they never reach the kernel's network stack, so there are no ICMP errors or log messages. The only symptom is increased latency and packet loss for subscribers. |
| **What happens without it** | Under moderate load (200+ active subscribers), packet drops at the device level. `ethtool -S <iface>` shows increasing `rx_dropped` counters. Subscribers experience intermittent slowness that is very hard to diagnose because the drops happen before any firewall or routing. |
| **How to monitor** | `cat /proc/net/softnet_stat` -- the second column shows backlog overflow counts per CPU. Non-zero values mean you need a larger backlog. |
| **Config file** | `/etc/sysctl.d/99-accel-ppp.conf` |

---

### Socket Connection Backlog

#### `net.core.somaxconn`

| | |
|---|---|
| **What it does** | Maximum number of pending connections in the listen queue for any TCP socket. |
| **Default** | `4096` (modern kernels) or `128` (older kernels) |
| **Recommended** | `4096` |
| **Why it matters** | Affects the dawos-agent HTTP server (Uvicorn) and any management tools connecting to the BNG. If many API clients connect simultaneously (e.g., a monitoring system polling health endpoints from multiple dashboards), a small backlog causes connection refusals. |
| **Config file** | `/etc/sysctl.d/99-accel-ppp.conf` |

---

### File Descriptor Limit

#### `fs.file-max`

| | |
|---|---|
| **What it does** | System-wide maximum number of open file descriptors. Every open file, socket, pipe, and network interface consumes a file descriptor. |
| **Default** | Varies (~100,000 - 200,000 depending on RAM) |
| **Recommended** | `1000000` (1 million) |
| **Why it matters** | Each PPPoE session uses several file descriptors: the PPP interface, the PPPoE socket, RADIUS sockets, and internal pipes. At 1,000 subscribers, accel-ppp alone may use 5,000+ file descriptors. Add RADIUS connections, nftables sockets, dawos-agent's HTTP server, and system services -- the default can be exhausted on a large BNG. |
| **What happens without it** | When the limit is reached, new PPPoE sessions fail to establish (`accept: Too many open files` in logs). Existing sessions continue but new subscribers cannot connect. The dawos-agent API also stops responding because it cannot open new sockets. |
| **How to monitor** | `cat /proc/sys/fs/file-nr` -- shows `allocated / unused / maximum`. If `allocated` approaches `maximum`, increase the limit. |
| **Config file** | `/etc/sysctl.d/99-accel-ppp.conf` |

---

### ARP Table Sizing

A BNG has a unique network topology: every subscriber is a directly-connected host on a point-to-point interface. The kernel's ARP (neighbor) table must hold an entry for each one. The default table sizes are designed for a machine with a handful of neighbors, not thousands.

#### `net.ipv4.neigh.default.gc_thresh1`

| | |
|---|---|
| **What it does** | Minimum number of ARP entries the kernel keeps without triggering garbage collection. Below this threshold, the GC does not run. |
| **Default** | `128` |
| **Recommended** | `8192` |
| **Why it matters** | With the default of 128, the kernel runs ARP garbage collection constantly on a BNG with hundreds of subscribers, consuming CPU and occasionally evicting valid entries. Setting it to 8192 tells the kernel "don't bother cleaning up until we have at least 8192 entries." |
| **Config file** | `/etc/sysctl.d/99-accel-ppp.conf` |

#### `net.ipv4.neigh.default.gc_thresh2`

| | |
|---|---|
| **What it does** | Soft maximum for ARP entries. Above this, the kernel aggressively garbage-collects entries older than 5 seconds. |
| **Default** | `512` |
| **Recommended** | `32768` |
| **Why it matters** | A BNG with 1,000 subscribers easily exceeds 512 ARP entries. With the default, the kernel constantly evicts and re-learns ARP entries, causing brief connectivity interruptions and unnecessary ARP broadcast storms. |
| **Config file** | `/etc/sysctl.d/99-accel-ppp.conf` |

#### `net.ipv4.neigh.default.gc_thresh3`

| | |
|---|---|
| **What it does** | Hard maximum for ARP entries. The kernel **refuses** to add new entries above this limit, even if the host is reachable. |
| **Default** | `1024` |
| **Recommended** | `65536` |
| **Why it matters** | This is the most critical ARP parameter. When the hard limit is reached, the kernel logs `neighbour table overflow` and **drops packets** to new destinations. On a BNG, this means new subscribers cannot be reached even though their PPPoE session is established. |
| **What happens without it** | At ~1,000 subscribers, `dmesg` fills with `neighbour table overflow` errors. New sessions establish but cannot pass traffic. Existing sessions may also lose connectivity as their ARP entries expire and cannot be renewed. **This is a production-breaking issue.** |
| **How to monitor** | `ip -s neigh show \| wc -l` shows the current ARP table size. `dmesg \| grep "neighbour table overflow"` shows if the limit has been hit. |
| **Config file** | `/etc/sysctl.d/99-accel-ppp.conf` |

!!! tip "Scaling ARP limits"
    Set `gc_thresh3` to at least 2x your maximum expected subscriber count. For 5,000 subscribers, use `gc_thresh3=16384` minimum. The 65,536 value provides headroom up to ~30,000 subscribers.

---

### Connection Tracking (Conntrack)

If your BNG performs NAT (SNAT/masquerade for subscriber traffic), every connection passing through nftables is tracked in the conntrack table. This is how the kernel knows which return packets belong to which subscriber.

#### `net.netfilter.nf_conntrack_max`

| | |
|---|---|
| **What it does** | Maximum number of concurrent connection tracking entries. Each TCP connection, UDP flow, ICMP exchange, and DNS query consumes one entry. |
| **Default** | `65536` (65k) |
| **Recommended** | `1048576` (1 million) |
| **Why it matters** | A single subscriber browsing the web typically has 50-200 concurrent connections (HTTP/2 multiplexing, CDN connections, background requests, DNS queries). At 500 subscribers, you need 25,000-100,000 conntrack entries just for web browsing. Add streaming video, gaming, and background app traffic, and 65k is exhausted quickly. When the conntrack table is full, **new connections are dropped silently** -- the kernel cannot create a tracking entry for them. |
| **What happens without it** | Subscribers report "internet is slow" or "some websites don't load." `dmesg` shows `nf_conntrack: table full, dropping packet`. The issue is intermittent because it depends on how many subscribers are active at once. Often misdiagnosed as an upstream bandwidth problem. |
| **Memory impact** | Each conntrack entry uses ~320 bytes of kernel memory. 1 million entries = ~320 MB. On a 2 GB RAM system, this is significant -- size it to your actual needs. For 500 subscribers, 262144 (256k) is usually sufficient. For 2,000+, use 1M. |
| **How to monitor** | `cat /proc/sys/net/netfilter/nf_conntrack_count` shows current entries. `cat /proc/sys/net/netfilter/nf_conntrack_max` shows the limit. When `count` approaches `max`, increase the limit or reduce timeouts. The DawOS Agent endpoint `GET /api/v1/conntrack/status` exposes both values via the API. |
| **Config file** | `/etc/sysctl.d/99-accel-ppp.conf` |

#### `net.netfilter.nf_conntrack_tcp_timeout_established`

| | |
|---|---|
| **What it does** | How many seconds to keep an established TCP connection in the conntrack table after the last packet. |
| **Default** | `432000` (5 days) |
| **Recommended** | `43200` (12 hours) |
| **Why it matters** | The default of 5 days is designed for firewalls protecting a small number of servers with long-lived connections. On a BNG doing NAT for hundreds of subscribers, stale entries from connections that were never properly closed (client crashed, network timeout, mobile device switched to cellular) accumulate for 5 days before being reclaimed. This wastes conntrack slots. 12 hours is long enough for any legitimate persistent connection (websockets, SSH, VPN) and short enough to reclaim stale entries efficiently. |
| **What happens without it** | The conntrack table fills up faster than necessary because dead connections occupy slots for 5 days. Combined with a low `nf_conntrack_max`, this causes the "table full, dropping packet" issue described above. |
| **Config file** | `/etc/sysctl.d/99-accel-ppp.conf` |

#### `net.netfilter.nf_conntrack_buckets`

| | |
|---|---|
| **What it does** | Size of the hash table used to index conntrack entries. Each "bucket" is a linked list of entries that hash to the same slot. More buckets = shorter lists = faster lookups. |
| **Default** | `nf_conntrack_max / 8` (e.g., 8192 when max is 65536) |
| **Recommended** | `262144` (nf_conntrack_max / 4) |
| **Why it matters** | When a packet arrives, the kernel must look up its conntrack entry by hashing the 5-tuple (src IP, dst IP, src port, dst port, protocol). If the hash table is too small, many entries collide into the same bucket, turning the lookup into a linear scan through a long linked list. At 1 million conntrack entries with only 8192 buckets, each bucket averages 122 entries — every packet traverses a list of 122 entries to find its match. With 262144 buckets, each bucket averages only 4 entries. |
| **What happens without it** | High CPU usage in the `nf_conntrack` kernel path under load. `perf top` shows `__nf_conntrack_find_get` consuming significant CPU. Subscribers experience increased latency because every packet must walk a long hash chain. |
| **How to set** | On some kernels, this parameter is read-only via sysctl and must be set via the module parameter: `echo 262144 > /sys/module/nf_conntrack/parameters/hashsize`. To make it persistent, add `options nf_conntrack hashsize=262144` to `/etc/modprobe.d/nf_conntrack.conf`. |
| **Config file** | `/etc/sysctl.d/99-accel-ppp.conf` (if writable) or `/etc/modprobe.d/nf_conntrack.conf` |

!!! tip "Hash table sizing rule"
    Use `nf_conntrack_buckets = nf_conntrack_max / 4` for optimal performance. Each bucket uses 8 bytes, so 262144 buckets = 2 MB — negligible compared to the conntrack entries themselves.

#### `net.netfilter.nf_conntrack_tcp_timeout_fin_wait`

| | |
|---|---|
| **What it does** | How many seconds to keep a TCP connection in FIN_WAIT state in the conntrack table. This state occurs when one side has sent a FIN but the other side hasn't acknowledged the close yet. |
| **Default** | `120` (2 minutes) |
| **Recommended** | `30` |
| **Why it matters** | When a subscriber disconnects abruptly (CPE reboot, cable pulled, power loss), the TCP connections on the BNG's NAT table enter FIN_WAIT and sit there for 2 minutes. With hundreds of subscribers reconnecting after a power outage, thousands of stale FIN_WAIT entries accumulate. Reducing to 30 seconds reclaims these entries 4x faster. |
| **Config file** | `/etc/sysctl.d/99-accel-ppp.conf` |

#### `net.netfilter.nf_conntrack_udp_timeout`

| | |
|---|---|
| **What it does** | How many seconds to keep a single-packet UDP flow in the conntrack table. A "single-packet" flow is one where only one packet has been seen (e.g., a DNS query before the response arrives). |
| **Default** | `30` |
| **Recommended** | `10` |
| **Why it matters** | Every DNS query from every subscriber creates a conntrack entry. A typical subscriber generates 10-50 DNS queries per minute. With 500 subscribers, that's 5,000-25,000 DNS conntrack entries, each living for 30 seconds. Reducing to 10 seconds is still far longer than any DNS response time (<1 second) and reclaims entries 3x faster. This is especially important on BNGs that also act as DNS forwarders (dnsmasq). |
| **Config file** | `/etc/sysctl.d/99-accel-ppp.conf` |

#### `net.netfilter.nf_conntrack_udp_timeout_stream`

| | |
|---|---|
| **What it does** | How many seconds to keep a bidirectional UDP stream (where packets have been seen in both directions) in the conntrack table. Applies to streaming media, VoIP, gaming, and any established UDP session. |
| **Default** | `120` (2 minutes) |
| **Recommended** | `60` (1 minute) |
| **Why it matters** | Bidirectional UDP flows include VoIP calls (SIP/RTP), online gaming, and video streaming. These are active sessions where 60 seconds of inactivity genuinely means the flow has ended. The default 120 seconds keeps dead flows around twice as long as necessary, wasting conntrack entries. |
| **Config file** | `/etc/sysctl.d/99-accel-ppp.conf` |

#### `net.netfilter.nf_conntrack_icmp_timeout`

| | |
|---|---|
| **What it does** | How many seconds to keep an ICMP flow (ping request/reply pair) in the conntrack table. |
| **Default** | `30` |
| **Recommended** | `10` |
| **Why it matters** | ICMP exchanges (ping) complete in milliseconds. The default 30-second timeout keeps the conntrack entry alive for thousands of times longer than the actual exchange. On a BNG where subscribers and monitoring systems send continuous pings, this wastes conntrack entries. 10 seconds provides ample time for even high-latency ping responses. |
| **Config file** | `/etc/sysctl.d/99-accel-ppp.conf` |

!!! info "Flushing conntrack"
    DawOS Agent provides `POST /api/v1/conntrack/flush` to clear the entire conntrack table. This is useful during maintenance or when the table is nearly full. Active connections are re-tracked automatically on the next packet -- subscribers experience a brief (~1 second) interruption as NAT state is rebuilt.

---

### Network Security Hardening

These parameters harden the BNG against network-layer attacks. They are placed in a separate file (`10-network-security.conf`) for visibility -- security auditors can review them independently of performance tuning.

#### `net.ipv4.conf.all.send_redirects` / `net.ipv4.conf.default.send_redirects`

| | |
|---|---|
| **What it does** | Controls whether the kernel sends ICMP Redirect messages when it routes a packet out the same interface it arrived on. |
| **Default** | `1` (enabled) |
| **Recommended** | `0` (disabled) |
| **Why it matters** | ICMP redirects tell a host "there's a better route -- send future packets to this other gateway instead." On a BNG, this is never appropriate: the BNG **is** the only gateway for all subscribers. Sending redirects could cause a subscriber's CPE to cache a redirect to another subscriber's PPP IP, causing traffic to be misrouted. More importantly, ICMP redirects are a well-known MITM attack vector -- an attacker could craft redirect messages to divert traffic through a malicious host. |
| **What happens without this** | Normally harmless on point-to-point PPP interfaces (redirects are rarely triggered on them), but the kernel may send redirects on the management or uplink interfaces. Disabling it is a defense-in-depth measure and a common CIS benchmark requirement. |
| **Config file** | `/etc/sysctl.d/10-network-security.conf` |

#### `net.ipv4.conf.all.log_martians` / `net.ipv4.conf.default.log_martians`

| | |
|---|---|
| **What it does** | Logs packets with impossible source addresses (martian packets) to the kernel log. A "martian" is a packet whose source address is reserved (0.0.0.0, 127.x.x.x, 224.x.x.x) or has no valid route back. |
| **Default** | `0` (disabled) |
| **Recommended** | `1` (enabled) |
| **Why it matters** | On a BNG, martian packets from subscriber-facing interfaces indicate either: (a) a misconfigured CPE, (b) a compromised device attempting IP spoofing, or (c) a routing loop. Logging them provides early warning of security issues and misconfigurations. Without logging, these packets are silently dropped and the operator has no visibility into what's happening. |
| **Log output** | Martians appear in `dmesg` and `journalctl -k` as: `IPv4: martian source X.X.X.X from Y.Y.Y.Y, on dev pppN`. |
| **Caution** | On a large BNG with many misconfigured CPEs, martian logging can generate significant log volume. Monitor `/var/log` disk usage after enabling. If log volume is excessive, consider disabling martian logging on the subscriber-facing interfaces only: `net.ipv4.conf.ppp*.log_martians=0`. |
| **Config file** | `/etc/sysctl.d/10-network-security.conf` |

#### `net.ipv4.conf.all.accept_redirects` / `net.ipv4.conf.default.accept_redirects`

| | |
|---|---|
| **What it does** | Controls whether the kernel accepts ICMP Redirect messages and updates its routing table accordingly. |
| **Default** | `1` (enabled) |
| **Recommended** | `0` (disabled) |
| **Why it matters** | We already disable *sending* redirects, but the BNG must also refuse to *accept* them. A compromised subscriber device could send crafted ICMP Redirect messages to the BNG, telling it "route traffic for IP X.X.X.X through me instead." If accepted, the BNG would redirect other subscribers' traffic through the attacker — a classic man-in-the-middle attack. On a BNG, the routing table is authoritative and should never be modified by ICMP messages from untrusted networks. |
| **What happens without it** | An attacker on the subscriber network could manipulate the BNG's routing table, causing traffic destined for one subscriber to be routed through another subscriber's device. This is a **critical security vulnerability**. |
| **Config file** | `/etc/sysctl.d/10-network-security.conf` |

#### `net.ipv6.conf.all.accept_redirects` / `net.ipv6.conf.default.accept_redirects`

| | |
|---|---|
| **What it does** | Same as the IPv4 variant but for ICMPv6 Redirect messages. |
| **Default** | `1` (enabled) |
| **Recommended** | `0` (disabled) |
| **Why it matters** | IPv6 Neighbor Discovery Protocol (NDP) uses ICMPv6 redirects. The same man-in-the-middle risk applies. On a dual-stack BNG, both IPv4 and IPv6 redirect acceptance must be disabled. |
| **Config file** | `/etc/sysctl.d/10-network-security.conf` |

#### `net.ipv4.conf.all.secure_redirects` / `net.ipv4.conf.default.secure_redirects`

| | |
|---|---|
| **What it does** | When `accept_redirects=1`, this further restricts accepted redirects to only those from the default gateway. "Secure" means the redirect source must be a known gateway — but this still allows a compromised gateway to redirect traffic. |
| **Default** | `1` (enabled) |
| **Recommended** | `0` (disabled) |
| **Why it matters** | Even "secure" redirects from the default gateway should not modify the BNG's routing table. The BNG's routes are set by the operator (static routes, OSPF, BGP via FRR). No ICMP message should override them. Setting this to `0` alongside `accept_redirects=0` provides defense-in-depth. |
| **Config file** | `/etc/sysctl.d/10-network-security.conf` |

#### `net.ipv4.conf.all.accept_source_route` / `net.ipv4.conf.default.accept_source_route`

| | |
|---|---|
| **What it does** | Controls whether the kernel accepts IP packets with the Source Route option set. Source routing allows the sender to specify the exact path a packet should take through the network, overriding normal routing decisions. |
| **Default** | `0` (disabled on most modern distros) |
| **Recommended** | `0` (disabled) |
| **Why it matters** | Source-routed packets are a classic firewall bypass technique. An attacker can craft a packet that routes through a specific path, potentially bypassing ACLs and firewall rules that only apply to certain interfaces. On a BNG, subscriber traffic should always follow the BNG's routing table — never a path dictated by the subscriber's device. While most modern distributions disable this by default, explicitly setting it ensures it stays disabled even after OS upgrades. |
| **Config file** | `/etc/sysctl.d/10-network-security.conf` |

#### `net.ipv6.conf.all.accept_source_route` / `net.ipv6.conf.default.accept_source_route`

| | |
|---|---|
| **What it does** | Same as IPv4 variant but for IPv6 Routing Header Type 0 (RH0), which allows source routing in IPv6. |
| **Default** | `0` (disabled on most modern distros) |
| **Recommended** | `0` (disabled) |
| **Why it matters** | IPv6 RH0 was deprecated in RFC 5095 due to amplification attack risks. A single packet with a routing header can be bounced between two nodes, amplifying traffic. Explicitly disabling it on the BNG prevents any RH0 packets from being processed. |
| **Config file** | `/etc/sysctl.d/10-network-security.conf` |

#### `net.ipv4.tcp_syncookies`

| | |
|---|---|
| **What it does** | Enables TCP SYN cookies as a fallback when the SYN backlog queue is full. Instead of allocating memory for half-open connections, the kernel encodes connection state in the SYN-ACK sequence number. |
| **Default** | `1` (enabled on most modern distros) |
| **Recommended** | `1` (enabled) |
| **Why it matters** | A BNG faces thousands of subscriber devices, some of which may be compromised and used to launch SYN flood attacks against the BNG's management interface (port 8470) or against other subscribers' services behind NAT. Without SYN cookies, a SYN flood exhausts the SYN backlog and prevents legitimate TCP connections — the dawos-agent API becomes unreachable. With SYN cookies, the kernel handles SYN floods without allocating per-connection memory, maintaining service availability. |
| **What happens without it** | During a SYN flood, `ss -s` shows thousands of `SYN-RECV` sockets. New legitimate connections (including dawos-agent API requests and SSH) are refused. The BNG is still forwarding subscriber traffic, but the operator cannot manage it remotely. |
| **Config file** | `/etc/sysctl.d/10-network-security.conf` |

!!! warning "SYN cookies trade-off"
    SYN cookies sacrifice TCP options negotiation (window scaling, selective ACK, timestamps) during a flood. This slightly reduces throughput for connections established while under attack. Once the flood stops, new connections negotiate full TCP options normally. The protection benefit far outweighs this minor trade-off.

#### `net.ipv4.icmp_echo_ignore_broadcasts`

| | |
|---|---|
| **What it does** | When enabled, the kernel does not respond to ICMP echo requests (pings) sent to broadcast or multicast addresses. |
| **Default** | `1` (enabled on most modern distros) |
| **Recommended** | `1` (enabled) |
| **Why it matters** | A **Smurf attack** works by sending ICMP echo requests to a broadcast address with a spoofed source IP (the victim's IP). Every host on the broadcast domain responds, flooding the victim with echo replies. A BNG connected to multiple subnets could amplify such an attack massively. Ignoring broadcast pings eliminates the BNG as a Smurf amplifier. |
| **Config file** | `/etc/sysctl.d/10-network-security.conf` |

#### `net.ipv4.icmp_ignore_bogus_error_responses`

| | |
|---|---|
| **What it does** | When enabled, the kernel ignores ICMP error responses that violate RFC 1122 (e.g., ICMP responses to broadcast addresses, ICMP errors about ICMP errors). |
| **Default** | `1` (enabled on most modern distros) |
| **Recommended** | `1` (enabled) |
| **Why it matters** | Many consumer CPE devices (cheap routers, ONTs) send malformed ICMP error messages. Without this setting, each bogus ICMP error is logged to the kernel log, consuming disk I/O and potentially filling the log partition. On a BNG with hundreds of CPEs, this can generate thousands of bogus error log entries per day. Enabling this setting silently ignores them. |
| **Config file** | `/etc/sysctl.d/10-network-security.conf` |

#### `net.core.default_qdisc`

| | |
|---|---|
| **What it does** | Sets the default packet scheduler (queueing discipline) for all network interfaces. The packet scheduler determines how outgoing packets are queued and which packets are sent first when the link is congested. |
| **Default** | `pfifo_fast` (simple FIFO with 3 priority bands) |
| **Recommended** | `fq_codel` (Fair Queue Controlled Delay) |
| **Why it matters** | `pfifo_fast` is a simple first-in-first-out queue. When a link is congested, it fills up and every flow suffers equally. A single subscriber downloading a large file can cause latency spikes for all other subscribers sharing the same uplink. **Bufferbloat** is the phenomenon where large buffers in the network path absorb packets during congestion, causing latency to spike from milliseconds to seconds. |
| **What `fq_codel` does** | Two things: (1) **Fair Queuing** -- creates a separate queue per flow (identified by source/destination IP+port). A heavy downloader gets its own queue and cannot starve a VoIP call or a gaming session. (2) **CoDel** (Controlled Delay) -- monitors queue residence time. If packets sit in the queue too long (indicating congestion), CoDel probabilistically drops packets to signal the sender to slow down, keeping latency low. |
| **Real-world impact** | Without `fq_codel`: a subscriber downloading at full speed causes 200-500ms latency for other subscribers. With `fq_codel`: latency stays under 10-20ms even during congestion. Gaming and VoIP remain usable while downloads proceed at full speed. |
| **Config file** | `/etc/sysctl.d/10-bufferbloat.conf` |

!!! tip "Per-subscriber rate limiting"
    `fq_codel` handles fairness between flows on a single interface. For per-subscriber bandwidth limits, accel-ppp uses `tc` (traffic control) with `tbf` (token bucket filter) or `htb` (hierarchical token bucket) qdiscs on each `ppp` interface. DawOS Agent manages these via the `GET /api/v1/traffic/ratelimits` and `POST /api/v1/traffic/ratelimit` endpoints.

---

### TCP Performance

These parameters optimize TCP behavior for a BNG that performs NAT on behalf of hundreds or thousands of subscribers. They reduce resource consumption from stale connections and improve throughput on lossy subscriber links.

#### `net.ipv4.tcp_fin_timeout`

| | |
|---|---|
| **What it does** | How many seconds to wait for a final FIN-ACK after the local side has closed a TCP connection. During this time, the socket remains in `FIN_WAIT_2` state, consuming a conntrack entry and kernel memory. |
| **Default** | `60` (1 minute) |
| **Recommended** | `30` |
| **Why it matters** | When a subscriber disconnects (CPE reboot, cable pull, power loss), their TCP connections on the BNG's NAT table enter `FIN_WAIT_2` — the BNG sent a FIN but the subscriber's device never responded. With the default 60-second timeout, each dead connection occupies a conntrack slot for a full minute. During a mass reconnection event (power outage recovery), hundreds of subscribers disconnect simultaneously, creating thousands of stale `FIN_WAIT_2` entries. Reducing to 30 seconds reclaims these entries twice as fast. |
| **Config file** | `/etc/sysctl.d/99-accel-ppp.conf` |

#### `net.ipv4.tcp_tw_reuse`

| | |
|---|---|
| **What it does** | Allows the kernel to reuse sockets in `TIME_WAIT` state for new outgoing connections, provided the TCP timestamp is newer than the last packet on the old connection. |
| **Default** | `2` (enabled for loopback only, kernel 5.17+) or `0` (disabled, older kernels) |
| **Recommended** | `1` (enabled for all connections) |
| **Why it matters** | When a BNG performs SNAT (masquerade) for subscriber traffic, it assigns a source port from the ephemeral port range (32768-60999 = ~28,000 ports) for each outgoing connection. When a connection closes, the source port enters `TIME_WAIT` for 60 seconds and cannot be reused. If many subscribers connect to the same destination (e.g., YouTube, Netflix, Google), the BNG can exhaust available source ports. With `tcp_tw_reuse=1`, ports in `TIME_WAIT` can be immediately reused for new connections to the same destination, preventing source port exhaustion. |
| **What happens without it** | Under heavy NAT load, `ss -s` shows thousands of `TIME_WAIT` sockets. New outgoing connections fail with `EADDRNOTAVAIL` (no available source ports). Subscribers see "connection refused" or timeouts when accessing popular websites. |
| **How to monitor** | `ss -s | grep TIME-WAIT` — if the count exceeds 20,000, you need `tcp_tw_reuse=1` or a larger ephemeral port range. |
| **Config file** | `/etc/sysctl.d/99-accel-ppp.conf` |

!!! note "tcp_tw_reuse vs tcp_tw_recycle"
    `tcp_tw_recycle` was removed from the kernel in version 4.12 because it broke connections behind NAT. **Never** use `tcp_tw_recycle`. Only `tcp_tw_reuse` is safe — it uses TCP timestamps to ensure the reused port doesn't cause packet confusion.

#### `net.ipv4.tcp_no_metrics_save`

| | |
|---|---|
| **What it does** | When disabled (`0`, default), the kernel caches TCP performance metrics (RTT, CWND, SSTHRESH) per destination IP. When a new connection is established to the same destination, it inherits the cached metrics. When enabled (`1`), each connection starts fresh with default TCP parameters. |
| **Default** | `0` (caching enabled) |
| **Recommended** | `1` (caching disabled) |
| **Why it matters** | On a BNG, the kernel sees traffic from hundreds of subscriber IPs to the same destination (e.g., many subscribers accessing `8.8.8.8`). If one subscriber's connection experiences packet loss, the kernel caches a low congestion window for that destination. When the next subscriber connects to the same destination through NAT, it inherits the degraded metrics — even though this subscriber's link is perfectly fine. This "metric poisoning" causes unexplained slowness for random subscribers. Disabling metric caching ensures each connection performs its own TCP slow start and congestion control independently. |
| **Config file** | `/etc/sysctl.d/99-accel-ppp.conf` |

#### `net.ipv4.tcp_congestion_control`

| | |
|---|---|
| **What it does** | Selects the TCP congestion control algorithm used for all TCP connections. The congestion control algorithm determines how fast TCP ramps up its sending rate and how it responds to packet loss. |
| **Default** | `cubic` |
| **Recommended** | `bbr` |
| **Why it matters** | **CUBIC** (the default) is loss-based: it increases throughput until a packet is lost, then backs off dramatically. On a BNG where subscriber links may have 0.1-1% natural packet loss (DSL, wireless CPE, long copper runs), CUBIC interprets every lost packet as congestion and throttles throughput unnecessarily. **BBR** (Bottleneck Bandwidth and Round-trip time), developed by Google, is model-based: it continuously estimates the bottleneck bandwidth and minimum RTT, adjusting sending rate to match the actual link capacity without relying on packet loss as a congestion signal. |
| **Real-world impact** | On a subscriber link with 0.5% packet loss: CUBIC achieves ~30% of link capacity, BBR achieves ~95%. Google reports 2-25x throughput improvement on lossy links after deploying BBR. For ISP subscribers on imperfect last-mile connections, BBR can significantly improve download speeds. |
| **Prerequisite** | BBR requires the `fq` or `fq_codel` qdisc (already set via `net.core.default_qdisc=fq_codel`). To verify: `tc qdisc show dev ens18 | grep fq`. |
| **How to enable** | `modprobe tcp_bbr && sysctl net.ipv4.tcp_congestion_control=bbr`. To verify: `sysctl net.ipv4.tcp_congestion_control` should show `bbr`. |
| **Config file** | `/etc/sysctl.d/99-accel-ppp.conf` |

!!! info "BBR affects BNG-originated traffic only"
    The TCP congestion control setting affects connections **originated by the BNG** (dawos-agent API responses, RADIUS packets, management SSH sessions) and connections **terminated at the BNG** (if running local services). It does **not** affect subscriber-to-internet traffic that the BNG merely forwards/NATs — that traffic uses the congestion control algorithm of the subscriber's device and the remote server.

---

### Memory Management

#### `vm.min_free_kbytes`

| | |
|---|---|
| **What it does** | Minimum amount of memory (in KB) the kernel keeps free at all times. When free memory drops below this threshold, the kernel starts reclaiming memory more aggressively from page cache and other sources. |
| **Default** | Calculated based on total RAM (~67 MB on a 2 GB system) |
| **Recommended** | `131072` (128 MB) |
| **Why it matters** | A BNG handles burst traffic patterns: when many subscribers come online simultaneously (morning, after a power outage), the kernel must allocate thousands of `sk_buff` structures (socket buffers) for incoming packets. Each `sk_buff` is ~240 bytes plus the packet data. A burst of 10,000 packets requires ~4 MB of immediately-available memory. If the kernel's free memory is too low, it must invoke the OOM (Out of Memory) killer to free memory — and the OOM killer may choose to kill accel-ppp or dawos-agent, causing a service outage. Setting `min_free_kbytes=131072` ensures 128 MB is always available for burst allocation. |
| **What happens without it** | During traffic bursts, `dmesg` shows `page allocation failure` or `Out of memory: Kill process`. The OOM killer selects the process using the most memory — which is often accel-ppp (the process you least want killed). All PPPoE sessions drop simultaneously. |
| **Memory cost** | The 128 MB is not wasted — it's held as free pages that the kernel uses for network buffers, file system cache, and other transient allocations. It simply prevents the kernel from using this memory for page cache that would need to be reclaimed under pressure. |
| **How to monitor** | `cat /proc/meminfo | grep MemFree` — should always be above `min_free_kbytes`. If it frequently drops to exactly `min_free_kbytes`, the system is under memory pressure and may need more RAM. |
| **Config file** | `/etc/sysctl.d/99-accel-ppp.conf` |

---

### Process File Descriptor Limits

The `fs.file-max` sysctl sets the **system-wide** file descriptor limit, but each process also has its own per-process limit controlled by `ulimit` and systemd's `LimitNOFILE`. Both must be raised for a BNG.

#### Per-process `nofile` limit

| | |
|---|---|
| **What it does** | Maximum number of file descriptors a single process can open. Controlled by `/etc/security/limits.conf` (for login sessions) and systemd's `LimitNOFILE` (for services). |
| **Default** | `1024` (soft) / `1048576` (hard, kernel 5.10+) |
| **Recommended** | `65536` for both soft and hard limits |
| **Why it matters** | Even though `fs.file-max` allows 1 million file descriptors system-wide, each process is individually limited to 1024 by default. accel-ppp with 500 sessions may need 2,000+ file descriptors (2 per PPP session + RADIUS sockets + internal pipes). dawos-agent needs file descriptors for its HTTP server, subprocess pipes, and log files. At the default 1024 limit, both processes can hit `Too many open files` errors. |
| **What happens without it** | accel-ppp logs `accept: Too many open files` and refuses new PPPoE sessions. dawos-agent returns HTTP 500 for requests that need subprocess execution. The system-wide `fs.file-max` is nowhere near exhausted, making this confusing to diagnose. |
| **How to configure** | See the [Quick Apply](#quick-apply) section for the complete setup. Both `/etc/security/limits.d/dawos.conf` and systemd service overrides are needed — `limits.conf` does not apply to systemd-managed services. |
| **How to verify** | For dawos-agent: `cat /proc/$(pgrep -f dawos)/limits | grep "Max open files"`. For accel-ppp: `cat /proc/$(pgrep accel-pppd)/limits | grep "Max open files"`. Both should show `65536`. |

---

## Scaling Guide

The recommended values above are optimized for a BNG with **500-2,000 subscribers**. For smaller or larger deployments, adjust accordingly:

| Parameter | < 200 subs | 500-2,000 subs | 2,000-10,000 subs | 10,000+ subs |
|-----------|:----------:|:--------------:|:-----------------:|:------------:|
| `nf_conntrack_max` | 262144 | 1048576 | 2097152 | 4194304 |
| `nf_conntrack_buckets` | 65536 | 262144 | 524288 | 1048576 |
| `nf_conntrack_tcp_timeout_established` | 43200 | 43200 | 21600 | 10800 |
| `neigh.gc_thresh3` | 16384 | 65536 | 131072 | 262144 |
| `netdev_max_backlog` | 100000 | 250000 | 500000 | 1000000 |
| `rmem_max` / `wmem_max` | 8388608 | 16777216 | 33554432 | 67108864 |
| `file-max` | 500000 | 1000000 | 2000000 | 4000000 |
| `vm.min_free_kbytes` | 65536 | 131072 | 262144 | 524288 |
| `LimitNOFILE` | 32768 | 65536 | 131072 | 262144 |

**Memory impact of conntrack sizing:**

| `nf_conntrack_max` | Entries | Kernel memory |
|:-------------------:|:-------:|:-------------:|
| 262144 | 256k | ~80 MB |
| 1048576 | 1M | ~320 MB |
| 2097152 | 2M | ~640 MB |
| 4194304 | 4M | ~1.3 GB |

For large deployments (10,000+ subscribers), ensure the BNG has at least 8 GB RAM to accommodate the conntrack table, ARP table, and per-session state.

---

## Verification

After applying the kernel tuning, verify all values are active:

```bash
#!/usr/bin/env bash
# verify-kernel-tuning.sh — Check all BNG kernel parameters

echo "=== Packet Forwarding ==="
sysctl net.ipv4.ip_forward
sysctl net.ipv6.conf.all.forwarding

echo ""
echo "=== Reverse Path Filtering ==="
sysctl net.ipv4.conf.all.rp_filter
sysctl net.ipv4.conf.default.rp_filter

echo ""
echo "=== Socket Buffers ==="
sysctl net.core.rmem_max
sysctl net.core.wmem_max

echo ""
echo "=== Network Backlog ==="
sysctl net.core.netdev_max_backlog
sysctl net.core.somaxconn

echo ""
echo "=== File Descriptors ==="
sysctl fs.file-max
cat /proc/sys/fs/file-nr | awk '{printf "  allocated/max: %s/%s (%.1f%% used)\n", $1, $3, ($1/$3)*100}'

echo ""
echo "=== ARP Table ==="
sysctl net.ipv4.neigh.default.gc_thresh1
sysctl net.ipv4.neigh.default.gc_thresh2
sysctl net.ipv4.neigh.default.gc_thresh3
echo "  current ARP entries: $(ip -s neigh show | wc -l)"

echo ""
echo "=== Connection Tracking ==="
sysctl net.netfilter.nf_conntrack_max
sysctl net.netfilter.nf_conntrack_buckets 2>/dev/null || \
  echo "  buckets (module param): $(cat /sys/module/nf_conntrack/parameters/hashsize 2>/dev/null || echo 'N/A')"
sysctl net.netfilter.nf_conntrack_tcp_timeout_established
sysctl net.netfilter.nf_conntrack_tcp_timeout_fin_wait 2>/dev/null
sysctl net.netfilter.nf_conntrack_udp_timeout
sysctl net.netfilter.nf_conntrack_udp_timeout_stream
sysctl net.netfilter.nf_conntrack_icmp_timeout
COUNT=$(cat /proc/sys/net/netfilter/nf_conntrack_count 2>/dev/null || echo "N/A")
MAX=$(cat /proc/sys/net/netfilter/nf_conntrack_max 2>/dev/null || echo "N/A")
echo "  current entries: ${COUNT}/${MAX}"

echo ""
echo "=== TCP Performance ==="
sysctl net.ipv4.tcp_fin_timeout
sysctl net.ipv4.tcp_tw_reuse
sysctl net.ipv4.tcp_no_metrics_save
sysctl net.ipv4.tcp_congestion_control
echo "  TIME_WAIT count: $(ss -s 2>/dev/null | grep -oP 'timewait \K[0-9]+' || echo 'N/A')"

echo ""
echo "=== Security Hardening ==="
sysctl net.ipv4.conf.all.send_redirects
sysctl net.ipv4.conf.all.accept_redirects
sysctl net.ipv4.conf.all.secure_redirects
sysctl net.ipv4.conf.all.accept_source_route
sysctl net.ipv6.conf.all.accept_redirects
sysctl net.ipv6.conf.all.accept_source_route
sysctl net.ipv4.conf.all.log_martians
sysctl net.ipv4.tcp_syncookies
sysctl net.ipv4.icmp_echo_ignore_broadcasts
sysctl net.ipv4.icmp_ignore_bogus_error_responses

echo ""
echo "=== Packet Scheduler ==="
sysctl net.core.default_qdisc

echo ""
echo "=== Memory Management ==="
sysctl vm.min_free_kbytes
FREE_KB=$(grep MemFree /proc/meminfo | awk '{print $2}')
MIN_KB=$(sysctl -n vm.min_free_kbytes)
echo "  current free: ${FREE_KB} KB (min: ${MIN_KB} KB)"

echo ""
echo "=== Process Limits ==="
DAWOS_PID=$(pgrep -f dawos 2>/dev/null)
ACCEL_PID=$(pgrep accel-pppd 2>/dev/null)
if [ -n "$DAWOS_PID" ]; then
  echo "  dawos-agent (PID ${DAWOS_PID}):"
  grep "Max open files" /proc/${DAWOS_PID}/limits 2>/dev/null | awk '{printf "    nofile: soft=%s hard=%s\n", $4, $5}'
fi
if [ -n "$ACCEL_PID" ]; then
  echo "  accel-ppp (PID ${ACCEL_PID}):"
  grep "Max open files" /proc/${ACCEL_PID}/limits 2>/dev/null | awk '{printf "    nofile: soft=%s hard=%s\n", $4, $5}'
fi

echo ""
echo "=== Softnet Backlog Drops (should be 0) ==="
awk '{print "  CPU" NR-1 ": dropped=" $2 " time_squeeze=" $3}' /proc/net/softnet_stat | head -4
```

### Expected Output

All values should match the recommended settings. Key things to watch:

- `ip_forward = 1` -- if `0`, subscribers cannot reach the internet
- `nf_conntrack_count` should be well below `nf_conntrack_max` -- if it's above 80%, increase the limit or reduce timeouts
- `tcp_syncookies = 1` -- if `0`, the BNG is vulnerable to SYN flood attacks
- `accept_redirects = 0` and `accept_source_route = 0` -- if `1`, the BNG is vulnerable to routing manipulation
- `tcp_congestion_control = bbr` -- if `cubic`, throughput may be suboptimal on lossy subscriber links
- `TIME_WAIT count` should be under 20,000 -- if higher, ensure `tcp_tw_reuse=1` is active
- `softnet_stat` dropped column should be `0` -- non-zero means `netdev_max_backlog` needs to be larger
- `file-nr` usage should be below 50% -- if it's above 80%, increase `file-max`
- Process `nofile` limits should show `65536` -- if `1024`, the systemd override is not applied

---

## Monitoring via DawOS Agent API

Several DawOS Agent endpoints expose kernel tuning-related information:

| Endpoint | What it shows |
|----------|---------------|
| `GET /api/v1/conntrack/status` | Current conntrack count, max, and usage percentage |
| `GET /api/v1/conntrack/timeouts` | Active conntrack timeout values (TCP, UDP, ICMP) |
| `POST /api/v1/conntrack/flush` | Flush the conntrack table (emergency use) |
| `GET /api/v1/firewall/sysctl` | All active sysctl values related to networking |
| `GET /api/v1/sessions/stats` | Active session count (correlates with ARP table size) |
| `GET /api/v1/network/throughput` | Per-interface traffic (high throughput = need larger buffers) |
| `GET /api/v1/diagnostics` | System health check including kernel parameter validation |

---

## Reference: Production BNG Configuration

These are the actual kernel tuning files deployed on a production BNG (accel-2, `192.168.212.226`) serving real ISP subscribers since June 2024.

!!! warning "Gap analysis"
    The production configuration below covers the **essential** BNG tuning but is missing several parameters recommended in this guide. See [Recommended Additions](#recommended-additions-for-production) below for what should be added.

### `/etc/sysctl.d/99-accel-ppp.conf`

```ini
net.ipv4.ip_forward=1
net.ipv6.conf.all.forwarding=1
net.ipv4.conf.all.rp_filter=2
net.ipv4.conf.default.rp_filter=2
net.core.rmem_max=16777216
net.core.wmem_max=16777216
net.core.netdev_max_backlog=250000
net.core.somaxconn=4096
fs.file-max=1000000
net.ipv4.neigh.default.gc_thresh1=8192
net.ipv4.neigh.default.gc_thresh2=32768
net.ipv4.neigh.default.gc_thresh3=65536
net.netfilter.nf_conntrack_max=1048576
net.netfilter.nf_conntrack_tcp_timeout_established=43200
```

### `/etc/sysctl.d/10-network-security.conf`

```ini
net.ipv4.conf.default.rp_filter=2
net.ipv4.conf.all.rp_filter=2
net.ipv4.conf.all.send_redirects=0
net.ipv4.conf.default.send_redirects=0
net.ipv4.conf.all.log_martians=1
net.ipv4.conf.default.log_martians=1
```

### `/etc/sysctl.d/10-bufferbloat.conf`

```ini
net.core.default_qdisc = fq_codel
```

### Recommended Additions for Production

These parameters are documented in this guide but **not yet deployed** on the production BNG. They should be added during the next maintenance window:

| Parameter | Value | Category | Risk if missing |
|-----------|-------|----------|-----------------|
| `nf_conntrack_buckets` | `262144` | Performance | Slow conntrack lookup under heavy NAT load |
| `nf_conntrack_tcp_timeout_fin_wait` | `30` | Performance | Stale FIN_WAIT entries waste conntrack slots |
| `nf_conntrack_udp_timeout` | `10` | Performance | DNS conntrack entries live 3x longer than needed |
| `nf_conntrack_udp_timeout_stream` | `60` | Performance | Dead UDP streams waste conntrack slots |
| `nf_conntrack_icmp_timeout` | `10` | Performance | Ping conntrack entries live 3x longer than needed |
| `tcp_fin_timeout` | `30` | Performance | Dead TCP connections in FIN_WAIT_2 for 60s |
| `tcp_tw_reuse` | `1` | Performance | Source port exhaustion under heavy NAT |
| `tcp_no_metrics_save` | `1` | Performance | Subscriber metric poisoning via cached TCP state |
| `tcp_congestion_control` | `bbr` | Performance | Suboptimal throughput on lossy subscriber links |
| `vm.min_free_kbytes` | `131072` | Stability | OOM killer during traffic bursts |
| `accept_redirects` | `0` | **Security** | Routing table manipulation from subscriber network |
| `secure_redirects` | `0` | **Security** | Gateway-sourced redirect attacks |
| `accept_source_route` | `0` | **Security** | Firewall bypass via source-routed packets |
| `tcp_syncookies` | `1` | **Security** | SYN flood denial of service |
| `icmp_echo_ignore_broadcasts` | `1` | **Security** | Smurf DDoS amplification |
| `icmp_ignore_bogus_error_responses` | `1` | **Security** | Log spam from malformed CPE ICMP errors |
| `LimitNOFILE` | `65536` | Stability | Per-process FD limit too low (default 1024) |

To apply all recommended additions at once, use the complete config files in the [Quick Apply](#quick-apply) section — they include both the existing production values and all recommended additions.
