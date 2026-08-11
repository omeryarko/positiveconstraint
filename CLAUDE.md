# PosConCom — project notes

## Machines

Omer works on this project from two machines. This section is in git so a session on
either machine sees both specs.

### Linux minipc — `yarko-MINIPC-PN62`

Primary working directory: `/home/yarko/PosConCom`. Specification read 2026-08-11.

| Item | Specification |
|---|---|
| Model | ASUSTeK MINIPC PN62 (board PN62) |
| BIOS | ASUSTeK 0807, 01 Nov 2019 |
| CPU | Intel Core i7-10510U (Comet Lake-U), 4 cores / 8 threads, 1.80 GHz base, 4.90 GHz max turbo |
| Cache | L1 128 KiB data + 128 KiB instruction, L2 1 MiB, L3 8 MiB |
| Graphics | Intel UHD Graphics (Comet Lake-U GT2), integrated, uses system memory |
| Memory | 16 GB DDR4-2667 SO-DIMM, 1 rank, 1.2 V, Transcend JM2666HSE-16G, in ChannelA-DIMM1 |
| Memory slots | 2 total. ChannelB-DIMM1 is empty, so the memory runs in single channel |
| Swap | 2 GB |
| Storage | Transcend TS480GMTS820S, 480 GB SATA SSD. Root partition 439 GB, 43% used on 2026-08-11 |
| Network | Intel I219-V Gigabit Ethernet, Intel Comet Lake PCH-LP CNVi Wi-Fi |
| OS | Ubuntu 24.04.4 LTS, kernel 6.8.0-136-generic, x86_64 |

Things that change what you recommend on this machine:

- **The memory runs in single channel.** The integrated graphics share system memory, so
  single channel cuts graphics bandwidth by about half and slows memory-heavy work. The
  free ChannelB-DIMM1 slot takes a second 16 GB DDR4-2666 SO-DIMM for 32 GB and dual
  channel. Match the speed and the CAS latency; a second JM2666HSE-16G is the safe choice.
- **15 GiB usable RAM and a 4-core mobile U-series CPU.** Do not plan long local model
  runs, large parallel builds, or memory-hungry data jobs here. Push heavy work to the
  Cloudflare Worker or to a cloud run.
- **There is no passwordless sudo.** Root-only tools such as `dmidecode` and `lshw` need
  Omer to run them by hand and to paste the output.

### MacBook Pro — `MacBookPro14,1`

MacBook Pro 13-inch, 2017, two Thunderbolt 3 ports. Specification read 2026-08-11.

| Item | Specification |
|---|---|
| Model | Apple MacBook Pro (MacBookPro14,1) |
| Firmware | System firmware 529.140.2.0.0, SMC 2.43f11 |
| CPU | Intel Core i5-7360U (Kaby Lake), 2 cores / 4 threads, 2.30 GHz |
| Cache | L2 256 KB per core, L3 4 MB |
| Graphics | Intel Iris Plus Graphics 640, integrated, up to 1536 MB dynamic VRAM from system memory |
| Displays | Built-in Retina 2560 × 1600, plus an HP 27es 1920 × 1080 over HDMI/DVI |
| Memory | 8 GB, soldered — there is no upgrade path |
| Storage | Apple SSD AP0256J, 251 GB NVMe (PCIe x4, 8.0 GT/s). APFS volume 250.69 GB, only 6.48 GB free on 2026-08-11 (97% used) |
| OS | macOS 13.7.8 Ventura, build 22H730 |

Things that change what you recommend on this machine:

- **The disk is almost full. This is the first constraint to check.** 6.48 GB free of
  250.69 GB. A `node_modules` install, a Docker pull, a headless Chrome run, or a large
  git clone can fill it. Ask Omer to free space before any big install. macOS also gets
  slow and can fail to write swap when free space is this low.
- **8 GB of soldered RAM and 2 physical cores.** This is the weaker of the two machines
  and it cannot be upgraded. The graphics take up to 1536 MB of that same 8 GB.
- **Prefer the Linux minipc for heavy work.** It has twice the RAM, twice the cores, and
  241 GB free. Site builds, OG image rendering with headless Chrome, and any data job
  belong there. Use the Mac for editing, review, and deploys.
- **macOS 13 Ventura is the last major release for this model.** Do not recommend tools
  that need macOS 14 or later.

## Which machine to use

| Work | Machine |
|---|---|
| Site builds, headless Chrome OG rendering, data jobs, anything memory- or disk-heavy | Linux minipc |
| Editing, review, git, `wrangler` deploys | Either |
| Anything that needs more than about 5 GB of free disk | Linux minipc |
